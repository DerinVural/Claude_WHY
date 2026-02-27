#!/usr/bin/env python3
"""
FPGA RAG v2 — 20 Soru Değerlendirme Scripti
============================================
test.txt dosyasındaki 20 soruyu RAG v2 pipeline'ından geçirir,
LLM cevapları üretir ve başarı metriklerine göre analiz eder.

Kullanım:
    python scripts/test_v2_20q.py
    python scripts/test_v2_20q.py --no-llm   # Yalnızca retrieval (LLM yok)
    python scripts/test_v2_20q.py --save      # Sonuçları JSON'a kaydet
"""

from __future__ import annotations

import sys
import os
import time
import json
import re
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Proje kökü
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")


# ─────────────────────────────────────────────────────────────────────────────
# 20 TEST SORUSU + BEKLENEN CEVAP ANALİZ KRİTERLERİ
# ─────────────────────────────────────────────────────────────────────────────

TEST_CASES = [
    # ── Proje A ──────────────────────────────────────────────────────────────
    {
        "id": "A-Q01",
        "project": "axi_gpio_example",
        "category": "Clock Yapılandırması",
        "difficulty": "Orta",
        "domain": "Kurgu",
        "question": "axi_gpio_example projesinde Nexys Video kartının saat sinyali karta nasıl giriyor? `nexys_video.xdc`'de clock için hangi PACKAGE_PIN (R4) ve IOSTANDARD (LVCMOS33) kullanılmış? `clk_wiz_0` 100 MHz çıkış (`clk_out1`) ve `locked` sinyallerini nereye bağlıyor?",
        "key_terms": ["R4", "clk_wiz", "locked", "LVCMOS33", "clk_out1"],
        "key_values": ["100 MHz", "100mhz"],
        "key_files": ["nexys_video.xdc", "create_minimal_microblaze.tcl"],
    },
    {
        "id": "A-Q02",
        "project": "axi_gpio_example",
        "category": "GPIO IP Kanal ve Yön Konfigürasyonu",
        "difficulty": "Kolay",
        "domain": "Kurgu",
        "question": "AXI GPIO IP'si kaç kanal, kaç bit genişlikte ve hangi yönde (giriş/çıkış) yapılandırılmış? Bu ayarlar BD dosyasının neresinde tanımlı?",
        "key_terms": ["C_GPIO_WIDTH", "C_ALL_OUTPUTS", "axi_gpio_0", "tek kanal", "çıkış", "output"],
        "key_values": ["8", "1"],
        "key_files": ["add_axi_gpio.tcl"],
    },
    {
        "id": "A-Q03",
        "project": "axi_gpio_example",
        "category": "Adres Haritası ve BRAM Boyutlandırma",
        "difficulty": "Orta",
        "domain": "Yazılım",
        "question": "axi_gpio_example projesinde `assign_bd_address` ile `SEG_axi_gpio_0` ve `C_D_LMB` (BRAM) segmentleri hangi adreslere atanmış? `create_minimal_microblaze.tcl`'de `local_mem` 8KB olarak tanımlanmış — GPIO base adresi (0x40000000) ve BRAM boyutu nedir?",
        "key_terms": ["SEG_axi_gpio_0", "BRAM", "C_D_LMB", "assign_bd_address", "0x40000000"],
        "key_values": ["8KB", "8 KB"],
        "key_files": ["add_axi_gpio.tcl", "create_minimal_microblaze.tcl"],
    },
    {
        "id": "A-Q04",
        "project": "axi_gpio_example",
        "category": "Reset Topolojisi",
        "difficulty": "Zor",
        "domain": "Debug",
        "question": "axi_gpio_example projesinde harici `reset_n` girişi (PACKAGE_PIN G4, IOSTANDARD LVCMOS15) XDC'de nasıl tanımlanmış? `rst_clk_wiz_0_100M` Processor System Reset modülü `peripheral_aresetn` ve `dcm_locked` sinyallerini nasıl üretiyor? MDM (`mdm_1`) bu zincirde nerede?",
        "key_terms": ["rst_clk_wiz_0_100M", "reset_n", "peripheral_aresetn", "dcm_locked", "MDM", "mdm_1"],
        "key_values": ["G4", "LVCMOS15"],
        "key_files": ["create_minimal_microblaze.tcl"],
    },
    {
        "id": "A-Q05",
        "project": "axi_gpio_example",
        "category": "AXI Interconnect Yapısı",
        "difficulty": "Orta",
        "domain": "Kurgu",
        "question": "AXI Interconnect kaç master ve kaç slave portuna sahip? MicroBlaze'den GPIO'ya veri yolu nasıl oluşuyor?",
        "key_terms": ["NUM_MI", "S00_AXI", "M00_AXI", "M_AXI_DP", "microblaze_0_axi_periph"],
        "key_values": ["1"],
        "key_files": ["add_axi_gpio.tcl"],
    },
    {
        "id": "A-Q06",
        "project": "axi_gpio_example",
        "category": "LED IOSTANDARD Seçimi",
        "difficulty": "Orta",
        "domain": "Sentez",
        "question": "Nexys Video XDC'de `leds[0]` ve `switches[0]` için hangi PACKAGE_PIN ve IOSTANDARD atanmış? Clock ve reset pinlerinin IOSTANDARD'ı nedir? T14, E22, LVCMOS25, LVCMOS12 değerlerini açıklayın.",
        "key_terms": ["LVCMOS25", "LVCMOS12", "LVCMOS15", "LVCMOS33", "switch", "LED"],
        "key_values": ["T14", "E22"],
        "key_files": ["nexys_video.xdc"],
    },
    {
        "id": "A-Q07",
        "project": "axi_gpio_example",
        "category": "Standalone Wrapper Neden Çalışmaz",
        "difficulty": "Zor",
        "domain": "Debug",
        "question": "`vivado_axi_simple/axi_gpio_wrapper.v` dosyasında AXI sinyalleri nasıl bağlanmış? s_axi_awaddr gibi AXI master sinyalleri tie-off edilmiş mi? GPIO portları (gpio_io_o, gpio_io_i) düzgün bağlanmış mı?",
        "key_terms": ["s_axi_awaddr", "32'h0", "gpio_io_o", "standalone", "tied off"],
        "key_values": ["1'b0"],
        "key_files": ["axi_gpio_wrapper.v"],
    },
    {
        "id": "A-Q08",
        "project": "axi_gpio_example",
        "category": "MicroBlaze Debug ve JTAG",
        "difficulty": "Zor",
        "domain": "Debug",
        "question": "MicroBlaze Debug Module (MDM) tasarımda hangi rolleri üstleniyor? Debug reset sinyali sistemi nasıl etkiler?",
        "key_terms": ["MDM", "mdm_1", "JTAG", "debug", "breakpoint", "C_USE_UART"],
        "key_values": [],
        "key_files": ["create_minimal_microblaze.tcl"],
    },
    {
        "id": "A-Q09",
        "project": "axi_gpio_example",
        "category": "Sentez Sonuçları ve Kaynak Kullanımı",
        "difficulty": "Orta",
        "domain": "Sentez",
        "question": "axi_gpio_example projesinin `SYNTHESIS_RESULTS.md` raporuna göre `microblaze_bd_wrapper` sentezinde kaç Slice LUT ve BRAM Tile kullanılmış? LUT Utilization yüzdesi nedir? DSP kullanımı var mı? Synthesis başarılı mı?",
        "key_terms": ["LUT", "BRAM", "synthesis", "microblaze_bd_wrapper", "Utilization"],
        "key_values": ["1,412", "1.05"],
        "key_files": ["SYNTHESIS_RESULTS.md"],
    },
    {
        "id": "A-Q10",
        "project": "axi_gpio_example",
        "category": "Timing Constraint Analizi",
        "difficulty": "Orta",
        "domain": "Sentez",
        "question": "Nexys Video XDC dosyasında `clk` portuna hangi `PACKAGE_PIN` ve `IOSTANDARD` atanmış? `create_clock` constraint nedir? R4 pinine LVCMOS33 ile bağlanan bu constraint'i açıklayın.",
        "key_terms": ["create_clock", "sys_clk", "LVCMOS33", "PACKAGE_PIN", "R4"],
        "key_values": ["10.000"],
        "key_files": ["nexys_video.xdc"],
    },
    # ── Proje B ──────────────────────────────────────────────────────────────
    {
        "id": "B-Q01",
        "project": "nexys_a7_dma_audio",
        "category": "Veri Yolu Genişlik Kaybı",
        "difficulty": "Orta",
        "domain": "Kurgu",
        "question": "`axis2fifo` modülü `axis_tdata` (32-bit) verisini alıp FIFO'ya yazarken kaç bit truncation (kırpma) uyguluyor? `fifo2audpwm`'de 8 bit `DATA_WIDTH` ile ses çıkışı nasıl üretiliyor?",
        "key_terms": ["axis2fifo", "fifo2audpwm", "axis_tdata", "truncation", "8 bit"],
        "key_values": ["32", "16", "8"],
        "key_files": ["axis2fifo.v", "fifo2audpwm.v"],
    },
    {
        "id": "B-Q02",
        "project": "nexys_a7_dma_audio",
        "category": "PWM Sayacı ve Örnekleme Zamanlaması",
        "difficulty": "Zor",
        "domain": "RTL Analiz",
        "question": "`fifo2audpwm` modülünde `count` ve `duty` sinyalleri birlikte nasıl çalışarak PWM oluşturuyor? `DATA_WIDTH+2` bit neden kullanılıyor? `fifo_rd_en` ne zaman assert ediliyor?",
        "key_terms": ["count", "DATA_WIDTH", "PWM", "duty", "fifo_rd_en"],
        "key_values": ["10 bit", "8", "1024", "256", "97.6 kHz"],
        "key_files": ["fifo2audpwm.v"],
    },
    {
        "id": "B-Q03",
        "project": "nexys_a7_dma_audio",
        "category": "Phase Increment Hesaplama",
        "difficulty": "Orta",
        "domain": "RTL Analiz",
        "question": "Tone generator'da `localparam INCREMENT = 32'h00B22D0E` değeri nasıl hesaplanmış? `TONE_FREQ=261` ve `ACCUMULATOR_DEPTH=32` değerleri bu hesaplamada nasıl kullanılıyor?",
        "key_terms": ["TONE_FREQ", "INCREMENT", "accumulator", "ACCUMULATOR_DEPTH", "localparam"],
        "key_values": ["261", "96000", "0x00B22D0E"],
        "key_files": ["tone_generator.v"],
    },
    {
        "id": "B-Q04",
        "project": "nexys_a7_dma_audio",
        "category": "FIFO Boyutlandırma ve PWM Buffer",
        "difficulty": "Orta",
        "domain": "Kurgu",
        "question": "`fifo2audpwm` modülünde `fifo_rd_en` sinyali ne zaman assert edilir? `duty` ve `count` register'ları nasıl çalışarak PWM üretiyor? `fifo_empty` ve `aud_en` arasındaki ilişki nedir? `DATA_WIDTH` parametresi kaç bit?",
        "key_terms": ["fifo_empty", "aud_en", "fifo_rd_en", "DATA_WIDTH", "duty", "count"],
        "key_values": ["8", "10"],
        "key_files": ["fifo2audpwm.v"],
    },
    {
        "id": "B-Q05",
        "project": "nexys_a7_dma_audio",
        "category": "DMA Transfer Modu",
        "difficulty": "Kolay",
        "domain": "Yazılım",
        "question": "AXI DMA IP'si Scatter-Gather modunda mı yoksa Direct Register modunda mı çalışıyor? `XAxiDma_HasSg` kontrolü ne söylüyor? MM2S ve S2MM transferleri `dma_send`/`dma_receive` fonksiyonlarında nasıl başlatılıyor? Transfer tamamlanana kadar `XAxiDma_Busy` polling ile mi bekleniyor? `dma_forward` içindeki `BUFFER_SIZE_WORDS` kaç word olarak tanımlanmış?",
        "key_terms": ["XAxiDma_HasSg", "Direct Register", "XAxiDma_SimpleTransfer", "MM2S", "polling"],
        "key_values": ["256", "BUFFER_SIZE"],
        "key_files": ["helloworld.c"],
    },
    {
        "id": "B-Q06",
        "project": "nexys_a7_dma_audio",
        "category": "Clock Domain'ler ve Crossing",
        "difficulty": "Zor",
        "domain": "Sentez",
        "question": "Nexys A7 DMA Audio projesinde kaç farklı clock domain var? `mig_7series_0` `ui_clk` (81.25 MHz) ile `clk_wiz_0` (100 MHz) arasındaki CDC (Clock Domain Crossing) async FIFO ile nasıl çözülmüş?",
        "key_terms": ["clk_wiz_0", "ui_clk", "CDC", "async FIFO", "MIG"],
        "key_values": ["3", "100 MHz", "81.25 MHz"],
        "key_files": ["axis2fifo.v"],
    },
    {
        "id": "B-Q07",
        "project": "nexys_a7_dma_audio",
        "category": "Bellek Haritası ve Peripheral Adresleri",
        "difficulty": "Kolay",
        "domain": "Yazılım",
        "question": "helloworld.c'de `XPAR_GPIO_IN`, `XPAR_GPIO_OUT`, `XPAR_AXI_DMA` peripheral ID'leri ve `DDR_BASE_ADDR` (MIG: `XPAR_MIG7SERIES_0_BASEADDR`) tanımları nelerdir? Ses verisi için hangi bellek adresi kullanılıyor?",
        "key_terms": ["XPAR_GPIO_IN", "XPAR_GPIO_OUT", "XPAR_AXI_DMA", "DDR_BASE_ADDR", "XPAR_MIG"],
        "key_values": ["0x40000000", "0x41E00000"],
        "key_files": ["helloworld.c", "design_1.tcl"],
    },
    {
        "id": "B-Q08",
        "project": "nexys_a7_dma_audio",
        "category": "axis2fifo Back-Pressure Mekanizması",
        "difficulty": "Zor",
        "domain": "RTL Analiz",
        "question": "`axis2fifo` modülünde `fifo_full` sinyali `axis_tready`'yi nasıl etkiliyor? `tvalid`/`tready` AXI-Stream handshake ile back-pressure nasıl uygulanıyor? Veri kaybı olabilir mi?",
        "key_terms": ["axis_tready", "fifo_full", "back-pressure", "tvalid", "handshake"],
        "key_values": [],
        "key_files": ["axis2fifo.v"],
    },
    {
        "id": "B-Q09",
        "project": "nexys_a7_dma_audio",
        "category": "XDC Constraint Stratejisi",
        "difficulty": "Orta",
        "domain": "Sentez",
        "question": "Nexys A7 DMA Audio projesinin XDC dosyasında `PWM_AUDIO_0_pwm` ve `PWM_AUDIO_0_en` portları için hangi PACKAGE_PIN ve IOSTANDARD değerleri atanmış? Bu pinlerin `aud_pwm` fonksiyonu nedir?",
        "key_terms": ["PWM_AUDIO_0", "LVCMOS33", "A11", "D12", "aud_pwm"],
        "key_values": ["2"],
        "key_files": ["Nexys-A7-100T-Master.xdc"],
    },
    {
        "id": "B-Q10",
        "project": "nexys_a7_dma_audio",
        "category": "Demo Modları ve Buton Eşlemesi",
        "difficulty": "Kolay",
        "domain": "Yazılım",
        "question": "SDK yazılımında kaç çalışma modu var, her mod hangi butona atanmış ve varsayılan mod hangisi? Hangi modlar gerçekten çalışıyor?",
        "key_terms": ["DEMO_MODE_SW_TONE_GEN", "DEMO_MODE_PAUSED", "DEMO_MODE_RECV_WAV_FILE",
                      "DEMO_MODE_PLAY_WAV_FILE", "DEMO_MODE_HW_TONE_GEN"],
        "key_values": ["5", "0x10", "261"],
        "key_files": ["helloworld.c"],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────────────────────────────────────

def score_answer(answer: str, tc: Dict) -> Dict:
    """
    LLM cevabını beklenen anahtar terimlere göre puanla.
    Returns: {score, term_hits, value_hits, file_hits, details}
    """
    ans_lower = answer.lower()

    # Key terms check (case-insensitive)
    term_hits = []
    term_misses = []
    for t in tc["key_terms"]:
        if t.lower() in ans_lower:
            term_hits.append(t)
        else:
            term_misses.append(t)

    # Key values check
    value_hits = []
    value_misses = []
    for v in tc["key_values"]:
        if v.lower() in ans_lower:
            value_hits.append(v)
        else:
            value_misses.append(v)

    # Key files check
    file_hits = []
    file_misses = []
    for f in tc["key_files"]:
        fname_lower = f.lower().replace(".", "")
        if f.lower() in ans_lower or fname_lower in ans_lower:
            file_hits.append(f)
        else:
            file_misses.append(f)

    # Score calculation
    term_score  = len(term_hits) / len(tc["key_terms"]) if tc["key_terms"] else 1.0
    value_score = len(value_hits) / len(tc["key_values"]) if tc["key_values"] else 1.0
    file_score  = len(file_hits) / len(tc["key_files"]) if tc["key_files"] else 1.0

    # Weights: terms 50%, values 35%, files 15%
    total = (term_score * 0.50) + (value_score * 0.35) + (file_score * 0.15)

    # Length check — too short = suspicious
    if len(answer) < 80:
        total *= 0.5

    return {
        "score": round(total, 3),
        "term_hits": term_hits,
        "term_misses": term_misses,
        "value_hits": value_hits,
        "value_misses": value_misses,
        "file_hits": file_hits,
        "file_misses": file_misses,
        "answer_len": len(answer),
    }


def grade(score: float) -> str:
    if score >= 0.80: return "A"
    if score >= 0.65: return "B"
    if score >= 0.50: return "C"
    if score >= 0.35: return "D"
    return "F"


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def load_v2_system():
    """GraphStore + VectorStoreV2 + SourceChunkStore + QueryRouter + HallucinationGate (4-store)"""
    from rag_v2.graph_store import GraphStore
    from rag_v2.vector_store_v2 import VectorStoreV2
    from rag_v2.query_router import QueryRouter
    from rag_v2.hallucination_gate import HallucinationGate
    from rag_v2.source_chunk_store import SourceChunkStore

    graph_path  = str(_ROOT / "db" / "graph" / "fpga_rag_v2_graph.json")
    chroma_path = str(_ROOT / "db" / "chroma_graph_nodes")
    source_path = str(_ROOT / "db" / "chroma_source_chunks")

    print(f"  [1] Graph yükleniyor: {graph_path}")
    gs = GraphStore(persist_path=graph_path)

    print(f"  [2] VectorStore yükleniyor: {chroma_path}")
    vs = VectorStoreV2(persist_directory=chroma_path, threshold=0.35)

    print(f"  [3] SourceChunkStore yükleniyor: {source_path}")
    sc = SourceChunkStore(persist_directory=source_path)

    print(f"  [4] QueryRouter + HallucinationGate başlatılıyor (4-store)...")
    router = QueryRouter(gs, vs, n_vector_results=6, source_chunk_store=sc, n_source_results=10)
    gate   = HallucinationGate(gs)

    stats = gs.stats()
    print(f"  Graph: {stats['total_nodes']} nodes, {stats['total_edges']} edges")
    print(f"  Vector: {vs.count()} docs | Source chunks: {sc.count()}")
    return gs, vs, sc, router, gate


def get_llm():
    from rag.llm_factory import get_llm as _get_llm
    return _get_llm("claude-sonnet-4-6")


def run_question(question: str, router, gate, llm, system_prompt: str) -> Dict:
    """Tek soruyu pipeline'dan geçir, sonuç dict döndür."""
    from rag_v2.response_builder import build_llm_context

    t0 = time.time()

    # 1. Classify + Route
    qt = router.classify(question)
    qr = router.route(question, qt)

    # 2. Hallucination Gate
    all_nodes = qr.all_nodes()
    gr = gate.check(all_nodes, qr.graph_edges)

    # 3. Build context — increase max_chars to give LLM more source code
    ctx = build_llm_context(qr, gr, max_nodes=10, max_chars=12000)

    # 4. LLM
    llm_answer = None
    if llm:
        try:
            llm_answer = llm.generate(
                query=question,
                context_documents=[ctx],
                system_prompt=system_prompt,
                temperature=0.3,
            )
        except Exception as e:
            llm_answer = f"[LLM HATA: {e}]"
    else:
        llm_answer = "[LLM yok — API key eksik]"

    elapsed = round(time.time() - t0, 2)

    return {
        "query_type": qt.value,
        "vector_hits": len(qr.vector_hits),
        "graph_nodes": len(qr.graph_nodes),
        "graph_edges": len(qr.graph_edges),
        "req_tree": len(qr.req_tree),
        "source_chunks": len(getattr(qr, "source_chunks", [])),
        "confidence": gr.overall_confidence,
        "warnings": gr.warnings,
        "stale_count": len(gr.filtered_node_ids),
        "answer": llm_answer or "",
        "elapsed_s": elapsed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true", help="LLM çağrısını atla")
    parser.add_argument("--save", action="store_true", help="Sonuçları JSON'a kaydet")
    parser.add_argument("--verbose", "-v", action="store_true", help="LLM cevabını göster")
    args = parser.parse_args()

    print("=" * 72)
    print("  FPGA RAG v2 — 20 Soru Değerlendirme")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    # Sistem yükle
    print("\n[SISTEM YÜKLEME]")
    gs, vs, sc, router, gate = load_v2_system()

    # LLM
    llm = None if args.no_llm else get_llm()
    if llm:
        print(f"  [4] LLM: {llm.__class__.__name__} ({getattr(llm, 'model_name', '?')}) ✓")
    else:
        print(f"  [4] LLM: DEVRE DIŞI {'(--no-llm)' if args.no_llm else '(key yok)'}")

    # System prompt (response_builder'dan al)
    from rag_v2.response_builder import FPGA_RAG_SYSTEM_PROMPT
    system_prompt = FPGA_RAG_SYSTEM_PROMPT.split("CONTEXT:")[0].strip()

    print(f"\n{'=' * 72}")
    print(f"  TEST — {len(TEST_CASES)} SORU")
    print(f"{'=' * 72}")

    all_results = []
    scores_by_project = {"axi_gpio_example": [], "nexys_a7_dma_audio": []}
    scores_by_domain  = {}
    scores_by_difficulty = {"Kolay": [], "Orta": [], "Zor": []}

    for i, tc in enumerate(TEST_CASES, 1):
        print(f"\n[{i:02d}/20] {tc['id']} — {tc['category']}")
        print(f"         Proje: {tc['project']} | Zorluk: {tc['difficulty']} | Alan: {tc['domain']}")
        print(f"         Soru: {tc['question'][:80]}...")

        # Pipeline
        result = run_question(tc["question"], router, gate, llm, system_prompt)

        # Score
        scoring = score_answer(result["answer"], tc)

        g = grade(scoring["score"])
        conf = result["confidence"]

        print(f"         → QueryType: {result['query_type']} | "
              f"vector:{result['vector_hits']} graph:{result['graph_nodes']} "
              f"edges:{result['graph_edges']} tree:{result['req_tree']} "
              f"chunks:{result['source_chunks']}")
        print(f"         → Güven: {conf} | Uyarı: {len(result['warnings'])} | "
              f"Stale: {result['stale_count']} | Süre: {result['elapsed_s']}s")
        print(f"         → Skor: {scoring['score']:.3f} [{g}] | "
              f"Terim:{len(scoring['term_hits'])}/{len(tc['key_terms'])} | "
              f"Değer:{len(scoring['value_hits'])}/{len(tc['key_values'])} | "
              f"Dosya:{len(scoring['file_hits'])}/{len(tc['key_files'])}")

        if scoring["term_misses"]:
            print(f"         → Eksik terimler: {scoring['term_misses']}")
        if scoring["value_misses"]:
            print(f"         → Eksik değerler: {scoring['value_misses']}")

        if args.verbose and result["answer"]:
            print(f"\n         LLM CEVAP:\n{result['answer'][:600]}\n")

        # Accumulate
        scores_by_project[tc["project"]].append(scoring["score"])
        domain = tc["domain"]
        scores_by_domain.setdefault(domain, []).append(scoring["score"])
        scores_by_difficulty[tc["difficulty"]].append(scoring["score"])

        entry = {
            **tc,
            "pipeline": result,
            "scoring": scoring,
            "grade": g,
        }
        all_results.append(entry)

    # ── ÖZET ──────────────────────────────────────────────────────────────────
    print(f"\n{'=' * 72}")
    print("  ÖZET ANALİZ")
    print(f"{'=' * 72}")

    all_scores = [r["scoring"]["score"] for r in all_results]
    avg_score = sum(all_scores) / len(all_scores)

    # Grade distribution
    grade_count = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for r in all_results:
        grade_count[r["grade"]] += 1

    print(f"\n  Toplam soru    : {len(TEST_CASES)}")
    print(f"  Ortalama skor  : {avg_score:.3f} [{grade(avg_score)}]")
    print(f"  Min / Max      : {min(all_scores):.3f} / {max(all_scores):.3f}")
    print(f"\n  Not dağılımı:")
    for g_label in ["A", "B", "C", "D", "F"]:
        count = grade_count[g_label]
        bar = "█" * count
        print(f"    {g_label}: {bar} ({count})")

    print(f"\n  Proje bazlı:")
    for proj, scores in scores_by_project.items():
        if scores:
            avg = sum(scores) / len(scores)
            print(f"    {proj:30s}: {avg:.3f} [{grade(avg)}]  ({len(scores)} soru)")

    print(f"\n  Zorluk bazlı:")
    for diff, scores in scores_by_difficulty.items():
        if scores:
            avg = sum(scores) / len(scores)
            print(f"    {diff:10s}: {avg:.3f} [{grade(avg)}]  ({len(scores)} soru)")

    print(f"\n  Alan bazlı:")
    for dom, scores in sorted(scores_by_domain.items()):
        avg = sum(scores) / len(scores)
        print(f"    {dom:15s}: {avg:.3f} [{grade(avg)}]  ({len(scores)} soru)")

    # Pipeline metrikleri
    avg_elapsed = sum(r["pipeline"]["elapsed_s"] for r in all_results) / len(all_results)
    conf_high = sum(1 for r in all_results if r["pipeline"]["confidence"].startswith("HIGH"))
    conf_medium = sum(1 for r in all_results if r["pipeline"]["confidence"].startswith("MEDIUM"))
    total_warnings = sum(len(r["pipeline"]["warnings"]) for r in all_results)

    print(f"\n  Pipeline metrikleri:")
    print(f"    Ortalama süre       : {avg_elapsed:.2f}s / soru")
    print(f"    HIGH güven          : {conf_high}/{len(TEST_CASES)}")
    print(f"    MEDIUM güven        : {conf_medium}/{len(TEST_CASES)}")
    print(f"    Toplam uyarı        : {total_warnings}")

    # Başarı metrikleri
    hit_80 = sum(1 for s in all_scores if s >= 0.80)
    hit_65 = sum(1 for s in all_scores if s >= 0.65)
    hit_50 = sum(1 for s in all_scores if s >= 0.50)

    print(f"\n  Başarı metrikleri:")
    print(f"    Skor ≥ 0.80 (A)    : {hit_80}/{len(TEST_CASES)} = {hit_80/len(TEST_CASES):.0%}")
    print(f"    Skor ≥ 0.65 (B+)   : {hit_65}/{len(TEST_CASES)} = {hit_65/len(TEST_CASES):.0%}")
    print(f"    Skor ≥ 0.50 (C+)   : {hit_50}/{len(TEST_CASES)} = {hit_50/len(TEST_CASES):.0%}")

    # En iyi / en kötü
    sorted_results = sorted(all_results, key=lambda r: r["scoring"]["score"], reverse=True)
    print(f"\n  En iyi 3 soru:")
    for r in sorted_results[:3]:
        print(f"    {r['id']:6s} [{r['grade']}] {r['scoring']['score']:.3f} — {r['category']}")
    print(f"\n  En kötü 3 soru:")
    for r in sorted_results[-3:]:
        print(f"    {r['id']:6s} [{r['grade']}] {r['scoring']['score']:.3f} — {r['category']}")

    # Genel not
    if avg_score >= 0.75:
        overall = "A — Mükemmel (sistem test.txt sorularını başarıyla cevaplayabiliyor)"
    elif avg_score >= 0.60:
        overall = "B — İyi (sistem büyük çoğunlukla doğru cevap veriyor)"
    elif avg_score >= 0.45:
        overall = "C — Orta (sistem temel soruları cevaplayabiliyor, geliştirilmeli)"
    elif avg_score >= 0.30:
        overall = "D — Zayıf (sistem önemli terimleri kaçırıyor)"
    else:
        overall = "F — Yetersiz (sistem kaynak dosyaları kapsamamıyor)"

    print(f"\n  {'─' * 70}")
    print(f"  GENEL NOT: {overall}")
    print(f"  {'─' * 70}")

    # Save
    if args.save:
        report = {
            "timestamp": datetime.now().isoformat(),
            "avg_score": round(avg_score, 4),
            "overall_grade": grade(avg_score),
            "hit_rate_A": round(hit_80 / len(TEST_CASES), 4),
            "hit_rate_B_plus": round(hit_65 / len(TEST_CASES), 4),
            "results": [
                {
                    "id": r["id"],
                    "project": r["project"],
                    "category": r["category"],
                    "difficulty": r["difficulty"],
                    "grade": r["grade"],
                    "score": r["scoring"]["score"],
                    "query_type": r["pipeline"]["query_type"],
                    "confidence": r["pipeline"]["confidence"],
                    "elapsed_s": r["pipeline"]["elapsed_s"],
                    "term_hits": r["scoring"]["term_hits"],
                    "term_misses": r["scoring"]["term_misses"],
                    "answer_preview": r["pipeline"]["answer"][:200],
                }
                for r in all_results
            ],
        }
        out_path = _ROOT / "evaluation_v2_20q.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n  Rapor kaydedildi: {out_path}")

    print(f"\n{'=' * 72}")
    print("  DEĞERLENDİRME TAMAMLANDI")
    print(f"{'=' * 72}\n")


if __name__ == "__main__":
    main()
