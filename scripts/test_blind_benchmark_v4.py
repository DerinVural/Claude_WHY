#!/usr/bin/env python3
"""
FPGA RAG v2 — Blind Benchmark v4
====================================
PDF Reference Manual (nexys-a7_rm.pdf) tam indekslenmiş haliyle test.
v3'ten tamamen farklı, yeni sorular — PDF indexleme sonrası kalite ölçümü.

7 Kategori:
  PDF HW Specs    (5 soru, w=25%) — board donanım spesifikasyonları (PDF)
  PDF Interfaces  (4 soru, w=20%) — bağlantı arayüzleri / pin atamaları (PDF)
  PDF Timing      (3 soru, w=15%) — VGA/DDR2 zamanlama (PDF tablo değerleri)
  IP Config       (3 soru, w=10%) — design_1.tcl (v2/v3'ten farklı)
  RTL Signal      (3 soru, w=10%) — tone_generator.v / fifo2audpwm.v
  Cross-Project   (2 soru, w=10%) — A vs B + PDF cross-check
  Trap v4         (3 soru, w=10%) — DB'de olmayan bilgiler (PDF tuzak dahil)

Doğrulama kaynakları (nexys-a7_rm.pdf):
  - p.2-3:   A7-100T: 63400 LUT, A7-50T: 32600 LUT, 6 vs 5 CMT
  - p.4:     1.0V=ADP2118/3A, 1.8V=ADP2138/0.8A, 3.3V=ADP2118/3A
  - p.8-10:  DDR2 MT47H64M16HR-25E, 128MiB, 16-bit, 1.8V, max 3000ps
  - p.10-11: SPI Flash S25FL128S, CS#=L13, SDI=K17, SDO=K18, SCK=E9
  - p.12:    Ethernet LAN8720A, RMII, PHY=00001
  - p.13:    Oscillator 100 MHz at pin E3, bank 35 MRCC
  - p.14:    USB-UART FT2232HQ, TXD=C4, RXD=D4, CTS=D3, RTS=E5
  - p.15:    USB HID PIC24FJ128, PS2_CLK=F4, PS2_DAT=B2
  - p.18:    VGA: 14 signals, 4 bits/color, 4096 colors, RED0=A3, HSYNC=B11
  - p.21:    VGA 640x480@60Hz: Tpw=96 clk (H), front porch=16 clk, 25 MHz pixel
  - p.22-24: 16 switches, 6 buttons, 16 LEDs, 8-digit 7-seg, 2 tri-color LED
  - p.25:    Pmod JA: JA1=C17, JA2=D18, JA3=E18; JXADC1=A13(AD3P)

Çalıştırma:
    source .venv/bin/activate
    python scripts/test_blind_benchmark_v4.py --save
    python scripts/test_blind_benchmark_v4.py --verbose
    python scripts/test_blind_benchmark_v4.py --category pdf_hw
    python scripts/test_blind_benchmark_v4.py --category trap_v4
"""

from __future__ import annotations

import sys
import re
import time
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Tuple

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

# ─────────────────────────────────────────────────────────────────────────────
# RENK / FORMAT
# ─────────────────────────────────────────────────────────────────────────────
G   = "\033[92m"
Y   = "\033[93m"
R   = "\033[91m"
B   = "\033[94m"
RST = "\033[0m"

def ok(s):   return f"{G}✓{RST} {s}"
def warn(s): return f"{Y}⚠{RST} {s}"
def err(s):  return f"{R}✗{RST} {s}"
def hdr(s):  return f"\n{B}{'═'*68}{RST}\n{B}  {s}{RST}\n{B}{'═'*68}{RST}"

def grade(score: float) -> str:
    if score >= 0.80: return f"{G}A{RST}"
    if score >= 0.65: return f"{Y}B{RST}"
    if score >= 0.50: return f"{Y}C{RST}"
    if score >= 0.35: return f"{R}D{RST}"
    return f"{R}F{RST}"

def grade_raw(score: float) -> str:
    if score >= 0.80: return "A"
    if score >= 0.65: return "B"
    if score >= 0.50: return "C"
    if score >= 0.35: return "D"
    return "F"


# ─────────────────────────────────────────────────────────────────────────────
# SORULAR
# ─────────────────────────────────────────────────────────────────────────────

BLIND_QUESTIONS_V4: Dict[str, List[Dict]] = {

    # ─── PDF HW Specs — board donanım spesifikasyonları ───────────────────
    "pdf_hw": [
        {
            "id": "PH-01",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7-100T boardundaki DDR2 RAM'in part numarası nedir? "
                "Kapasite, veri yolu genişliği ve besleme voltajı nedir? "
                "Nexys A7 referans kılavuzuna göre cevap verin."
            ),
            "key_terms":  ["MT47H64M16HR", "128", "16", "1.8V", "DDR2"],
            "key_values": ["MT47H64M16HR", "128", "16"],
            "note": "nexys-a7_rm.pdf s.8: MT47H64M16HR-25E, 128MiB, 16-bit, 1.8V",
        },
        {
            "id": "PH-02",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 referans kılavuzundaki ürün karşılaştırma tablosuna göre "
                "XC7A100T-1CSG324C FPGA kaç Look-up Table (LUT) ve kaç DSP Slice "
                "içerir? XC7A50T-1CSG324I'nın LUT ve DSP değerleri nedir?"
            ),
            "key_terms":  ["63,400", "32,600", "XC7A100T", "XC7A50T", "LUT", "DSP", "240", "120"],
            "key_values": ["63,400", "32,600"],
            "note": "nexys-a7_rm.pdf s.2: 100T=63400 LUT/240 DSP/6 CMT, 50T=32600 LUT/120 DSP/5 CMT",
        },
        {
            "id": "PH-03",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 boardunda 1.0V çekirdek gerilimini sağlayan regülatörün "
                "model numarası nedir ve maksimum akım kapasitesi nedir? "
                "1.8V ve 3.3V için hangi regülatörler kullanılmıştır?"
            ),
            "key_terms":  ["ADP2118", "IC22", "IC17", "1.0V", "1.8V", "3.3V", "3A", "0.8A"],
            "key_values": ["ADP2118", "3A", "0.8A"],
            "note": "nexys-a7_rm.pdf Table 1.1: 1.0V=IC22/ADP2118/3A, 1.8V=IC23/ADP2118/0.8A, 3.3V=IC17/ADP2118/3A",
        },
        {
            "id": "PH-04",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 boardundaki Quad-SPI Flash belleğin modeli nedir? "
                "Nexys-A7-100T-Master.xdc dosyasına göre QSPI_CSN ve QSPI_DQ[0] "
                "hangi FPGA pinlerine bağlıdır?"
            ),
            "key_terms":  ["S25FL128S", "L13", "K17", "SPI", "Flash", "QSPI"],
            "key_values": ["S25FL128S", "L13", "K17"],
            "note": "nexys-a7_rm.pdf: Spansion S25FL128S; Master.xdc: QSPI_CSN=L13, QSPI_DQ[0]=K17 (SCK=E9 dedicated pin via STARTUPE2)",
        },
        {
            "id": "PH-05",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 boardundaki 100 MHz osilatör hangi FPGA pinine bağlıdır? "
                "Bu pin hangi bankta ve ne tür bir clock girişidir?"
            ),
            "key_terms":  ["E3", "100", "MHz", "bank", "35", "MRCC"],
            "key_values": ["E3", "100", "35"],
            "note": "nexys-a7_rm.pdf s.13: 100 MHz at pin E3, bank 35 MRCC input",
        },
    ],

    # ─── PDF Interfaces — bağlantı arayüzleri ve pin atamaları ───────────
    "pdf_interfaces": [
        {
            "id": "PI-01",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 boardundaki USB-UART köprüsünün çipi nedir? "
                "UART TXD ve RXD sinyalleri hangi FPGA pinlerine bağlıdır?"
            ),
            "key_terms":  ["FT2232HQ", "C4", "D4", "TXD", "RXD", "UART"],
            "key_values": ["FT2232HQ", "C4", "D4"],
            "note": "nexys-a7_rm.pdf s.14: FT2232HQ, TXD=C4, RXD=D4, CTS=D3, RTS=E5",
        },
        {
            "id": "PI-02",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 VGA portunun pin bağlantıları nedir? "
                "Nexys-A7-100T-Master.xdc dosyasına göre VGA_R[0], VGA_G[0], "
                "VGA_B[0] ve VGA_HS sinyalleri hangi FPGA pinlerine bağlıdır? "
                "Kaç FPGA sinyali kullanılmaktadır?"
            ),
            "key_terms":  ["A3", "C6", "B7", "B11", "14", "VGA_HS", "VGA_R", "VGA_G", "VGA_B"],
            "key_values": ["A3", "C6", "B7", "B11", "14"],
            "note": "Master.xdc: VGA_R[0]=A3, VGA_G[0]=C6, VGA_B[0]=B7, VGA_HS=B11, 14 sinyaller",
        },
        {
            "id": "PI-03",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 USB HID Host bağlantısının kontrol MCU'su nedir? "
                "PS/2 CLK ve DATA sinyalleri hangi FPGA pinlerine bağlıdır?"
            ),
            "key_terms":  ["PIC24FJ128", "F4", "B2", "PS2_CLK", "PS2_DAT", "HID"],
            "key_values": ["PIC24FJ128", "F4", "B2"],
            "note": "nexys-a7_rm.pdf s.15: PIC24FJ128, PS2_CLK=F4, PS2_DAT=B2",
        },
        {
            "id": "PI-04",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 Pmod JA konektöründe JA1, JA2 ve JA3 sinyalleri "
                "hangi FPGA pinlerine bağlıdır? "
                "JXADC1 pini hangi FPGA pinine ve hangi analog kanala karşılık gelir?"
            ),
            "key_terms":  ["C17", "D18", "E18", "A13", "AD3P", "JA1", "JA2", "JXADC"],
            "key_values": ["C17", "D18", "E18", "A13"],
            "note": "nexys-a7_rm.pdf s.25: JA1=C17, JA2=D18, JA3=E18, JXADC1=A13(AD3P)",
        },
    ],

    # ─── PDF Timing — VGA / DDR2 zamanlama değerleri ──────────────────────
    "pdf_timing": [
        {
            "id": "PT-01",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 VGA portunda kaç farklı renk görüntülenebilir? "
                "Her renk kanalı kaç bit genişliğindedir? "
                "Bu tasarım piksel başına toplam kaç bit kullanır?"
            ),
            "key_terms":  ["4096", "4", "12", "bit", "renk", "VGA"],
            "key_values": ["4096", "4", "12"],
            "note": "nexys-a7_rm.pdf s.18: 4 bit/kanal × 3 = 12 bit/piksel = 4096 renk",
        },
        {
            "id": "PT-02",
            "project": "nexys_a7_dma_audio",
            "question": (
                "nexys-a7_rm.pdf Bölüm 8.1 VGA System Timing'e göre "
                "640x480@60Hz modunda yatay senkronizasyon (Horizontal Sync) "
                "pulse genişliği (Tpw) kaç pixel clock süresidir? "
                "Yatay front porch ve back porch kaç clock'tur? "
                "Pixel clock frekansı nedir?"
            ),
            "key_terms":  ["96", "16", "48", "25", "MHz", "Tpw", "front porch", "back porch"],
            "key_values": ["96", "16", "48", "25"],
            "note": "nexys-a7_rm.pdf s.21: Tpw=96, front porch=16, back porch=48 clks, 25 MHz pixel clock",
        },
        {
            "id": "PT-03",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 seven-segment display'inde gözle algılanamayan "
                "titreme (flicker) için minimum tazeleme frekansı ne olmalıdır? "
                "8 basamaklı gösterim için her basamak ne kadar süre aktif kalmalıdır?"
            ),
            "key_terms":  ["45", "1", "16", "ms", "Hz", "eight", "8", "segment"],
            "key_values": ["45", "1", "16"],
            "note": "nexys-a7_rm.pdf s.24: <45Hz flicker görünür, 1-16ms tazeleme, her digit 1/8 süre",
        },
    ],

    # ─── IP Config — design_1.tcl (v2/v3'ten farklı parametreler) ─────────
    "ip_config_v4": [
        {
            "id": "IC4-01",
            "project": "nexys_a7_dma_audio",
            "question": (
                "nexys_a7_dma_audio projesinde design_1.tcl'deki "
                "write_mig_file_design_1_mig_7series_0_0 prosedüründe "
                "UserMemoryAddressMap değeri nedir? "
                "BANK_ROW_COLUMN mu yoksa ROW_BANK_COLUMN mu seçilmiş?"
            ),
            "key_terms":  ["BANK_ROW_COLUMN", "ROW_BANK_COLUMN", "mig", "DDR2", "UserMemoryAddressMap"],
            "key_values": ["BANK_ROW_COLUMN"],
            "note": "design_1.tcl: write_mig_file proc: <UserMemoryAddressMap>BANK_ROW_COLUMN</UserMemoryAddressMap>",
        },
        {
            "id": "IC4-02",
            "project": "nexys_a7_dma_audio",
            "question": (
                "nexys_a7_dma_audio projesinde design_1.tcl'deki "
                "axi_dma_0 IP'sinin c_sg_length_width değeri nedir? "
                "Bu parametre ne işe yarar?"
            ),
            "key_terms":  ["c_sg_length_width", "24", "length", "transfer", "axi_dma"],
            "key_values": ["24"],
            "note": "design_1.tcl: CONFIG.c_sg_length_width {24} — scatter-gather transfer length bits",
        },
        {
            "id": "IC4-03",
            "project": "nexys_a7_dma_audio",
            "question": (
                "design_1.tcl'deki clk_wiz_0 IP'sinde "
                "CLKOUT2_REQUESTED_OUT_FREQ değeri nedir? "
                "MMCM_CLKFBOUT_MULT_F ve MMCM_DIVCLK_DIVIDE değerleri nelerdir?"
            ),
            "key_terms":  ["24.576", "CLKOUT2", "MMCM_CLKFBOUT_MULT_F", "7.125", "clk_wiz"],
            "key_values": ["24.576", "7.125"],
            "note": "design_1.tcl: CLKOUT2_REQUESTED_OUT_FREQ={24.576}, MMCM_CLKFBOUT_MULT_F={7.125}, MMCM_DIVCLK_DIVIDE={1}",
        },
    ],

    # ─── RTL Signal — tone_generator.v / fifo2audpwm.v ───────────────────
    "rtl_signal_v4": [
        {
            "id": "RS4-01",
            "project": "nexys_a7_dma_audio",
            "question": (
                "tone_generator.v modülünde axis_tlast sinyali nasıl üretilir? "
                "packet_count ve PACKET_SIZE parametrelerinin rolünü açıklayın."
            ),
            "key_terms":  ["packet_count", "PACKET_SIZE", "tlast", "axis_tlast",
                           "PACKET_SIZE-1", "eşit"],
            "key_values": ["packet_count", "PACKET_SIZE"],
            "note": "tone_generator.v: assign axis_tlast = (packet_count == PACKET_SIZE-1)",
        },
        {
            "id": "RS4-02",
            "project": "nexys_a7_dma_audio",
            "question": (
                "tone_generator.v modülündeki ACCUMULATOR_DEPTH parametresi "
                "varsayılan değeri nedir? "
                "Bu parametre dalga üretimini nasıl etkiler?"
            ),
            "key_terms":  ["ACCUMULATOR_DEPTH", "32", "frekans", "akümülatör", "DDS"],
            "key_values": ["32"],
            "note": "tone_generator.v: localparam ACCUMULATOR_DEPTH = 32",
        },
        {
            "id": "RS4-03",
            "project": "nexys_a7_dma_audio",
            "question": (
                "fifo2audpwm.v modülünde DATA_WIDTH parametresinin varsayılan "
                "değeri nedir? duty array'inin eleman sayısı ve her elemanın "
                "bit genişliği nedir?"
            ),
            "key_terms":  ["DATA_WIDTH", "8", "duty", "4", "9", "array"],
            "key_values": ["8", "4"],
            "note": "fifo2audpwm.v: DATA_WIDTH=8, duty[3:0] (4 element), duty [DATA_WIDTH:0] = [8:0] (9-bit)",
        },
    ],

    # ─── Cross-Project — A vs B + PDF cross-check ────────────────────────
    "cross_v4": [
        {
            "id": "CV4-01",
            "question": (
                "nexys_a7_dma_audio projesinde kullanılan Nexys A7-100T FPGA'nın "
                "part numarasını belirtin. Nexys A7 referans kılavuzuna göre bu "
                "board'un DDR2 belleği kaç MiB kapasiteye sahiptir?"
            ),
            "project": "nexys_a7_dma_audio + axi_gpio_example",
            "key_terms":  ["xc7a100t", "128", "DDR2", "MiB", "nexys"],
            "key_values": ["xc7a100t", "128"],
            "note": "project_info.tcl: xc7a100tcsg324-1; PDF: 128MiB DDR2 MT47H64M16HR-25E",
        },
        {
            "id": "CV4-02",
            "question": (
                "nexys_a7_dma_audio projesindeki tone_generator.v ses üretim yöntemi "
                "ile Nexys A7 referans kılavuzundaki audio çıkış bölümünde "
                "bahsedilen yöntem nedir? İkisi arasındaki benzerliği açıklayın."
            ),
            "project": "nexys_a7_dma_audio + axi_gpio_example",
            "key_terms":  ["PWM", "pulse", "modulation", "audio", "tone", "ses"],
            "key_values": ["PWM"],
            "note": "tone_generator.v: AXI-Stream ses paketi üretir; PDF s.30: PWM audio amplifier",
        },
    ],

    # ─── Trap v4 — DB'de olmayan bilgiler (PDF tuzakları dahil) ──────────
    "trap_v4": [
        {
            "id": "TR4-01",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 boardunda DDR3 SDRAM bellek modülü var mıdır? "
                "Eğer varsa, DDR3 MIG IP konfigürasyonunda kullanılan "
                "clock period ve veri yolu genişliği nedir?"
            ),
            "expected": "NOT_IN_DB",
            "hallucination_keywords": ["ddr3 mig", "ddr3 sdram var", "ddr3 bulunmaktadır",
                                       "ddr3 mevcuttur", "1066 mhz", "ddr3_sdram",
                                       "ddr3 clock"],
            "note": "Nexys A7'de DDR3 YOK — DDR2 (MT47H64M16HR-25E) kullanılıyor. DDR3 varlığı halüsinasyon.",
        },
        {
            "id": "TR4-02",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 VGA portu 16-bit true color (65536 renk) veya "
                "24-bit full color (16.7 milyon renk) destekliyor mu? "
                "Bu mod için gerekli donanım bağlantısı nedir?"
            ),
            "expected": "NOT_IN_DB",
            "hallucination_keywords": ["65536 renk", "65536 color", "16.7 million",
                                       "16.7 milyon renk", "true color destekl",
                                       "full color destekl", "16-bit vga destekl",
                                       "24-bit vga destekl"],
            "note": "Nexys A7 VGA yalnızca 12-bit (4096 renk) destekler. 16/24-bit desteklenir denmesi halüsinasyon.",
        },
        {
            "id": "TR4-03",
            "project": "nexys_a7_dma_audio",
            "question": (
                "Nexys A7 boardunda USB 3.0 (SuperSpeed) host portu var mıdır? "
                "USB 3.0 transferinde kullanılan FPGA IP bloğu ve bant genişliği nedir?"
            ),
            "expected": "NOT_IN_DB",
            "hallucination_keywords": ["usb 3.0 destekl", "usb 3.0 bulunmaktadır",
                                       "usb 3.0 mevcuttur", "5 gbps", "xhci controller",
                                       "usb 3.0 ip", "superspeed ip"],
            "note": "Nexys A7'de USB 3.0 YOK — PIC24FJ128 üzerinden USB 2.0 HID Host var.",
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORİ META
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_INFO_V4 = {
    "pdf_hw":          ("PDF HW Specs    (nexys-a7_rm.pdf donanım)",     0.25),
    "pdf_interfaces":  ("PDF Interfaces  (nexys-a7_rm.pdf bağlantı)",    0.20),
    "pdf_timing":      ("PDF Timing      (VGA/DDR2/7-seg zamanlama)",    0.15),
    "ip_config_v4":    ("IP Config v4    (design_1.tcl yeni params)",    0.10),
    "rtl_signal_v4":   ("RTL Signal v4   (tone_gen/fifo2audpwm)",        0.10),
    "cross_v4":        ("Cross v4        (proje+PDF çapraz)",            0.10),
    "trap_v4":         ("Trap v4         (DDR3/VGA16bit/USB3 tuzak)",    0.10),
}


# ─────────────────────────────────────────────────────────────────────────────
# SKOR
# ─────────────────────────────────────────────────────────────────────────────

NOT_IN_DB_SIGNALS = [
    "bilmiyorum", "context'te", "bağlamda", "bulunamadı", "mevcut değil",
    "yer almıyor", "bilgi yok", "not found", "not available", "cannot find",
    "no information", "kayıt yok", "verilmemiş", "belirtilmemiş",
    "sağlanan bilgide", "verilen context", "elimde yok", "bilgim yok",
    "erişemiyorum", "içermemektedir", "görünmüyor", "içinde değil",
    "bulunmamaktadır", "bulunmuyor", "tespit edilemedi",
    "cannot be determined", "not specified", "not documented",
    "not explicitly", "no specific", "tespit edilemez",
    "yoktur", "yok.", "yok,", "yoktu", "hayır",
    "desteklenmez", "desteklenmiyor", "desteklenmemektedir",
    "mevcut olmadığı", "geçerli değil",
    "ne de ", "ne ... ne de",
]

_NEGATION_WORDS = [
    "yok", "değil", "bulunmamaktadır", "bulunmuyor", "içermemektedir",
    "mevcut değil", "yer almıyor", "kullanılmıyor", "kullanılmamaktadır",
    "olmayan", "yoktur", "hayır", "bulunamadı", "desteklenmiyor",
    "reddediyorum", "bilinmiyor", "içermiyor", "bulunmamakta",
    "içermemekte", "kullanılmamakta", "mevcut olmayan", "devre dışı",
    "etkin değil", "aktif değil", "tanımlanmamış", "belirtilmemiş",
    "çalışmadığı", "çalışmıyor", "çalışmamaktadır",
    "yer almadığı", "yer almamaktadır",
    "bulunmadığı", "bulunmadı", "bulunmayan",
    "kullanılmadığı", "kullanılmamaktadır",
    "içermediği", "içermemektedir",
    "mevcut değildir", "mevcut olmadığı",
    "not ", "no ", "does not", "doesn't", "without", "absent",
    "not found", "not available", "not present", "not used", "disabled",
]


def score_real_question(q: Dict, answer: str) -> Tuple[float, List[str], List[str]]:
    ans_lower = answer.lower()
    term_hits = [t for t in q["key_terms"] if t.lower() in ans_lower]
    val_hits  = [v for v in q["key_values"] if v.lower() in ans_lower]
    term_score = len(term_hits) / len(q["key_terms"])
    val_score  = len(val_hits)  / len(q["key_values"])
    score = term_score * 0.60 + val_score * 0.40
    return round(score, 3), term_hits, val_hits


def score_trap_question(q: Dict, answer: str) -> Tuple[float, str, List[str]]:
    ans_lower = answer.lower()
    says_unknown = any(sig in ans_lower for sig in NOT_IN_DB_SIGNALS)

    halluc_matches = []
    for kw in q.get("hallucination_keywords", []):
        pat = re.compile(r'\b' + re.escape(kw.lower()) + r'\b')
        for m in pat.finditer(ans_lower):
            window = ans_lower[max(0, m.start()-200): m.end()+200]
            is_negated = any(neg in window for neg in _NEGATION_WORDS)
            if not is_negated:
                halluc_matches.append(m.group())

    has_halluc = len(halluc_matches) > 0

    if says_unknown and not has_halluc:
        return 1.0, "PASS", []
    elif says_unknown and has_halluc:
        return 0.5, "PARTIAL (reddetti ama uydurma değer var)", halluc_matches
    elif not says_unknown and has_halluc:
        return 0.0, "FAIL (hallucinasyon)", halluc_matches
    else:
        return 0.3, "PARTIAL (genel cevap, net ret yok)", []


# ─────────────────────────────────────────────────────────────────────────────
# SİSTEM YÜKLEME
# ─────────────────────────────────────────────────────────────────────────────

def load_system():
    from rag_v2.graph_store        import GraphStore
    from rag_v2.vector_store_v2    import VectorStoreV2
    from rag_v2.source_chunk_store import SourceChunkStore
    from rag_v2.query_router       import QueryRouter
    from rag_v2.hallucination_gate import HallucinationGate

    gs  = GraphStore(persist_path=str(_ROOT / "db/graph/fpga_rag_v2_graph.json"))
    vs  = VectorStoreV2(persist_directory=str(_ROOT / "db/chroma_graph_nodes"), threshold=0.35)
    sc  = SourceChunkStore(persist_directory=str(_ROOT / "db/chroma_source_chunks"))
    router = QueryRouter(gs, vs, n_vector_results=6, source_chunk_store=sc, n_source_results=10)
    gate   = HallucinationGate(gs)
    return gs, vs, sc, router, gate


def get_llm():
    from rag.llm_factory import get_llm as _get_llm
    return _get_llm("claude-sonnet-4-6")


def ask(question: str, router, gate, llm, system_prompt: str, verbose=False) -> Dict:
    from rag_v2.response_builder import build_llm_context
    from rag_v2.grounding_checker import GroundingChecker

    t0  = time.time()
    qt  = router.classify(question)
    qr  = router.route(question, qt)
    gr  = gate.check(qr.all_nodes(), qr.graph_edges)
    ctx = build_llm_context(qr, gr, max_nodes=12, max_chars=14000)

    answer = "[LLM yok]"
    if llm:
        try:
            answer = llm.generate(
                query=question, context_documents=[ctx],
                system_prompt=system_prompt, temperature=0.2,
            )
        except Exception as e:
            answer = f"[LLM HATA: {e}]"

    sc_chunks = getattr(qr, "source_chunks", [])

    if answer and not answer.startswith("[LLM"):
        grounding_warns = GroundingChecker().check(answer, sc_chunks, qr.graph_nodes)
        if grounding_warns:
            gr.warnings.extend(grounding_warns)

    chunk_files = list({c.get("file_path", "") for c in sc_chunks} if sc_chunks else set())

    result = {
        "question":     question[:80],
        "query_type":   qt.value,
        "vector_hits":  len(qr.vector_hits),
        "graph_nodes":  len(qr.graph_nodes),
        "graph_edges":  len(qr.graph_edges),
        "source_chunks": len(sc_chunks),
        "chunk_files":  [Path(f).name for f in chunk_files if f],
        "confidence":   gr.overall_confidence,
        "warnings":     gr.warnings,
        "answer":       answer,
        "elapsed_s":    round(time.time() - t0, 2),
    }
    if verbose:
        print(f"\n    Q: {question[:100]}")
        print(f"    [Type={qt.value} | nodes={len(qr.graph_nodes)} | "
              f"edges={len(qr.graph_edges)} | chunks={len(sc_chunks)}]")
        pdf_chunks = [c for c in sc_chunks if c.get("file_type") == "pdf"]
        if pdf_chunks:
            print(f"    PDF chunks: {[c.get('chunk_label','')[:30] for c in pdf_chunks[:2]]}")
        print(f"    A: {answer[:400]}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# TEST ÇALIŞTIRICISI
# ─────────────────────────────────────────────────────────────────────────────

def run_category(
    cat_key: str,
    questions: List[Dict],
    router, gate, llm, system_prompt: str,
    verbose: bool,
) -> Dict:
    label, _ = CATEGORY_INFO_V4[cat_key]
    print(hdr(f"KATEGORİ: {label}"))

    results = []
    for q in questions:
        is_trap = q.get("expected") == "NOT_IN_DB"
        print(f"\n  {B}{q['id']}{RST}  [{q['project']}]")

        r = ask(q["question"], router, gate, llm, system_prompt, verbose)

        if is_trap:
            score, verdict, halluc = score_trap_question(q, r["answer"])
            sym = ok if score >= 0.8 else (warn if score >= 0.4 else err)
            print(f"    {sym(f'Trap skor={score:.2f} — {verdict}')}")
            if halluc:
                print(f"    Uydurma: {halluc[:3]}")
            results.append({
                "id": q["id"], "category": cat_key,
                "project": q["project"], "type": "trap",
                "score": score, "verdict": verdict,
                "hallucination_matches": halluc,
                "source_chunks": r["source_chunks"],
                "chunk_files": r["chunk_files"],
                "query_type": r["query_type"],
                "answer_snippet": r["answer"][:300],
                "ground_truth": q.get("note", ""),
            })
        else:
            score, term_hits, val_hits = score_real_question(q, r["answer"])
            sym = ok if score >= 0.8 else (warn if score >= 0.5 else err)
            print(f"    {sym(f'Skor={score:.2f}')} | terms={term_hits} | vals={val_hits}")
            print(f"    Source: {r['source_chunks']} chunk | {r['chunk_files'][:2]}")
            results.append({
                "id": q["id"], "category": cat_key,
                "project": q["project"], "type": "real",
                "score": score,
                "term_hits": term_hits,
                "term_misses": [t for t in q["key_terms"] if t not in term_hits],
                "val_hits": val_hits,
                "val_misses": [v for v in q["key_values"] if v not in val_hits],
                "source_chunks": r["source_chunks"],
                "chunk_files": r["chunk_files"],
                "query_type": r["query_type"],
                "answer_snippet": r["answer"][:300],
                "ground_truth": q.get("note", ""),
            })

    avg = sum(x["score"] for x in results) / len(results) if results else 0
    print(f"\n  {B}Kategori skoru{RST}: {avg:.3f} → {grade(avg)}")
    return {
        "category": cat_key, "label": label,
        "score": round(avg, 3), "grade": grade_raw(avg),
        "n_questions": len(results), "questions": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ÖZET RAPOR
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(cat_results: List[Dict]) -> float:
    print(f"\n{B}{'═'*68}{RST}")
    print(f"{B}  BLIND BENCHMARK v4 — ÖZET RAPOR{RST}")
    print(f"{B}{'═'*68}{RST}")

    total_weighted = 0.0
    for cr in cat_results:
        cat_key = cr["category"]
        _, weight = CATEGORY_INFO_V4.get(cat_key, ("?", 0.10))
        s   = cr["score"]
        bar = "█" * int(s * 20) + "░" * (20 - int(s * 20))
        total_weighted += s * weight
        print(f"  {cr['label']:45s} {bar} {s:.3f} [{grade(s)}] (w={weight:.0%})")

    print(f"\n  {'─'*68}")
    print(f"  AĞIRLIKLI TOPLAM SKOR : {total_weighted:.3f} → {grade(total_weighted)}")
    print(f"  {'─'*68}")

    all_q  = [q for cr in cat_results for q in cr["questions"]]
    n_total = len(all_q)
    n_pass  = sum(1 for q in all_q if q["score"] >= 0.80)
    n_fail  = sum(1 for q in all_q if q["score"] < 0.50)
    n_trap  = sum(1 for q in all_q if q["type"] == "trap")
    n_trap_pass = sum(1 for q in all_q if q["type"] == "trap" and q["score"] >= 0.80)

    # PDF sorularının özet istatistikleri
    pdf_qs = [q for cr in cat_results
              if cr["category"].startswith("pdf")
              for q in cr["questions"]]
    pdf_pass = sum(1 for q in pdf_qs if q["score"] >= 0.80)

    print(f"\n  Toplam soru       : {n_total}")
    print(f"  Geçen (≥0.80)     : {n_pass}/{n_total}")
    print(f"  Başarısız (<0.50) : {n_fail}/{n_total}")
    print(f"  Trap geçen        : {n_trap_pass}/{n_trap}")
    print(f"  PDF soruları geçen: {pdf_pass}/{len(pdf_qs)}")

    worst = sorted(all_q, key=lambda x: x["score"])[:4]
    print(f"\n  En düşük 4 soru:")
    for q in worst:
        misses = q.get("term_misses", []) + q.get("val_misses", [])
        print(f"    {q['id']}: skor={q['score']:.2f} | eksik={misses}")

    print(f"{B}{'═'*68}{RST}\n")
    return round(total_weighted, 3)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FPGA RAG v2 Blind Benchmark v4 (PDF odaklı)")
    parser.add_argument("--save",     action="store_true", help="JSON raporu kaydet")
    parser.add_argument("--verbose",  action="store_true", help="Tam cevapları + PDF chunk göster")
    parser.add_argument("--category", type=str, default="",
                        help="Belirli kategori: "
                             "pdf_hw|pdf_interfaces|pdf_timing|"
                             "ip_config_v4|rtl_signal_v4|cross_v4|trap_v4")
    args = parser.parse_args()

    n_total = sum(len(v) for v in BLIND_QUESTIONS_V4.values())
    print(f"\n{B}{'═'*68}")
    print(f"  FPGA RAG v2 — Blind Benchmark v4 (PDF İndeksli)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*68}{RST}")
    print(f"\n  Kapsam  : {n_total} soru × 7 kategori")
    print(f"  YENİ    : nexys-a7_rm.pdf tam indekslenmiş (51 chunk)")
    print(f"  Odak    : PDF HW Specs, Interfaces, Timing + Trap (DDR3/VGA16bit/USB3)")

    print("\n  [SİSTEM] Yükleniyor...")
    gs, vs, sc, router, gate = load_system()
    llm = get_llm()
    if not llm:
        print(f"  {Y}⚠ LLM yok — API key bulunamadı.{RST}")

    from rag_v2.response_builder import FPGA_RAG_SYSTEM_PROMPT
    system_prompt = FPGA_RAG_SYSTEM_PROMPT.split("CONTEXT:")[0].strip()

    t_start = time.time()
    cat_results = []
    only_cat = args.category.lower()

    for cat_key, questions in BLIND_QUESTIONS_V4.items():
        if only_cat and cat_key != only_cat:
            continue
        cr = run_category(cat_key, questions, router, gate, llm, system_prompt, args.verbose)
        cat_results.append(cr)

    elapsed = round(time.time() - t_start, 1)
    final_score = print_summary(cat_results)
    print(f"  Toplam süre: {elapsed}s")

    if args.save:
        out_path = _ROOT / "blind_benchmark_v4_report.json"
        report = {
            "timestamp":     datetime.now().isoformat(),
            "version":       "v4",
            "total_score":   final_score,
            "overall_grade": grade_raw(final_score),
            "elapsed_s":     elapsed,
            "n_questions":   n_total,
            "categories":    cat_results,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  Rapor kaydedildi: {out_path}")


if __name__ == "__main__":
    main()
