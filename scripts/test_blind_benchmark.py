#!/usr/bin/env python3
"""
FPGA RAG v2 — Blind Benchmark Test
=====================================
Sistemin hiç görmediği sorularda başarısını ölçer.

Bu sorular:
  - test_v2_20q.py ve test_robustness.py'den TAMAMEN BAĞIMSIZDIR
  - key_terms ve key_values doğrudan kaynak koddan alınmıştır
  - LLM ve sistem hiçbir şekilde bu soruları optimize etmemiştir

5 Kategori × Sorular:
  RTL/Verilog  (6 soru) — axis2fifo, fifo2audpwm, tone_generator
  C Firmware   (4 soru) — helloworld.c DMA/Audio
  TCL/BD       (4 soru) — create_minimal_microblaze.tcl
  XDC          (3 soru) — nexys_video.xdc pin/timing
  Trap         (3 soru) — DB'de olmayan bilgiler

Çalıştırma:
    source .venv/bin/activate
    python scripts/test_blind_benchmark.py
    python scripts/test_blind_benchmark.py --save
    python scripts/test_blind_benchmark.py --verbose
    python scripts/test_blind_benchmark.py --category rtl
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
# SORU KATEGORİLERİ
# ─────────────────────────────────────────────────────────────────────────────

# Ground truth: doğrudan kaynak koddan alınmış, sistem tarafından görülmemiş

BLIND_QUESTIONS = {

    # ── RTL / Verilog ────────────────────────────────────────────────────────
    "rtl": [
        {
            "id": "BL-RTL-01",
            "project": "PROJECT-A",
            "question": (
                "DMA Audio projesindeki axis2fifo modülünde fifo_wr_data portuna "
                "aktarılan veri, axis_tdata sinyalinin hangi bit aralığından alınmaktadır? "
                "axis2fifo.v kaynak koduna göre cevap verin."
            ),
            "ground_truth": "assign fifo_wr_data = axis_tdata[15:0]",
            "key_terms":  ["fifo_wr_data", "axis_tdata", "15:0", "16"],
            "key_values": ["15:0"],
            "note": "axis2fifo.v satır 35: assign fifo_wr_data = axis_tdata[15:0]",
        },
        {
            "id": "BL-RTL-02",
            "project": "PROJECT-A",
            "question": (
                "axis2fifo modülünde axis_tready sinyali nasıl üretilmektedir? "
                "Hangi koşulda '1' olur? axis2fifo.v'deki assign ifadesini açıklayın."
            ),
            "ground_truth": "assign axis_tready = ~fifo_full — FIFO dolu değilken 1",
            "key_terms":  ["axis_tready", "fifo_full", "~", "dolu değil", "not"],
            "key_values": ["fifo_full"],
            "note": "axis2fifo.v satır 33: assign axis_tready = ~fifo_full",
        },
        {
            "id": "BL-RTL-03",
            "project": "PROJECT-A",
            "question": (
                "fifo2audpwm modülü 32 bitlik FIFO verisini kaç ayrı duty cycle "
                "register'ına dağıtır? Her register kaç bitlik veriyi alır? "
                "Verilog kaynak koduna göre bit dilimlerini açıklayın."
            ),
            "ground_truth": "4 adet duty[0..3], her biri 8 bit: [7:0],[15:8],[23:16],[31:24]",
            "key_terms":  ["duty", "4", "7:0", "15:8", "23:16", "31:24"],
            "key_values": ["4"],
            "note": "fifo2audpwm.v satır 22, 29-32: reg [DATA_WIDTH:0] duty [3:0]",
        },
        {
            "id": "BL-RTL-04",
            "project": "PROJECT-A",
            "question": (
                "fifo2audpwm modülünde count register'ının bit genişliği nedir? "
                "DATA_WIDTH parametresi 8 olarak alındığında kaç bitlik bir sayaç "
                "elde edilir? fifo2audpwm.v'deki tanımı açıklayın."
            ),
            "ground_truth": "reg [DATA_WIDTH+1:0] count → [9:0] → 10 bit",
            "key_terms":  ["10", "count", "DATA_WIDTH", "9:0"],
            "key_values": ["10"],
            "note": "fifo2audpwm.v satır 21: reg [DATA_WIDTH+1:0] count = 0 → DATA_WIDTH=8 → [9:0] = 10 bit",
        },
        {
            "id": "BL-RTL-05",
            "project": "PROJECT-A",
            "question": (
                "tone_generator.v'de localparam INCREMENT değeri nedir (hexadecimal)? "
                "Bu değer hangi ses frekansına (Hz) ve örnek örnekleme frekansına (Hz) karşılık "
                "gelmektedir? TONE_FREQ ve AUD_SAMPLE_FREQ parametrelerini de belirtin."
            ),
            "ground_truth": "INCREMENT = 32'h00B22D0E, TONE_FREQ=261 Hz, AUD_SAMPLE_FREQ=96000 Hz",
            "key_terms":  ["0x00B22D0E", "00B22D0E", "261", "96000", "INCREMENT"],
            "key_values": ["00B22D0E", "261", "96000"],
            "note": "tone_generator.v satır 50: localparam INCREMENT = 32'h00B22D0E, param 261 Hz / 96 kHz",
        },
        {
            "id": "BL-RTL-06",
            "project": "PROJECT-A",
            "question": (
                "tone_generator modülünde axis_tdata sinyali nasıl üretilmektedir? "
                "32 bitlik duty (faz akümülatörü) register'ının hangi bitleri "
                "AXI veri çıkışına aktarılmaktadır? Verilog satırını açıklayın."
            ),
            "ground_truth": "duty[ACCUMULATOR_DEPTH-1:ACCUMULATOR_DEPTH-16] = duty[31:16] üst 16 bit",
            "key_terms":  ["duty", "31:16", "üst 16", "axis_tdata", "accumulator"],
            "key_values": ["31:16"],
            "note": "tone_generator.v satır 59: assign axis_tdata = {{16{1'b0}}, duty[31:16]}",
        },
    ],

    # ── C Firmware ───────────────────────────────────────────────────────────
    "firmware": [
        {
            "id": "BL-FW-01",
            "project": "PROJECT-A",
            "question": (
                "helloworld.c'de MEM_BASE_ADDR sabitinin değeri nedir? "
                "DDR_BASE_ADDR ile arasındaki offset (byte cinsinden hex) nedir? "
                "#define tanımını açıklayın."
            ),
            "ground_truth": "MEM_BASE_ADDR = DDR_BASE_ADDR + 0x1000000 (16 MB offset)",
            "key_terms":  ["0x1000000", "MEM_BASE_ADDR", "DDR_BASE_ADDR", "16"],
            "key_values": ["0x1000000"],
            "note": "helloworld.c satır 16: #define MEM_BASE_ADDR (DDR_BASE_ADDR + 0x1000000)",
        },
        {
            "id": "BL-FW-02",
            "project": "PROJECT-A",
            "question": (
                "helloworld.c'deki dma_sw_tone_gen() fonksiyonunda yazılımsal "
                "tın üretimi için kullanılan INCREMENT sabiti nedir? "
                "Akümülatör sonucunun buffer'a yazılırken bit kaydırma (shift) "
                "miktarı kaçtır? Kaynak kod satırlarını açıklayın."
            ),
            "ground_truth": "accum += 0x00B22D0E; buffer[i] = accum>>24 (üst 8 bit)",
            "key_terms":  ["0x00B22D0E", "accum", ">>24", "24", "dma_sw_tone_gen"],
            "key_values": ["0x00B22D0E", "24"],
            "note": "helloworld.c satır 292-293: accum += 0x00B22D0E; ((u8*)buffer)[i] = accum>>24",
        },
        {
            "id": "BL-FW-03",
            "project": "PROJECT-A",
            "question": (
                "init_dma() fonksiyonu DMA başlatma sonrası konsola hangi "
                "teknik değeri yazdırır? xil_printf satırını ve yazdırılan "
                "struct alanını açıklayın."
            ),
            "ground_truth": "TxBdRing.MaxTransferLen — xil_printf MaxTransferLen",
            "key_terms":  ["MaxTransferLen", "TxBdRing", "xil_printf", "init_dma"],
            "key_values": ["MaxTransferLen"],
            "note": "helloworld.c satır 100: xil_printf('Note: MaxTransferLen=%d', TxBdRing.MaxTransferLen)",
        },
        {
            "id": "BL-FW-04",
            "project": "PROJECT-A",
            "question": (
                "helloworld.c'deki GpioIn_Data struct'ında switch_pe ve switch_ne "
                "field'larının C veri türleri nedir? Struct tanımını açıklayın."
            ),
            "ground_truth": "switch_pe: u16, switch_ne: u16",
            "key_terms":  ["u16", "switch_pe", "switch_ne", "GpioIn_Data"],
            "key_values": ["u16"],
            "note": "helloworld.c satır 53-54: u16 switch_pe; u16 switch_ne;",
        },
    ],

    # ── TCL / Block Design ───────────────────────────────────────────────────
    "tcl": [
        {
            "id": "BL-TCL-01",
            "project": "PROJECT-B",
            "question": (
                "axi_gpio_example projesinde create_minimal_microblaze.tcl'de "
                "MicroBlaze IP'sinin CONFIG.C_D_AXI parametresi hangi değere "
                "ayarlanmıştır? Bu konfigürasyon MicroBlaze mimarisini nasıl etkiler?"
            ),
            "ground_truth": "CONFIG.C_D_AXI {0} — AXI veri bus devre dışı, sadece LMB kullanılıyor",
            "key_terms":  ["C_D_AXI", "0", "devre dışı", "LMB"],
            "key_values": ["0"],
            "note": "create_minimal_microblaze.tcl satır 36: CONFIG.C_D_AXI {0}",
        },
        {
            "id": "BL-TCL-02",
            "project": "PROJECT-B",
            "question": (
                "create_minimal_microblaze.tcl'deki apply_bd_automation komutu "
                "MicroBlaze için kaç KB yerel bellek (LMB BRAM) tahsis etmektedir? "
                "local_mem parametresini açıklayın."
            ),
            "ground_truth": "local_mem 8KB — 8 KB LMB BRAM",
            "key_terms":  ["8KB", "8", "local_mem", "LMB", "BRAM"],
            "key_values": ["8"],
            "note": "create_minimal_microblaze.tcl satır 70: local_mem \"8KB\"",
        },
        {
            "id": "BL-TCL-03",
            "project": "PROJECT-B",
            "question": (
                "create_minimal_microblaze.tcl'de clk_wiz_0 IP'si için "
                "PRIM_IN_FREQ ve CLKOUT1_REQUESTED_OUT_FREQ değerleri nedir? "
                "Saat tasarımını açıklayın."
            ),
            "ground_truth": "PRIM_IN_FREQ {100}, CLKOUT1_REQUESTED_OUT_FREQ {100} — 100 MHz giriş/çıkış",
            "key_terms":  ["100", "PRIM_IN_FREQ", "CLKOUT1_REQUESTED", "clk_wiz"],
            "key_values": ["100"],
            "note": "create_minimal_microblaze.tcl satır 53-54: PRIM_IN_FREQ {100} CLKOUT1_REQUESTED_OUT_FREQ {100}",
        },
        {
            "id": "BL-TCL-04",
            "project": "PROJECT-B",
            "question": (
                "create_minimal_microblaze.tcl'de resetn sinyali hangi "
                "PACKAGE_PIN'e atanmıştır? IOSTANDARD değeri nedir?"
            ),
            "ground_truth": "PACKAGE_PIN G4, IOSTANDARD LVCMOS15",
            "key_terms":  ["G4", "LVCMOS15", "resetn", "reset"],
            "key_values": ["G4", "LVCMOS15"],
            "note": "create_minimal_microblaze.tcl satır 123: PACKAGE_PIN G4 IOSTANDARD LVCMOS15",
        },
    ],

    # ── XDC / Constraints ────────────────────────────────────────────────────
    "xdc": [
        {
            "id": "BL-XDC-01",
            "project": "PROJECT-B",
            "question": (
                "axi_gpio_example projesinin nexys_video.xdc kısıt dosyasında "
                "leds[0] portu hangi PACKAGE_PIN'e ve hangi IOSTANDARD'a "
                "atanmıştır?"
            ),
            "ground_truth": "PACKAGE_PIN T14, IOSTANDARD LVCMOS25",
            "key_terms":  ["T14", "LVCMOS25", "leds"],
            "key_values": ["T14", "LVCMOS25"],
            "note": "nexys_video.xdc satır 11: PACKAGE_PIN T14 IOSTANDARD LVCMOS25 leds[0]",
        },
        {
            "id": "BL-XDC-02",
            "project": "PROJECT-B",
            "question": (
                "nexys_video.xdc'de switches portları için kullanılan IOSTANDARD nedir? "
                "leds portları için kullanılan IOSTANDARD'dan farklı mı? "
                "switches[0]'ın pin atamasını da belirtin."
            ),
            "ground_truth": "switches → LVCMOS12, leds → LVCMOS25, switches[0] = E22",
            "key_terms":  ["LVCMOS12", "LVCMOS25", "E22", "switches", "leds"],
            "key_values": ["LVCMOS12", "E22"],
            "note": "nexys_video.xdc satır 21: PACKAGE_PIN E22 IOSTANDARD LVCMOS12 switches[0]",
        },
        {
            "id": "BL-XDC-03",
            "project": "PROJECT-B",
            "question": (
                "nexys_video.xdc'de sistem saati (sys_clk) için create_clock "
                "kısıtında tanımlanan periyot değeri nedir (nanosaniye)? "
                "Waveform tanımını da açıklayın."
            ),
            "ground_truth": "period 10.000 ns (100 MHz), waveform {0.000 5.000}",
            "key_terms":  ["10.000", "10", "sys_clk", "waveform", "5.000", "100"],
            "key_values": ["10.000"],
            "note": "nexys_video.xdc satır 5: create_clock -period 10.000 -name sys_clk -waveform {0.000 5.000}",
        },
    ],

    # ── Trap (DB'de olmayan bilgiler) ────────────────────────────────────────
    "trap": [
        {
            "id": "BL-TRAP-01",
            "project": "PROJECT-A",
            "question": (
                "DMA Audio projesinin helloworld.c SDK uygulaması FreeRTOS veya "
                "başka bir RTOS (Xilkernel, ThreadX vb.) üzerinde mi çalışmaktadır? "
                "Hangi task'lar tanımlanmıştır ve task scheduling mekanizması "
                "nasıl konfigüre edilmiştir?"
            ),
            "expected": "NOT_IN_DB",
            "note": "helloworld.c bare-metal uygulama — FreeRTOS/RTOS kullanmıyor",
            "hallucination_keywords": [
                "freertos", "xilkernel", "xtaskcreate", "vtaskdelay",
                "semaphore", "mutex", "scheduler", "rtos task",
            ],
        },
        {
            "id": "BL-TRAP-02",
            "project": "PROJECT-A",
            "question": (
                "DMA Audio projesinde fifo2audpwm modülü için bir simulation "
                "testbench dosyası (fifo2audpwm_tb.v veya benzer) bulunmakta mıdır? "
                "Eğer varsa simülasyon süresi ve uygulanan test vektörleri nelerdir?"
            ),
            "expected": "NOT_IN_DB",
            "note": "Projede fifo2audpwm için testbench dosyası bulunmuyor",
            "hallucination_keywords": [
                "fifo2audpwm_tb", "tb.v", "testbench", "test_fifo",
                "initial begin", "stimulus", "sim_time", "#100", "#200",
            ],
        },
        {
            "id": "BL-TRAP-03",
            "project": "PROJECT-B",
            "question": (
                "axi_gpio_example projesinde AXI GPIO (axi_gpio_0) için interrupt "
                "desteği (IP2INTC_IRPT) add_axi_gpio.tcl'de etkinleştirilmiş midir? "
                "Interrupt öncelik değeri ve INTC bağlantısı nasıl yapılandırılmıştır?"
            ),
            "expected": "NOT_IN_DB",
            "note": "axi_gpio_0 interrupt configure edilmemiş — AXI INTC yok bu projede",
            "hallucination_keywords": [
                "ip2intc_irpt", "c_interrupt_present", "interrupt priority",
                "irq_f2p", "intc", "xlconcat", "enable {1}",
            ],
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# SİSTEM YÜKLEME
# ─────────────────────────────────────────────────────────────────────────────

def load_system():
    from rag_v2.graph_store import GraphStore
    from rag_v2.vector_store_v2 import VectorStoreV2
    from rag_v2.query_router import QueryRouter
    from rag_v2.hallucination_gate import HallucinationGate
    from rag_v2.source_chunk_store import SourceChunkStore

    gs = GraphStore(persist_path=str(_ROOT / "db/graph/fpga_rag_v2_graph.json"))
    vs = VectorStoreV2(persist_directory=str(_ROOT / "db/chroma_graph_nodes"), threshold=0.35)
    sc = SourceChunkStore(persist_directory=str(_ROOT / "db/chroma_source_chunks"))
    router = QueryRouter(gs, vs, n_vector_results=6, source_chunk_store=sc, n_source_results=10)
    gate   = HallucinationGate(gs)
    return gs, vs, sc, router, gate


def get_llm():
    from rag.llm_factory import get_llm as _get_llm
    return _get_llm("claude-sonnet-4-6")


def ask(question: str, router, gate, llm, system_prompt: str, verbose=False) -> Dict:
    from rag_v2.response_builder import build_llm_context
    from rag_v2.grounding_checker import GroundingChecker

    t0 = time.time()
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

    chunk_files = list({c.get("file_path","") for c in sc_chunks} if sc_chunks else set())

    result = {
        "question": question[:80],
        "query_type": qt.value,
        "vector_hits": len(qr.vector_hits),
        "graph_nodes": len(qr.graph_nodes),
        "graph_edges": len(qr.graph_edges),
        "source_chunks": len(sc_chunks),
        "chunk_files": [Path(f).name for f in chunk_files if f],
        "confidence": gr.overall_confidence,
        "warnings": gr.warnings,
        "answer": answer,
        "elapsed_s": round(time.time() - t0, 2),
    }
    if verbose:
        print(f"\n    Q: {question[:100]}")
        print(f"    [Type={qt.value} | nodes={len(qr.graph_nodes)} | edges={len(qr.graph_edges)} | chunks={len(sc_chunks)}]")
        print(f"    A: {answer[:400]}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# SKOR HESAPLAMA
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
    # Türkçe — statik ifadeler
    "yok", "değil", "bulunmamaktadır", "bulunmuyor", "içermemektedir",
    "mevcut değil", "yer almıyor", "kullanılmıyor", "kullanılmamaktadır",
    "olmayan", "yoktur", "hayır", "bulunamadı", "desteklenmiyor",
    "reddediyorum", "bilinmiyor", "içermiyor", "bulunmamakta",
    # Türkçe — fiil olumsuz ekleri (-ma/-me + -(i)yor/-dı/-mış/-dığı)
    "çalışmadığı", "çalışmıyor", "çalışmamaktadır", "çalışmamakta",
    "yer almadığı", "yer almamaktadır", "yer almıyor",
    "bulunmadığı", "bulunmadı", "bulunmayan",
    "kullanılmadığı", "kullanılmamaktadır", "kullanılmıyor",
    "tanımlanmadığı", "tanımlanmamış", "tanımlanmamaktadır",
    "içermediği", "içermemektedir", "içermiyor",
    "görmüyorum", "gözlenmemektedir", "tespit edilememiştir",
    "yer almamış", "mevcut değildir", "mevcut olmadığı",
    "kullanılmamış", "eklenmemiş", "bağlı değil", "desteklenmemektedir",
    # İngilizce
    "not ", "no ", "does not", "doesn't", "without", "absent",
    "not found", "not available", "not present", "not used", "disabled",
]


def score_real_question(q: Dict, answer: str) -> Tuple[float, List[str], List[str]]:
    """
    Real questions: key_terms (60%) + key_values (40%) match.
    Returns (score, term_hits, val_hits).
    """
    ans_lower = answer.lower()
    term_hits = [t for t in q["key_terms"] if t.lower() in ans_lower]
    val_hits  = [v for v in q["key_values"] if v.lower() in ans_lower]
    term_score = len(term_hits) / len(q["key_terms"])
    val_score  = len(val_hits) / len(q["key_values"])
    score = term_score * 0.60 + val_score * 0.40
    return round(score, 3), term_hits, val_hits


def score_trap_question(q: Dict, answer: str) -> Tuple[float, str, List[str]]:
    """
    Trap questions: system should say "not in DB" without inventing values.
    Returns (score, verdict, hallucination_matches).
    """
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
        score, verdict = 1.0, "PASS"
    elif says_unknown and has_halluc:
        score, verdict = 0.5, "PARTIAL (reddetti ama uydurma değer var)"
    elif not says_unknown and has_halluc:
        score, verdict = 0.0, "FAIL (hallucinasyon)"
    else:
        score, verdict = 0.3, "PARTIAL (genel cevap, net ret yok)"

    return round(score, 3), verdict, halluc_matches


# ─────────────────────────────────────────────────────────────────────────────
# TEST ÇALIŞTIRICISI
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_INFO = {
    "rtl":      ("RTL / Verilog (PROJECT-A)", 0.25),
    "firmware": ("C Firmware  (PROJECT-A)",   0.25),
    "tcl":      ("TCL / Block Design (B)",    0.25),
    "xdc":      ("XDC / Constraints (B)",     0.15),
    "trap":     ("Trap (DB'de yok)",           0.10),
}


def run_category(
    cat_key: str,
    questions: List[Dict],
    router, gate, llm, system_prompt: str,
    verbose: bool,
) -> Dict:
    label, _ = CATEGORY_INFO[cat_key]
    print(hdr(f"KATEGORİ: {label}"))

    results = []
    for q in questions:
        is_trap = q.get("expected") == "NOT_IN_DB"
        print(f"\n  {B}{q['id']}{RST}  [{q['project']}]")

        r = ask(q["question"], router, gate, llm, system_prompt, verbose)
        answer = r["answer"]

        if is_trap:
            score, verdict, halluc_matches = score_trap_question(q, answer)
            sym = ok if score >= 0.8 else (warn if score >= 0.4 else err)
            print(f"    {sym(f'Trap skor={score:.2f} — {verdict}')}")
            if halluc_matches:
                print(f"    Uydurma: {halluc_matches[:3]}")
            results.append({
                "id": q["id"],
                "category": cat_key,
                "project": q["project"],
                "type": "trap",
                "score": score,
                "verdict": verdict,
                "hallucination_matches": halluc_matches,
                "source_chunks": r["source_chunks"],
                "chunk_files": r["chunk_files"],
                "query_type": r["query_type"],
                "answer_snippet": answer[:300],
                "ground_truth": q.get("note", ""),
            })
        else:
            score, term_hits, val_hits = score_real_question(q, answer)
            sym = ok if score >= 0.8 else (warn if score >= 0.5 else err)
            print(f"    {sym(f'Skor={score:.2f}')} | terms={term_hits} | vals={val_hits}")
            print(f"    Source: {r['source_chunks']} chunk | {r['chunk_files']}")
            results.append({
                "id": q["id"],
                "category": cat_key,
                "project": q["project"],
                "type": "real",
                "score": score,
                "term_hits": term_hits,
                "term_misses": [t for t in q["key_terms"] if t not in term_hits],
                "val_hits": val_hits,
                "val_misses": [v for v in q["key_values"] if v not in val_hits],
                "source_chunks": r["source_chunks"],
                "chunk_files": r["chunk_files"],
                "query_type": r["query_type"],
                "answer_snippet": answer[:300],
                "ground_truth": q.get("note", ""),
            })

    avg = sum(r["score"] for r in results) / len(results) if results else 0
    print(f"\n  {B}Kategori skoru{RST}: {avg:.3f} → {grade(avg)}")
    return {
        "category": cat_key,
        "label": label,
        "score": round(avg, 3),
        "grade": grade_raw(avg),
        "n_questions": len(results),
        "questions": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ÖZET RAPOR
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(cat_results: List[Dict]) -> float:
    print(f"\n{B}{'═'*68}{RST}")
    print(f"{B}  BLIND BENCHMARK — ÖZET RAPOR{RST}")
    print(f"{B}{'═'*68}{RST}")

    total_weighted = 0.0
    for cr in cat_results:
        cat_key = cr["category"]
        _, weight = CATEGORY_INFO.get(cat_key, ("?", 0.20))
        s = cr["score"]
        bar = "█" * int(s * 20) + "░" * (20 - int(s * 20))
        total_weighted += s * weight
        print(f"  {cr['label']:35s} {bar} {s:.3f} [{grade(s)}] (w={weight:.0%})")

    print(f"\n  {'─'*68}")
    print(f"  AĞIRLIKLI TOPLAM SKOR : {total_weighted:.3f} → {grade(total_weighted)}")
    print(f"  {'─'*68}")

    # Soru bazlı detay
    all_q = [q for cr in cat_results for q in cr["questions"]]
    n_total = len(all_q)
    n_pass  = sum(1 for q in all_q if q["score"] >= 0.80)
    n_fail  = sum(1 for q in all_q if q["score"] < 0.50)
    n_trap  = sum(1 for q in all_q if q["type"] == "trap")
    n_trap_pass = sum(1 for q in all_q if q["type"] == "trap" and q["score"] >= 0.80)

    print(f"\n  Toplam soru    : {n_total}")
    print(f"  Geçen (≥0.80)  : {n_pass}/{n_total}")
    print(f"  Başarısız (<0.50): {n_fail}/{n_total}")
    print(f"  Trap geçen     : {n_trap_pass}/{n_trap}")

    # En kötü sorular
    worst = sorted(all_q, key=lambda x: x["score"])[:3]
    print(f"\n  En düşük 3 soru:")
    for q in worst:
        misses = q.get("term_misses", []) + q.get("val_misses", [])
        print(f"    {q['id']}: skor={q['score']:.2f} | eksik={misses}")

    print(f"{B}{'═'*68}{RST}\n")
    return round(total_weighted, 3)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FPGA RAG v2 Blind Benchmark")
    parser.add_argument("--save",     action="store_true", help="JSON raporu kaydet")
    parser.add_argument("--verbose",  action="store_true", help="Tam cevapları göster")
    parser.add_argument("--category", type=str, default="",
                        help="Sadece belirli kategori (rtl/firmware/tcl/xdc/trap)")
    args = parser.parse_args()

    print(f"\n{B}{'═'*68}")
    print(f"  FPGA RAG v2 — Blind Benchmark")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*68}{RST}")
    print(f"\n  Kapsam  : {sum(len(v) for v in BLIND_QUESTIONS.values())} soru × 5 kategori")
    print(f"  Önemli  : Bu sorular sistem tarafından hiç görülmemiştir!")

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

    for cat_key, questions in BLIND_QUESTIONS.items():
        if only_cat and cat_key != only_cat:
            continue
        cr = run_category(cat_key, questions, router, gate, llm,
                          system_prompt, args.verbose)
        cat_results.append(cr)

    elapsed = round(time.time() - t_start, 1)
    final_score = print_summary(cat_results)
    print(f"  Toplam süre: {elapsed}s")

    if args.save:
        # robustness_report.json ile karşılaştırma için aynı dizine yaz
        out_path = _ROOT / "blind_benchmark_report.json"
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_score": final_score,
            "overall_grade": grade_raw(final_score),
            "elapsed_s": elapsed,
            "n_questions": sum(len(v) for v in BLIND_QUESTIONS.values()),
            "categories": cat_results,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"  Rapor kaydedildi: {out_path}")


if __name__ == "__main__":
    main()
