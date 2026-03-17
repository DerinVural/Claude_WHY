#!/usr/bin/env python3
"""
FPGA RAG v2 — Blind Benchmark v5
====================================
"0'dan Proje Oluşturma" — Vivado Workflow HOW Sorguları
-------------------------------------------------------
Bu benchmark iki amaca hizmet eder:
1. Yeni proje oluşturma ve Vivado workflow HOW sorgularını ölçer
2. Mevcut kategorilerden seçilen regression guard soruları ile diğer
   kategorilerin etkilenmediğini doğrular.

7 Kategori:
  HOW New Project   (5 soru, w=25%) — IP Integrator ile sıfırdan proje
  HOW Synthesis     (4 soru, w=20%) — Sentez, Implementation, Bitstream
  HOW Constraints   (3 soru, w=15%) — XDC, Timing Constraints
  HOW IP Config     (3 soru, w=15%) — IP parametrelerini ayarlama
  WHAT Concepts     (3 soru, w=10%) — Kavramsal (UG kaynaklı)
  Regression TRACE  (3 soru, w=10%) — Mevcut TRACE sorularından seçim (v1)
  Trap v5           (3 soru, w=05%) — Workflow tuzakları

Çalıştırma:
    source .venv/bin/activate
    python scripts/test_blind_benchmark_v5.py --save
    python scripts/test_blind_benchmark_v5.py --verbose
    python scripts/test_blind_benchmark_v5.py --category how_new_project
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

BLIND_QUESTIONS_V5: Dict[str, List[Dict]] = {

    # ─── HOW New Project — IP Integrator ile sıfırdan proje ─────────────
    "how_new_project": [
        {
            "id": "HNP-01",
            "project": "general",
            "question": (
                "Vivado'da yeni bir MicroBlaze tabanlı gömülü sistem projesi "
                "oluştururken hangi adımları izlemeliyim? "
                "IP Integrator'dan başlayarak block design oluşturma, "
                "MicroBlaze ekleme ve wrapper sentezi aşamalarını açıklayın."
            ),
            "key_terms":  ["create_project", "block design", "MicroBlaze", "wrapper",
                           "create_bd_design", "IP Integrator", "make_wrapper"],
            "key_values": ["create_project", "MicroBlaze", "wrapper"],
            "note": "UG912/UG898: create_project → create_bd_design → add MicroBlaze → Run Block Automation → make_wrapper → launch_runs",
        },
        {
            "id": "HNP-02",
            "project": "general",
            "question": (
                "Vivado IP Integrator'da AXI GPIO IP bloğunu block design'a eklemek "
                "ve MicroBlaze'e bağlamak için hangi adımları uygulamalıyım? "
                "create_bd_cell ve connect_bd_intf_net komutlarını kullanarak "
                "TCL ile nasıl yapılır?"
            ),
            "key_terms":  ["create_bd_cell", "connect_bd_intf_net", "axi_gpio",
                           "S_AXI", "axi_interconnect", "AXI GPIO"],
            "key_values": ["create_bd_cell", "connect_bd_intf_net", "axi_gpio"],
            "note": "UG994/UG912: create_bd_cell xilinx.com:ip:axi_gpio → connect_bd_intf_net ile S_AXI → AXI interconnect",
        },
        {
            "id": "HNP-03",
            "project": "general",
            "question": (
                "Vivado'da yeni bir proje oluştururken 'Run Block Automation' ve "
                "'Run Connection Automation' adımları ne zaman ve hangi sırayla "
                "çalıştırılmalıdır? Bu iki otomasyon arasındaki fark nedir?"
            ),
            "key_terms":  ["Run Block Automation", "Run Connection Automation",
                           "automation", "MicroBlaze", "AXI", "bağlantı"],
            "key_values": ["Run Block Automation", "Run Connection Automation"],
            "note": "UG994: Block Automation önce (MicroBlaze local memory/debug kurar), Connection Automation sonra (AXI bağlantıları tamamlar)",
        },
        {
            "id": "HNP-04",
            "project": "general",
            "question": (
                "Vivado'da block design HDL wrapper nasıl oluşturulur? "
                "make_wrapper komutu ne işe yarar ve sentez öncesi neden "
                "gereklidir? TCL komutu nedir?"
            ),
            "key_terms":  ["make_wrapper", "wrapper", "HDL", "top-level",
                           "add_files", "set_property top"],
            "key_values": ["make_wrapper", "wrapper"],
            "note": "UG895/UG894: make_wrapper -files [get_files *.bd] -top → add_files → set_property top",
        },
        {
            "id": "HNP-05",
            "project": "general",
            "question": (
                "Vivado'da bir Clocking Wizard (clk_wiz) IP'sini block design'a "
                "ekleyip 100 MHz giriş saatten 50 MHz ve 25 MHz çıkış saatleri "
                "oluşturmak için hangi parametreler ayarlanmalıdır?"
            ),
            "key_terms":  ["clk_wiz", "CLKOUT1", "CLKOUT2",
                           "CLKOUT1_REQUESTED_OUT_FREQ", "50", "25",
                           "CLK_IN1", "Clocking Wizard"],
            "key_values": ["clk_wiz", "50", "25"],
            "note": "PG065: CONFIG.CLKOUT1_REQUESTED_OUT_FREQ 50 CONFIG.CLKOUT2_REQUESTED_OUT_FREQ 25 CONFIG.USE_LOCKED 1",
        },
    ],

    # ─── HOW Synthesis — Sentez, Implementation, Bitstream ──────────────
    "how_synthesis": [
        {
            "id": "HS-01",
            "project": "general",
            "question": (
                "Vivado'da sentezi ve implementasyonu TCL ile nasıl başlatırım? "
                "launch_runs, wait_on_run ve open_run komutlarının doğru sırası "
                "ve parametreleri nelerdir?"
            ),
            "key_terms":  ["launch_runs", "wait_on_run", "open_run",
                           "synth_1", "impl_1", "jobs"],
            "key_values": ["launch_runs", "wait_on_run", "synth_1"],
            "note": "UG894: launch_runs synth_1 -jobs 4 → wait_on_run synth_1 → launch_runs impl_1 → wait_on_run impl_1",
        },
        {
            "id": "HS-02",
            "project": "general",
            "question": (
                "Vivado'da bitstream dosyası oluşturduktan sonra FPGA'ya "
                "programlamak için hangi adımlar gereklidir? "
                "open_hw_manager ve program_hw_devices komutlarını açıklayın."
            ),
            "key_terms":  ["write_bitstream", "open_hw_manager",
                           "open_hw_target", "program_hw_devices",
                           "get_hw_devices", "bitstream"],
            "key_values": ["write_bitstream", "open_hw_manager", "program_hw_devices"],
            "note": "UG908: write_bitstream → open_hw_manager → connect_hw_server → open_hw_target → program_hw_devices",
        },
        {
            "id": "HS-03",
            "project": "axi_gpio_example",
            "question": (
                "axi_gpio_example projesini Vivado'da sentezlemek için hangi "
                "TCL komutlarını çalıştırmalıyım? "
                "Projeyi açmadan doğrudan non-project modda çalışmanın adımları "
                "nelerdir?"
            ),
            "key_terms":  ["read_verilog", "read_xdc", "synth_design",
                           "opt_design", "place_design", "route_design",
                           "write_bitstream"],
            "key_values": ["synth_design", "place_design", "write_bitstream"],
            "note": "UG901/UG904: read_verilog → read_xdc → synth_design -top → opt_design → place_design → route_design → write_bitstream",
        },
        {
            "id": "HS-04",
            "project": "general",
            "question": (
                "Vivado sentez sonuçlarında 'timing not met' hatası alındığında "
                "hangi adımlarla analiz yapılır? report_timing_summary ve "
                "report_clock_interaction komutları nasıl kullanılır?"
            ),
            "key_terms":  ["report_timing_summary", "report_clock_interaction",
                           "timing", "setup", "hold", "WNS", "WHS"],
            "key_values": ["report_timing_summary", "timing"],
            "note": "UG903/UG904: report_timing_summary -delay_type max_min → WNS/WHS analizi → set_multicycle_path / false_path düzeltmeleri",
        },
    ],

    # ─── HOW Constraints — XDC dosyası oluşturma ─────────────────────────
    "how_constraints": [
        {
            "id": "HC-01",
            "project": "general",
            "question": (
                "Vivado'da bir XDC kısıt dosyasında FPGA pinlerine I/O sinyali "
                "atamak için hangi komut kullanılır? "
                "PACKAGE_PIN, IOSTANDARD ve SLEW rate nasıl ayarlanır?"
            ),
            "key_terms":  ["set_property", "PACKAGE_PIN", "IOSTANDARD",
                           "SLEW", "get_ports", "LVCMOS33"],
            "key_values": ["set_property", "PACKAGE_PIN", "IOSTANDARD"],
            "note": "UG903: set_property PACKAGE_PIN X [get_ports sig] → set_property IOSTANDARD LVCMOS33 [get_ports sig]",
        },
        {
            "id": "HC-02",
            "project": "general",
            "question": (
                "Vivado'da bir clock sinyali için timing constraint nasıl "
                "tanımlanır? create_clock komutunun parametreleri ve "
                "100 MHz için period değeri nedir?"
            ),
            "key_terms":  ["create_clock", "period", "10", "get_ports",
                           "waveform", "100 MHz", "constraint"],
            "key_values": ["create_clock", "period", "10"],
            "note": "UG903: create_clock -period 10.000 -name sys_clk [get_ports clk] — 100MHz = 10ns period",
        },
        {
            "id": "HC-03",
            "project": "nexys_a7_dma_audio",
            "question": (
                "nexys_a7_dma_audio projesindeki Nexys-A7-100T-Master.xdc "
                "dosyasında 100 MHz sistem saati hangi FPGA pinine bağlıdır? "
                "Bu pin için IOSTANDARD nedir?"
            ),
            "key_terms":  ["E3", "CLK100MHZ", "LVCMOS33", "PACKAGE_PIN",
                           "create_clock", "100"],
            "key_values": ["E3", "CLK100MHZ", "LVCMOS33"],
            "note": "Master.xdc: PACKAGE_PIN E3 get_ports CLK100MHZ, IOSTANDARD LVCMOS33, create_clock -period 10.000",
        },
    ],

    # ─── HOW IP Config — IP parametrelerini TCL ile ayarlama ─────────────
    "how_ip_config": [
        {
            "id": "HIC-01",
            "project": "general",
            "question": (
                "Vivado IP Integrator'da bir IP bloğunun parametrelerini TCL ile "
                "nasıl ayarlarım? set_property CONFIG ile "
                "AXI DMA'nın scatter-gather modunu etkinleştirme örneği verin."
            ),
            "key_terms":  ["set_property", "CONFIG", "axi_dma",
                           "c_include_sg", "get_bd_cells", "1"],
            "key_values": ["set_property", "CONFIG", "c_include_sg"],
            "note": "UG994: set_property -dict [list CONFIG.c_include_sg {1}] [get_bd_cells axi_dma_0]",
        },
        {
            "id": "HIC-02",
            "project": "nexys_a7_dma_audio",
            "question": (
                "nexys_a7_dma_audio projesinde MIG 7 Series IP'sinin "
                "temel konfigürasyonu nasıl yapılmış? "
                "DDR2 için kullanılan clock period ve veri yolu genişliği nedir?"
            ),
            "key_terms":  ["mig_7series", "DDR2", "clock_period",
                           "3077", "16", "DATA_WIDTH", "MIG"],
            "key_values": ["mig_7series", "DDR2", "3077"],
            "note": "design_1.tcl: mig_7series_0 CONFIG — DDR2, clock_period=3077ps, DATA_WIDTH=16",
        },
        {
            "id": "HIC-03",
            "project": "general",
            "question": (
                "Vivado'da AXI Interconnect IP'sini block design'a eklerken "
                "master ve slave port sayısını nasıl belirlerim? "
                "NUM_MI ve NUM_SI parametreleri ne anlama gelir?"
            ),
            "key_terms":  ["axi_interconnect", "NUM_MI", "NUM_SI",
                           "master", "slave", "AXI Interconnect"],
            "key_values": ["axi_interconnect", "NUM_MI", "NUM_SI"],
            "note": "PG059: CONFIG.NUM_MI=1 (master count), CONFIG.NUM_SI=N (slave/peripheral count)",
        },
    ],

    # ─── WHAT Concepts — Kavramsal (UG kaynaklı) ─────────────────────────
    "what_concepts": [
        {
            "id": "WC-01",
            "project": "general",
            "question": (
                "Vivado IP Integrator'da 'Block Automation' özelliği ne işe yarar? "
                "MicroBlaze için bu otomasyon hangi bileşenleri otomatik olarak ekler?"
            ),
            "key_terms":  ["Block Automation", "MicroBlaze", "LMB",
                           "BRAM", "MDM", "local memory", "debug"],
            "key_values": ["Block Automation", "MicroBlaze", "LMB"],
            "note": "UG994: Block Automation ekler: LMB BRAM controller, LMB v1.0, MDM (debug), proc_sys_reset",
        },
        {
            "id": "WC-02",
            "project": "general",
            "question": (
                "Vivado'da AXI4, AXI4-Lite ve AXI4-Stream protokolleri arasındaki "
                "fark nedir? Hangi durumda hangisi tercih edilir?"
            ),
            "key_terms":  ["AXI4", "AXI4-Lite", "AXI4-Stream",
                           "burst", "throughput", "register", "streaming"],
            "key_values": ["AXI4", "AXI4-Lite", "AXI4-Stream"],
            "note": "PG059/UG994: AXI4=burst/memory, AXI4-Lite=single register, AXI4-Stream=unidirectional data flow (no address)",
        },
        {
            "id": "WC-03",
            "project": "general",
            "question": (
                "Vivado SmartConnect ve AXI Interconnect IP blokları arasındaki "
                "temel fark nedir? Yeni tasarımlarda hangisi önerilir?"
            ),
            "key_terms":  ["SmartConnect", "AXI Interconnect",
                           "PG247", "PG059", "performans", "newer"],
            "key_values": ["SmartConnect", "AXI Interconnect"],
            "note": "PG247/PG059: SmartConnect=newer/automatic width/clock conversion, AXI Interconnect=legacy manual config",
        },
    ],

    # ─── Regression TRACE — Mevcut TRACE testlerinden seçim ─────────────
    "regression_trace": [
        {
            "id": "RT-01",
            "project": "nexys_a7_dma_audio",
            "question": (
                "DMA Audio projesinde ses verisinin MIG 7 Series DDR3 belleğinden "
                "çıkıp AXI DMA üzerinden AXI-Stream'e dönüşerek ses çıkış modülüne "
                "ulaşmasına kadar geçen bileşenlerin zincirini açıklayın."
            ),
            "key_terms":  ["mig_7series", "axi_dma", "axis", "fifo2audpwm",
                           "AXI-Stream", "DMA", "ses"],
            "key_values": ["mig_7series", "axi_dma", "fifo2audpwm"],
            "note": "Graph TRACE: mig_7series_0 → axi_dma_0 → axis2fifo → fifo2audpwm_0",
            "expected_route": "Trace",
        },
        {
            "id": "RT-02",
            "project": "axi_gpio_example",
            "question": (
                "axi_gpio_example projesinde MicroBlaze işlemcisinden GPIO "
                "LED'lerine veri yazma zincirini açıklayın: "
                "microblaze_0, AXI Interconnect ve axi_gpio_0 rollerini belirtin."
            ),
            "key_terms":  ["microblaze_0", "axi_interconnect", "axi_gpio_0",
                           "GPIO", "LED", "AXI", "gpio_io_o"],
            "key_values": ["microblaze_0", "axi_gpio_0"],
            "note": "Graph TRACE: microblaze_0 → microblaze_0_axi_periph → axi_gpio_0 → gpio_io_o",
            "expected_route": "Trace",
        },
        {
            "id": "RT-03",
            "project": "nexys_a7_dma_audio",
            "question": (
                "nexys_a7_dma_audio projesinde clk_wiz_0 ve proc_sys_reset_0 "
                "bileşenleri hangi gereksinimi karşılamaktadır? "
                "Bu bileşenler arasındaki CONNECTS_TO ilişkisini açıklayın."
            ),
            "key_terms":  ["clk_wiz_0", "proc_sys_reset_0", "CONNECTS_TO",
                           "clock", "reset", "saat"],
            "key_values": ["clk_wiz_0", "proc_sys_reset_0"],
            "note": "Graph TRACE: clk_wiz_0 CONNECTS_TO proc_sys_reset_0 (slowest_sync_clk)",
            "expected_route": "Trace",
        },
    ],

    # ─── Trap v5 — Workflow tuzakları ─────────────────────────────────────
    "trap_v5": [
        {
            "id": "TR5-01",
            "project": "general",
            "question": (
                "Vivado 2018.2'de 'Project Mode' yerine 'Non-Project Mode' "
                "kullanılırsa .xpr proje dosyası otomatik olarak oluşturulur mu? "
                "run_all.tcl scripti non-project modda bir .xpr dosyası üretir mi?"
            ),
            "expected": "NOT_IN_DB",
            "hallucination_keywords": [
                "evet .xpr oluşturulur", ".xpr otomatik", "xpr dosyası üretilir",
                "non-project modda xpr", "xpr dosyası oluşturulur",
            ],
            "note": "Non-project mode'da .xpr oluşmaz — sadece in-memory. .xpr yalnızca project mode'da.",
        },
        {
            "id": "TR5-02",
            "project": "general",
            "question": (
                "Vivado IP Integrator'da oluşturulan block design, sentez öncesi "
                "HDL wrapper olmadan doğrudan top-level module olarak kullanılabilir mi? "
                "Wrapper oluşturmadan sentez başarılı olur mu?"
            ),
            "expected": "NOT_IN_DB",
            "hallucination_keywords": [
                "wrapper olmadan sentez yapılabilir", "doğrudan top-level kullanılabilir",
                "wrapper gerekmez", "wrapper olmaksızın sentez",
                "bd dosyası doğrudan kullanılabilir",
            ],
            "note": "Block design'ın HDL wrapper'a ihtiyacı var — .bd doğrudan sentezlenemez, make_wrapper zorunlu.",
        },
        {
            "id": "TR5-03",
            "project": "nexys_a7_dma_audio",
            "question": (
                "nexys_a7_dma_audio projesinde AXI DMA'nın Simple DMA modunda "
                "çalışacak şekilde konfigure edildiğini doğrulayan kaynak kodu var mı? "
                "c_include_sg parametresinin değeri nedir?"
            ),
            "expected": "NOT_IN_DB",
            "hallucination_keywords": [
                "simple dma modunda", "c_include_sg {0}", "sg devre dışı",
                "simple mode etkin", "c_include_sg = 0", "c_include_sg değeri 0",
            ],
            "note": "Gerçekte c_include_sg=1 (Scatter-Gather aktif). Simple DMA değil SG DMA kullanılıyor.",
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORİ META
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_INFO_V5 = {
    "how_new_project":  ("HOW New Project  (IP Integrator sıfırdan proje)",  0.25),
    "how_synthesis":    ("HOW Synthesis    (sentez/impl/bitstream workflow)", 0.20),
    "how_constraints":  ("HOW Constraints  (XDC, timing, pin atama)",        0.15),
    "how_ip_config":    ("HOW IP Config    (IP parametre ayarlama)",          0.15),
    "what_concepts":    ("WHAT Concepts    (kavramsal UG sorguları)",         0.10),
    "regression_trace": ("Regression TRACE (mevcut TRACE testleri)",          0.10),
    "trap_v5":          ("Trap v5          (workflow tuzakları)",              0.05),
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
    vs  = VectorStoreV2(persist_directory=str(_ROOT / "db/chroma_v2"), threshold=0.35)
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
    doc_chunks  = getattr(qr, "doc_chunks", [])
    doc_ids     = list({c.get("doc_id", "") for c in doc_chunks} if doc_chunks else set())

    result = {
        "question":     question[:80],
        "query_type":   qt.value,
        "vector_hits":  len(qr.vector_hits),
        "graph_nodes":  len(qr.graph_nodes),
        "graph_edges":  len(qr.graph_edges),
        "source_chunks": len(sc_chunks),
        "doc_chunks":   len(doc_chunks),
        "chunk_files":  [Path(f).name for f in chunk_files if f],
        "doc_ids":      doc_ids[:5],
        "confidence":   gr.overall_confidence,
        "warnings":     gr.warnings,
        "answer":       answer,
        "elapsed_s":    round(time.time() - t0, 2),
    }
    if verbose:
        print(f"\n    Q: {question[:100]}")
        print(f"    [Type={qt.value} | nodes={len(qr.graph_nodes)} | "
              f"edges={len(qr.graph_edges)} | chunks={len(sc_chunks)} | "
              f"doc_chunks={len(doc_chunks)}]")
        if doc_ids:
            print(f"    Doc IDs: {doc_ids[:4]}")
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
    label, _ = CATEGORY_INFO_V5[cat_key]
    print(hdr(f"KATEGORİ: {label}"))

    results = []
    for q in questions:
        is_trap = q.get("expected") == "NOT_IN_DB"
        print(f"\n  {B}{q['id']}{RST}  [{q['project']}]")

        r = ask(q["question"], router, gate, llm, system_prompt, verbose)

        # Regression TRACE: route doğruluğunu da kontrol et
        expected_route = q.get("expected_route", "")
        route_ok = (not expected_route) or (r["query_type"].lower() == expected_route.lower())
        if expected_route and not verbose:
            route_sym = ok("Route OK") if route_ok else warn(f"Route={r['query_type']} (beklenen {expected_route})")
            print(f"    {route_sym}")

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
                "doc_chunks": r["doc_chunks"],
                "doc_ids": r["doc_ids"],
                "chunk_files": r["chunk_files"],
                "query_type": r["query_type"],
                "route_ok": route_ok,
                "answer_snippet": r["answer"][:300],
                "ground_truth": q.get("note", ""),
            })
        else:
            score, term_hits, val_hits = score_real_question(q, r["answer"])
            sym = ok if score >= 0.8 else (warn if score >= 0.5 else err)
            print(f"    {sym(f'Skor={score:.2f}')} | terms={term_hits} | vals={val_hits}")
            print(f"    Source: {r['source_chunks']} chunk | DocStore: {r['doc_chunks']} chunk")
            if r["doc_ids"]:
                print(f"    Docs: {r['doc_ids'][:3]}")
            print(f"    Files: {r['chunk_files'][:2]}")
            results.append({
                "id": q["id"], "category": cat_key,
                "project": q["project"], "type": "real",
                "score": score,
                "term_hits": term_hits,
                "term_misses": [t for t in q["key_terms"] if t not in term_hits],
                "val_hits": val_hits,
                "val_misses": [v for v in q["key_values"] if v not in val_hits],
                "source_chunks": r["source_chunks"],
                "doc_chunks": r["doc_chunks"],
                "doc_ids": r["doc_ids"],
                "chunk_files": r["chunk_files"],
                "query_type": r["query_type"],
                "route_ok": route_ok,
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
    print(f"{B}  BLIND BENCHMARK v5 — ÖZET RAPOR{RST}")
    print(f"{B}{'═'*68}{RST}")

    total_weighted = 0.0
    for cr in cat_results:
        cat_key = cr["category"]
        _, weight = CATEGORY_INFO_V5.get(cat_key, ("?", 0.10))
        s   = cr["score"]
        bar = "█" * int(s * 20) + "░" * (20 - int(s * 20))
        total_weighted += s * weight
        print(f"  {cr['label']:50s} {bar} {s:.3f} [{grade(s)}] (w={weight:.0%})")

    print(f"\n  {'─'*68}")
    print(f"  AĞIRLIKLI TOPLAM SKOR : {total_weighted:.3f} → {grade(total_weighted)}")
    print(f"  {'─'*68}")

    all_q  = [q for cr in cat_results for q in cr["questions"]]
    n_total = len(all_q)
    n_pass  = sum(1 for q in all_q if q["score"] >= 0.80)
    n_fail  = sum(1 for q in all_q if q["score"] < 0.50)
    n_trap  = sum(1 for q in all_q if q["type"] == "trap")
    n_trap_pass = sum(1 for q in all_q if q["type"] == "trap" and q["score"] >= 0.80)
    n_how_qs = [q for cr in cat_results
                if cr["category"].startswith("how")
                for q in cr["questions"]]
    n_how_pass = sum(1 for q in n_how_qs if q["score"] >= 0.80)

    print(f"\n  Toplam soru          : {n_total}")
    print(f"  Geçen (≥0.80)        : {n_pass}/{n_total}")
    print(f"  Başarısız (<0.50)    : {n_fail}/{n_total}")
    print(f"  Trap geçen           : {n_trap_pass}/{n_trap}")
    print(f"  HOW sorular geçen    : {n_how_pass}/{len(n_how_qs)}")

    # Route doğruluğu (regression_trace için)
    trace_qs = [q for cr in cat_results
                if cr["category"] == "regression_trace"
                for q in cr["questions"]]
    n_route_ok = sum(1 for q in trace_qs if q.get("route_ok", True))
    if trace_qs:
        print(f"  TRACE route doğru    : {n_route_ok}/{len(trace_qs)}")

    worst = sorted(all_q, key=lambda x: x["score"])[:4]
    print(f"\n  En düşük 4 soru:")
    for q in worst:
        misses = q.get("term_misses", []) + q.get("val_misses", [])
        print(f"    {q['id']}: skor={q['score']:.2f} | eksik={misses[:4]}")

    print(f"{B}{'═'*68}{RST}\n")
    return round(total_weighted, 3)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="FPGA RAG v2 Blind Benchmark v5 (0'dan proje oluşturma / Vivado workflow)"
    )
    parser.add_argument("--save",     action="store_true", help="JSON raporu kaydet")
    parser.add_argument("--verbose",  action="store_true", help="Tam cevaplar + doc IDs göster")
    parser.add_argument("--category", type=str, default="",
                        help="Belirli kategori: "
                             "how_new_project|how_synthesis|how_constraints|"
                             "how_ip_config|what_concepts|regression_trace|trap_v5")
    args = parser.parse_args()

    n_total = sum(len(v) for v in BLIND_QUESTIONS_V5.values())
    print(f"\n{B}{'═'*68}")
    print(f"  FPGA RAG v2 — Blind Benchmark v5 (0'dan Proje Oluşturma)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*68}{RST}")
    print(f"\n  Kapsam  : {n_total} soru × 7 kategori")
    print(f"  Odak    : HOW workflow sorguları (yeni proje, sentez, constraints)")
    print(f"  Yeni    : pg059/pg020/pg062/ug898 indexli, routing fix uygulandı")

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

    for cat_key, questions in BLIND_QUESTIONS_V5.items():
        if only_cat and cat_key != only_cat:
            continue
        cr = run_category(cat_key, questions, router, gate, llm, system_prompt, args.verbose)
        cat_results.append(cr)

    elapsed = round(time.time() - t_start, 1)
    final_score = print_summary(cat_results)
    print(f"  Toplam süre: {elapsed}s")

    if args.save:
        out_path = _ROOT / "blind_benchmark_v5_report.json"
        report = {
            "timestamp":     datetime.now().isoformat(),
            "version":       "v5",
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
