#!/usr/bin/env python3
"""
FPGA RAG v2 — Blind Benchmark v2
====================================
v1'den farklı, hiç görülmemiş 26 soru.

6 Kategori:
  IP Config      (5 soru, w=20%) — design_1.tcl IP parametreleri
  RTL Deep       (5 soru, w=20%) — fifo2audpwm/axis2fifo derinlemesine
  C Advanced     (5 soru, w=20%) — helloworld.c farklı işlevler
  XDC Pins       (5 soru, w=20%) — PROJECT-B pin atamaları
  Cross-Project  (3 soru, w=10%) — iki proje karşılaştırma
  Trap           (3 soru, w=10%) — DB'de olmayan bilgiler

Kaynak doğrulama:
  - design_1.tcl: C_BAUDRATE=230400, FIFO depth=4096, clk audio=24.576MHz, DDR2 AXI=128bit
  - fifo2audpwm.v: duty[9:8] → kanal seçimi, aud_en FIFO empty kontrolü
  - helloworld.c: DMA_RESET_TIMEOUT=1000000U, DemoMode enum, WAV→u8 formül, dma_mm2s_done flag
  - create_axi_with_xdc.tcl / nexys_video.xdc: switches LVCMOS12, E22-M17, CFGBVS=VCCO
  - cross: xc7a100t vs xc7a200t, AXI DMA var/yok, clk_wiz NUM_OUT_CLKS

Çalıştırma:
    source .venv/bin/activate
    python scripts/test_blind_benchmark_v2.py --save
    python scripts/test_blind_benchmark_v2.py --verbose
    python scripts/test_blind_benchmark_v2.py --category ip_config
"""

from __future__ import annotations

import sys
import os
import re
import time
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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
# SORU KATEGORİLERİ  — v1'den BAĞIMSIZ, tamamen yeni sorular
# ─────────────────────────────────────────────────────────────────────────────

BLIND_QUESTIONS_V2: Dict[str, List[Dict]] = {

    # ─── IP Config (PROJECT-A, design_1.tcl kaynaklı) ─────────────────────
    "ip_config": [
        {
            "id": "IP-01",
            "project": "PROJECT-A",
            "question": (
                "nexys_a7_dma_audio projesinde design_1.tcl dosyasındaki "
                "axi_uartlite_0 IP'sinin C_BAUDRATE konfigürasyon değeri nedir? "
                "Bu değer serial iletişim tasarımını nasıl etkiler?"
            ),
            "key_terms":  ["230400", "baud", "uart", "C_BAUDRATE"],
            "key_values": ["230400"],
            "note": "design_1.tcl: CONFIG.C_BAUDRATE {230400}",
        },
        {
            "id": "IP-02",
            "project": "PROJECT-A",
            "question": (
                "nexys_a7_dma_audio projesinde design_1.tcl'deki "
                "axi_dma_0 IP'sinin c_mm2s_burst_size ve c_s2mm_burst_size "
                "değerleri nedir? Scatter Gather modu aktif mi?"
            ),
            "key_terms":  ["256", "burst", "scatter", "sg", "c_include_sg"],
            "key_values": ["256"],
            "note": "design_1.tcl: c_mm2s_burst_size=256, c_s2mm_burst_size=256, c_include_sg=0",
        },
        {
            "id": "IP-03",
            "project": "PROJECT-A",
            "question": (
                "design_1.tcl dosyasındaki clk_wiz_0 IP'sinde CLKOUT2 frekansı "
                "nedir? Bu saatin hangi audio bileşenine gittiği düşünülmektedir?"
            ),
            "key_terms":  ["24.576", "CLKOUT2", "audio", "clk_wiz", "MHz"],
            "key_values": ["24.576"],
            "note": "design_1.tcl: CLKOUT2_REQUESTED_OUT_FREQ=24.576 MHz (audio clock)",
        },
        {
            "id": "IP-04",
            "project": "PROJECT-A",
            "question": (
                "nexys_a7_dma_audio projesinde design_1.tcl'deki "
                "fifo_generator_0 IP'sinin Input_Depth ve Output_Depth değerleri "
                "nedir? Full_Threshold_Assert_Value kaçtır?"
            ),
            "key_terms":  ["4096", "4093", "fifo", "depth", "threshold"],
            "key_values": ["4096", "4093"],
            "note": "design_1.tcl: Input_Depth=4096, Output_Depth=4096, Full_Threshold_Assert_Value=4093",
        },
        {
            "id": "IP-05",
            "project": "PROJECT-A",
            "question": (
                "design_1.tcl'deki mig_7series_0 IP'sinin AXI data genişliği "
                "C0_S_AXI_DATA_WIDTH kaç bit olarak ayarlanmıştır? "
                "DDR2 CAS Latency değeri nedir?"
            ),
            "key_terms":  ["128", "DDR2", "CAS", "AXI", "data width"],
            "key_values": ["128", "5"],
            "note": "design_1.tcl: C0_S_AXI_DATA_WIDTH=128, CAS_Latency=5",
        },
    ],

    # ─── RTL Deep (PROJECT-A, fifo2audpwm.v / axis2fifo.v) ───────────────
    "rtl_deep": [
        {
            "id": "RTL-01",
            "project": "PROJECT-A",
            "question": (
                "fifo2audpwm.v modülünde aud_pwm sinyali nasıl üretilir? "
                "count register'ının hangi bitleri duty kayıtını seçmek için "
                "kullanılır, hangi bitleri PWM karşılaştırmasında kullanılır?"
            ),
            "key_terms":  ["count", "duty", "DATA_WIDTH", "9:8", "7:0", "karşılaştır"],
            "key_values": ["count[9:8]", "count[7:0]"],
            "note": "fifo2audpwm.v: aud_pwm = count[7:0] <= duty[count[9:8]]",
        },
        {
            "id": "RTL-02",
            "project": "PROJECT-A",
            "question": (
                "fifo2audpwm.v modülünde fifo_rd_en sinyalinin aktif olma koşulu "
                "nedir? '&count == 1' ifadesi ne anlama gelir?"
            ),
            "key_terms":  ["fifo_rd_en", "fifo_empty", "&count", "reduction", "1"],
            "key_values": ["&count", "fifo_empty"],
            "note": "fifo2audpwm.v: fifo_rd_en = (fifo_empty == 0 && &count == 1'b1) — &count is bitwise AND reduction",
        },
        {
            "id": "RTL-03",
            "project": "PROJECT-A",
            "question": (
                "fifo2audpwm.v modülünde fifo_rd_data[31:24] hangi duty kanalına "
                "atanır? fifo_rd_data[15:8] hangi duty kanalına atanır? "
                "duty array'inin her elemanının bit genişliği nedir?"
            ),
            "key_terms":  ["duty[3]", "duty[1]", "31:24", "15:8", "8:0", "9 bit"],
            "key_values": ["duty[3]", "duty[1]"],
            "note": "fifo2audpwm.v: duty[3]<=fifo_rd_data[31:24], duty[1]<=fifo_rd_data[15:8], duty is [DATA_WIDTH:0]=[8:0]",
        },
        {
            "id": "RTL-04",
            "project": "PROJECT-A",
            "question": (
                "axis2fifo.v modülünde hangi portlar 'unused' veya kullanılmayan "
                "olarak işaretlenmiştir? Bu portların neden kullanılmadığını "
                "AXI-Stream protokolü açısından açıklayın."
            ),
            "key_terms":  ["axis_tkeep", "axis_tlast", "unused", "kullanılmıyor", "paket"],
            "key_values": ["axis_tkeep", "axis_tlast"],
            "note": "axis2fifo.v: axis_tkeep and axis_tlast are unused (/* unused */)",
        },
        {
            "id": "RTL-05",
            "project": "PROJECT-A",
            "question": (
                "fifo2audpwm.v modülünde aud_en sinyali ne zaman 0 değerini alır? "
                "Bu davranış ses çıkışı (audio output) açısından nasıl yorumlanır?"
            ),
            "key_terms":  ["aud_en", "fifo_empty", "0", "ses", "audio"],
            "key_values": ["fifo_empty"],
            "note": "fifo2audpwm.v: aud_en <= 0 when fifo_empty == 1 (FIFO boş olduğunda audio amplifier kapatılır)",
        },
    ],

    # ─── C Advanced (PROJECT-A, helloworld.c) ─────────────────────────────
    "c_advanced": [
        {
            "id": "CA-01",
            "project": "PROJECT-A",
            "question": (
                "helloworld.c dosyasında DMA_RESET_TIMEOUT_CNT ve "
                "DMA_BUSY_TIMEOUT_CNT sabitlerinin değerleri nedir? "
                "Bu sabitlerin birimi ne olabilir?"
            ),
            "key_terms":  ["DMA_RESET_TIMEOUT_CNT", "DMA_BUSY_TIMEOUT_CNT",
                           "1000000", "2000000"],
            "key_values": ["1000000", "2000000"],
            "note": "helloworld.c: #define DMA_RESET_TIMEOUT_CNT 1000000U, DMA_BUSY_TIMEOUT_CNT 2000000U",
        },
        {
            "id": "CA-02",
            "project": "PROJECT-A",
            "question": (
                "helloworld.c'deki DemoMode enum'unda DEMO_MODE_PAUSED değeri "
                "kaçtır? Enum'un toplam kaç modu vardır ve bunlar nelerdir?"
            ),
            "key_terms":  ["DEMO_MODE_PAUSED", "0", "HW_TONE_GEN", "SW_TONE_GEN",
                           "RECV_WAV", "PLAY_WAV"],
            "key_values": ["0", "5"],
            "note": "helloworld.c: DemoMode enum — PAUSED=0, HW_TONE_GEN, SW_TONE_GEN, RECV_WAV_FILE, PLAY_WAV_FILE (5 mode)",
        },
        {
            "id": "CA-03",
            "project": "PROJECT-A",
            "question": (
                "helloworld.c'deki recv_wav fonksiyonunda izin verilen "
                "maksimum WAV dosya boyutu nedir? "
                "16-bit WAV verisi 8-bit'e nasıl dönüştürülür?"
            ),
            "key_terms":  ["0x7FFFFF", "32768", "8", ">>", "u16", "u8"],
            "key_values": ["0x7FFFFF", "32768"],
            "note": "helloworld.c: max size=0x7FFFFF, formula: (u8)((u16)(wav_data[i]+32768)>>8)",
        },
        {
            "id": "CA-04",
            "project": "PROJECT-A",
            "question": (
                "helloworld.c'deki dma_mm2s_isr interrupt handler fonksiyonu "
                "hangi global değişkeni set eder? XAXIDMA_IRQ_IOC_MASK ne anlama gelir?"
            ),
            "key_terms":  ["dma_mm2s_done", "IOC", "interrupt", "1", "flag"],
            "key_values": ["dma_mm2s_done", "XAXIDMA_IRQ_IOC_MASK"],
            "note": "helloworld.c: dma_mm2s_done = 1 when XAXIDMA_IRQ_IOC_MASK fires (IOC = Interrupt on Complete)",
        },
        {
            "id": "CA-05",
            "project": "PROJECT-A",
            "question": (
                "helloworld.c'deki Demo struct'ında XIntc intc_inst alanı var mı? "
                "init fonksiyonunda XIntc interrupt controller başlatma sırası nasıldır?"
            ),
            "key_terms":  ["XIntc", "intc_inst", "XIntc_Initialize", "XIntc_Connect",
                           "XIntc_Start"],
            "key_values": ["XIntc", "intc_inst"],
            "note": "helloworld.c: Demo struct has XIntc intc_inst; init() calls XIntc_Initialize→XIntc_Connect→XIntc_Start",
        },
    ],

    # ─── XDC Pins (PROJECT-B) ─────────────────────────────────────────────
    "xdc_pins": [
        {
            "id": "XP-01",
            "project": "PROJECT-B",
            "question": (
                "axi_gpio_example projesinde switches[0] ve switches[7] hangi "
                "PACKAGE_PIN'lere atanmıştır? Switch pinleri için IOSTANDARD nedir?"
            ),
            "key_terms":  ["E22", "M17", "LVCMOS12", "switch"],
            "key_values": ["E22", "M17", "LVCMOS12"],
            "note": "nexys_video.xdc / create_axi*.tcl: switches[0]=E22, switches[7]=M17, IOSTANDARD=LVCMOS12",
        },
        {
            "id": "XP-02",
            "project": "PROJECT-B",
            "question": (
                "axi_gpio_example projesinde leds[3] ve leds[6] hangi "
                "PACKAGE_PIN'lere atanmıştır? LED pinleri için IOSTANDARD nedir?"
            ),
            "key_terms":  ["U16", "W15", "LVCMOS25", "led"],
            "key_values": ["U16", "W15", "LVCMOS25"],
            "note": "nexys_video.xdc / create_axi*.tcl: leds[3]=U16, leds[6]=W15, IOSTANDARD=LVCMOS25",
        },
        {
            "id": "XP-03",
            "project": "PROJECT-B",
            "question": (
                "Nexys-Video-Master.xdc dosyasında tanımlı "
                "CFGBVS ve CONFIG_VOLTAGE değerleri nedir? "
                "Bu konfigürasyonlar ne anlama gelir?"
            ),
            "key_terms":  ["CFGBVS", "VCCO", "CONFIG_VOLTAGE", "3.3"],
            "key_values": ["VCCO", "3.3"],
            "note": "Nexys-Video-Master.xdc: set_property CFGBVS VCCO, CONFIG_VOLTAGE 3.3",
        },
        {
            "id": "XP-04",
            "project": "PROJECT-B",
            "question": (
                "create_axi_with_xdc.tcl dosyasında axi_gpio_0 IP'si dual channel "
                "(çift kanallı) olarak mı konfigüre edilmiştir? "
                "C_IS_DUAL ve GPIO2 kanalının kullanımını açıklayın."
            ),
            "key_terms":  ["C_IS_DUAL", "1", "GPIO2", "switch", "input", "dual"],
            "key_values": ["C_IS_DUAL", "switches"],
            "note": "create_axi_with_xdc.tcl: C_IS_DUAL=1, GPIO→LEDs(output), GPIO2→Switches(input)",
        },
        {
            "id": "XP-05",
            "project": "PROJECT-B",
            "question": (
                "axi_gpio_example projesinde switches[3] ve switches[5] "
                "hangi PACKAGE_PIN'lere atanmıştır?"
            ),
            "key_terms":  ["G22", "J16", "switch", "PACKAGE_PIN"],
            "key_values": ["G22", "J16"],
            "note": "nexys_video.xdc: switches[3]=G22, switches[5]=J16, IOSTANDARD=LVCMOS12",
        },
    ],

    # ─── Cross-Project (A vs B karşılaştırması) ───────────────────────────
    "cross_project": [
        {
            "id": "CR-01",
            "question": (
                "nexys_a7_dma_audio (PROJECT-A) ve axi_gpio_example (PROJECT-B) "
                "projelerinin hedef FPGA part numaraları nedir? "
                "Bu iki part arasındaki temel fark nedir?"
            ),
            "project": "BOTH",
            "key_terms":  ["xc7a100t", "xc7a200t", "100T", "200T",
                           "Artix", "nexys"],
            "key_values": ["xc7a100tcsg324-1", "xc7a200tsbg484-1"],
            "note": "A: xc7a100tcsg324-1 (Nexys A7-100T), B: xc7a200tsbg484-1 (Nexys Video)",
        },
        {
            "id": "CR-02",
            "question": (
                "nexys_a7_dma_audio projesinde AXI DMA IP bloğu var mı? "
                "axi_gpio_example projesinde var mı? "
                "Bu fark iki proje arasındaki temel amaç farkını nasıl yansıtır?"
            ),
            "project": "BOTH",
            "key_terms":  ["axi_dma", "DMA", "GPIO", "audio", "yoktur",
                           "farklı", "amaç"],
            "key_values": ["axi_dma"],
            "note": "A: axi_dma_0 var (audio streaming), B: DMA yok (GPIO LED/switch kontrol)",
        },
        {
            "id": "CR-03",
            "question": (
                "nexys_a7_dma_audio projesinde clk_wiz_0 'ın kaç çıkış saati "
                "(NUM_OUT_CLKS) vardır? axi_gpio_example projesinde clk_wiz "
                "konfigürasyonu nasıl farklılık gösterir?"
            ),
            "project": "BOTH",
            "key_terms":  ["NUM_OUT_CLKS", "2", "audio", "24.576",
                           "fark", "clock"],
            "key_values": ["2", "24.576"],
            "note": "A: NUM_OUT_CLKS=2 (100MHz+24.576MHz audio), B: single output 100MHz clock",
        },
    ],

    # ─── Trap (DB'de olmayan bilgiler) ────────────────────────────────────
    "trap_v2": [
        {
            "id": "TR2-01",
            "project": "PROJECT-A",
            "question": (
                "nexys_a7_dma_audio projesinde kullanılan audio codec chip'i nedir? "
                "CS4344 veya CS5343 gibi bir ses codec'in I2S konfigürasyon "
                "parametreleri nelerdir?"
            ),
            "expected": "NOT_IN_DB",
            "hallucination_keywords": ["cs4344", "cs5343", "i2s", "mclk", "bclk",
                                       "lrclk", "codec", "44.1"],
            "note": "Projede audio codec YOK — direkt PWM kullanılıyor (fifo2audpwm). CS4344/CS5343 hallucination.",
        },
        {
            "id": "TR2-02",
            "project": "PROJECT-A",
            "question": (
                "nexys_a7_dma_audio projesinde design_1.tcl'de Ethernet PHY "
                "bloğu (LiteEth veya Xilinx Ethernet) yapılandırılmış mı? "
                "MAC adresi ve PHY arayüzü (RGMII/SGMII) nedir?"
            ),
            "expected": "NOT_IN_DB",
            "hallucination_keywords": ["ethernet", "mac", "phy", "rgmii", "sgmii",
                                       "liteeth", "axi_ethernet", "88e1512"],
            "note": "Projede Ethernet bloğu YOK — audio DMA projesi, network stack yok",
        },
        {
            "id": "TR2-03",
            "project": "PROJECT-B",
            "question": (
                "axi_gpio_example projesinde MicroBlaze işlemcisi üzerinde "
                "FreeRTOS işletim sistemi çalışıyor mu? "
                "Kaç task tanımlanmıştır ve heap boyutu nedir?"
            ),
            "expected": "NOT_IN_DB",
            "hallucination_keywords": ["freertos", "task", "heap", "vtaskcreate",
                                       "scheduler", "os", "rtos"],
            "note": "Projede FreeRTOS YOK — bare-metal uygulama (helloworld.c direkt çalışır)",
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORİ META (isim + ağırlık)
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_INFO_V2 = {
    "ip_config":     ("IP Config  (design_1.tcl, PROJECT-A)",   0.20),
    "rtl_deep":      ("RTL Deep   (fifo2audpwm, PROJECT-A)",     0.20),
    "c_advanced":    ("C Advanced (helloworld.c, PROJECT-A)",    0.20),
    "xdc_pins":      ("XDC Pins   (PROJECT-B)",                  0.20),
    "cross_project": ("Cross-Project (A ↔ B)",                  0.10),
    "trap_v2":       ("Trap v2    (DB'de yok)",                  0.10),
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
]

_NEGATION_WORDS = [
    # Türkçe — statik
    "yok", "değil", "bulunmamaktadır", "bulunmuyor", "içermemektedir",
    "mevcut değil", "yer almıyor", "kullanılmıyor", "kullanılmamaktadır",
    "olmayan", "yoktur", "hayır", "bulunamadı", "desteklenmiyor",
    "reddediyorum", "bilinmiyor", "içermiyor", "bulunmamakta",
    "içermemekte", "kullanılmamakta", "mevcut olmayan", "devre dışı",
    "etkin değil", "aktif değil", "tanımlanmamış", "belirtilmemiş",
    # Türkçe — fiil olumsuz ekleri
    "çalışmadığı", "çalışmıyor", "çalışmamaktadır", "çalışmamakta",
    "yer almadığı", "yer almamaktadır",
    "bulunmadığı", "bulunmadı", "bulunmayan",
    "kullanılmadığı", "kullanılmamaktadır",
    "tanımlanmadığı", "tanımlanmamış",
    "içermediği", "içermemektedir",
    "görmüyorum", "gözlenmemektedir", "tespit edilememiştir",
    "yer almamış", "mevcut değildir", "mevcut olmadığı",
    "kullanılmamış", "eklenmemiş", "bağlı değil", "desteklenmemektedir",
    # İngilizce
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
            window = ans_lower[max(0, m.start()-150): m.end()+80]
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
    from rag_v2.graph_store       import GraphStore
    from rag_v2.vector_store_v2   import VectorStoreV2
    from rag_v2.source_chunk_store import SourceChunkStore
    from rag_v2.query_router      import QueryRouter
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
        "question":    question[:80],
        "query_type":  qt.value,
        "vector_hits": len(qr.vector_hits),
        "graph_nodes": len(qr.graph_nodes),
        "graph_edges": len(qr.graph_edges),
        "source_chunks": len(sc_chunks),
        "chunk_files": [Path(f).name for f in chunk_files if f],
        "confidence":  gr.overall_confidence,
        "warnings":    gr.warnings,
        "answer":      answer,
        "elapsed_s":   round(time.time() - t0, 2),
    }
    if verbose:
        print(f"\n    Q: {question[:100]}")
        print(f"    [Type={qt.value} | nodes={len(qr.graph_nodes)} | "
              f"edges={len(qr.graph_edges)} | chunks={len(sc_chunks)}]")
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
    label, _ = CATEGORY_INFO_V2[cat_key]
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
            print(f"    Source: {r['source_chunks']} chunk | {r['chunk_files']}")
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
    print(f"{B}  BLIND BENCHMARK v2 — ÖZET RAPOR{RST}")
    print(f"{B}{'═'*68}{RST}")

    total_weighted = 0.0
    for cr in cat_results:
        cat_key = cr["category"]
        _, weight = CATEGORY_INFO_V2.get(cat_key, ("?", 0.20))
        s   = cr["score"]
        bar = "█" * int(s * 20) + "░" * (20 - int(s * 20))
        total_weighted += s * weight
        print(f"  {cr['label']:40s} {bar} {s:.3f} [{grade(s)}] (w={weight:.0%})")

    print(f"\n  {'─'*68}")
    print(f"  AĞIRLIKLI TOPLAM SKOR : {total_weighted:.3f} → {grade(total_weighted)}")
    print(f"  {'─'*68}")

    all_q  = [q for cr in cat_results for q in cr["questions"]]
    n_total = len(all_q)
    n_pass  = sum(1 for q in all_q if q["score"] >= 0.80)
    n_fail  = sum(1 for q in all_q if q["score"] < 0.50)
    n_trap  = sum(1 for q in all_q if q["type"] == "trap")
    n_trap_pass = sum(1 for q in all_q if q["type"] == "trap" and q["score"] >= 0.80)

    print(f"\n  Toplam soru      : {n_total}")
    print(f"  Geçen (≥0.80)    : {n_pass}/{n_total}")
    print(f"  Başarısız (<0.50): {n_fail}/{n_total}")
    print(f"  Trap geçen       : {n_trap_pass}/{n_trap}")

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
    parser = argparse.ArgumentParser(description="FPGA RAG v2 Blind Benchmark v2")
    parser.add_argument("--save",     action="store_true", help="JSON raporu kaydet")
    parser.add_argument("--verbose",  action="store_true", help="Tam cevapları göster")
    parser.add_argument("--category", type=str, default="",
                        help="Sadece belirli kategori çalıştır: "
                             "ip_config|rtl_deep|c_advanced|xdc_pins|cross_project|trap_v2")
    args = parser.parse_args()

    n_total = sum(len(v) for v in BLIND_QUESTIONS_V2.values())
    print(f"\n{B}{'═'*68}")
    print(f"  FPGA RAG v2 — Blind Benchmark v2")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*68}{RST}")
    print(f"\n  Kapsam  : {n_total} soru × 6 kategori")
    print(f"  Önemli  : v1'den tamamen farklı, hiç görülmemiş sorular!")
    print(f"  Fark    : IP Config + RTL Deep + C Advanced + XDC Pins + Cross-Project + Trap")

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

    for cat_key, questions in BLIND_QUESTIONS_V2.items():
        if only_cat and cat_key != only_cat:
            continue
        cr = run_category(cat_key, questions, router, gate, llm, system_prompt, args.verbose)
        cat_results.append(cr)

    elapsed = round(time.time() - t_start, 1)
    final_score = print_summary(cat_results)
    print(f"  Toplam süre: {elapsed}s")

    if args.save:
        out_path = _ROOT / "blind_benchmark_v2_report.json"
        report = {
            "timestamp":    datetime.now().isoformat(),
            "version":      "v2",
            "total_score":  final_score,
            "overall_grade": grade_raw(final_score),
            "elapsed_s":    elapsed,
            "n_questions":  n_total,
            "categories":   cat_results,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  Rapor kaydedildi: {out_path}")


if __name__ == "__main__":
    main()
