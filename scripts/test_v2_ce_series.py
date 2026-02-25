#!/usr/bin/env python3
"""
FPGA RAG v2 — C+E Serisi Değerlendirme (20 Soru)
==================================================
C-Serisi: Eksik alanlar — SDK Build, MIG, Bitstream, Simülasyon, P&R, DRC
E-Serisi: Sınav — Çapraz analiz, ters mühendislik, hata senaryoları

Kullanım:
    python scripts/test_v2_ce_series.py
    python scripts/test_v2_ce_series.py --save
    python scripts/test_v2_ce_series.py --no-llm
"""

from __future__ import annotations

import sys, os, time, json, re, argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")


# ─────────────────────────────────────────────────────────────────────────────
# C + E SERİSİ TEST SORULARI
# ─────────────────────────────────────────────────────────────────────────────

TEST_CASES = [
    # ═══════════════════════════════════════════════════════════════
    # C-SERİSİ — Eksik Alanlar
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "C-Q01",
        "project": "nexys_a7_dma_audio",
        "category": "Linker Script / Bellek Layout",
        "difficulty": "Orta",
        "domain": "SDK Build",
        "question": "DMA Audio projesinde `lscript.ld` linker script'i belleği nasıl bölüyor? MicroBlaze'in BRAM (LMB) ve DDR2 segmentleri hangi adreslerde tanımlanmış? Stack ve heap boyutları nedir?",
        "key_terms": ["lscript.ld", "BRAM", "DDR2", "stack", "heap", "microblaze"],
        "key_values": ["0x80000000", "0x00000000"],
        "key_files": ["helloworld.c"],
    },
    {
        "id": "C-Q02",
        "project": "nexys_a7_dma_audio",
        "category": "Yazılım Bug Analizi",
        "difficulty": "Zor",
        "domain": "Hata Senaryosu",
        "question": "helloworld.c'deki DMA polling döngülerinde (`XAxiDma_Busy`) timeout mekanizması var mı? Sonsuz döngüye girilirse sistem nasıl kurtarılır? Bu bug hangi satırlarda gizli?",
        "key_terms": ["XAxiDma_Busy", "polling", "timeout", "sonsuz döngü", "watchdog", "busy"],
        "key_values": [],
        "key_files": ["helloworld.c"],
    },
    {
        "id": "C-Q03",
        "project": "nexys_a7_dma_audio",
        "category": "Timeout / Sonsuz Döngü",
        "difficulty": "Zor",
        "domain": "Hata Senaryosu",
        "question": "helloworld.c'de UART receive (`XUartLite_Recv`) ve DMA transfer polling döngüleri watchdog timer olmadan bloklanabilir. Bu durumu önlemek için hangi yazılım değişiklikleri gerekir? `XAxiDma_Reset` ne zaman çağrılmalı?",
        "key_terms": ["XUartLite_Recv", "XAxiDma_Reset", "timeout", "watchdog", "blocking"],
        "key_values": [],
        "key_files": ["helloworld.c"],
    },
    {
        "id": "C-Q04",
        "project": "axi_gpio_example",
        "category": "IP Versiyon Kataloğu",
        "difficulty": "Orta",
        "domain": "Kurgu",
        "question": "axi_gpio_example projesinde kullanılan IP bloklarının sürüm numaraları nedir? Clocking Wizard, Proc Sys Reset, AXI GPIO, AXI Interconnect ve MicroBlaze sürümleri hangi Vivado sürümüyle uyumlu?",
        "key_terms": ["clk_wiz", "proc_sys_reset", "axi_gpio", "microblaze", "versiyon", "v6", "v5", "v2"],
        "key_values": [],
        "key_files": ["create_minimal_microblaze.tcl", "add_axi_gpio.tcl"],
    },
    {
        "id": "C-Q05",
        "project": "nexys_a7_dma_audio",
        "category": "MIG DDR2 Kalibrasyon",
        "difficulty": "Zor",
        "domain": "MIG / DDR2",
        "question": "Nexys A7 DMA Audio projesinde `mig_7series_0` DDR2 kontrolcüsü kalibrasyon sürecini nasıl yürütüyor? `ui_clk` (81.25 MHz) ve `init_calib_complete` sinyali ne anlama geliyor? MIG'in clock domain'i sistem saatiyle nasıl bağlanıyor?",
        "key_terms": ["mig_7series_0", "ui_clk", "init_calib_complete", "DDR2", "kalibrasyon", "calib"],
        "key_values": ["81.25", "81"],
        "key_files": ["design_1.tcl"],
    },
    {
        "id": "C-Q06",
        "project": "nexys_a7_dma_audio",
        "category": "Bitstream + ELF Gömme",
        "difficulty": "Zor",
        "domain": "Bitstream",
        "question": "Nexys A7 DMA Audio projesinde bitstream oluşturulduktan sonra MicroBlaze yazılımı (.elf) bitstream'e nasıl gömülür? `updatemem` komutu hangi parametrelerle çalıştırılır? `.mmi` dosyası ve `BMM_INFO_PROCESSOR` pragma'sı bu süreçte ne rol oynar? BRAM içeriği nasıl güncellenir?",
        "key_terms": ["updatemem", "bitstream", "elf", "BMM", "mmi", "BRAM", "write_bitstream"],
        "key_values": [],
        "key_files": ["design_1.tcl"],
    },
    {
        "id": "C-Q07",
        "project": "nexys_a7_dma_audio",
        "category": "Testbench Tasarımı",
        "difficulty": "Zor",
        "domain": "Simülasyon",
        "question": "`fifo2audpwm` modülünü test etmek için Verilog testbench nasıl tasarlanır? Normal akış, `fifo_empty` durumu ve PWM duty cycle doğruluğu için hangi test senaryoları gerekli? `aud_pwm` çıkışı nasıl doğrulanır? `DATA_WIDTH=8` ve `count[DATA_WIDTH+1:DATA_WIDTH]` mantığı simülasyonda nasıl test edilir?",
        "key_terms": ["testbench", "fifo_empty", "aud_pwm", "DATA_WIDTH", "simülasyon", "duty", "count"],
        "key_values": ["8"],
        "key_files": ["fifo2audpwm.v"],
    },
    {
        "id": "C-Q08",
        "project": "axi_gpio_example",
        "category": "Utilization Tahmini",
        "difficulty": "Orta",
        "domain": "Implementasyon",
        "question": "axi_gpio_example projesi xc7a200tsbg484-1 FPGA'ya implement edildiğinde LUT, FF ve BRAM kullanımı tahminen ne kadar olur? MicroBlaze, AXI Interconnect ve AXI GPIO IP'lerinin kaynak ayak izi nedir? SYNTHESIS_RESULTS.md'deki sentez verilerini kullan.",
        "key_terms": ["LUT", "FF", "BRAM", "utilization", "xc7a200t", "kaynak", "resource"],
        "key_values": [],
        "key_files": ["SYNTHESIS_RESULTS.md"],
    },
    {
        "id": "C-Q09",
        "project": "nexys_a7_dma_audio",
        "category": "WAV Dosya İşleme",
        "difficulty": "Orta",
        "domain": "Yazılım",
        "question": "helloworld.c'deki `recv_wav()` fonksiyonu WAV dosyasını nasıl işliyor? RIFF header'ı nasıl parse ediliyor? `MAX_WAV_SIZE` sınırı nedir ve bu sınır aşıldığında ne olur? Format doğrulama adımları nelerdir?",
        "key_terms": ["recv_wav", "RIFF", "WAV", "MAX_WAV_SIZE", "header", "parse"],
        "key_values": ["0x7FFFFF", "8388607"],
        "key_files": ["helloworld.c"],
    },
    {
        "id": "C-Q10",
        "project": "axi_gpio_example",
        "category": "DRC / Critical Warning",
        "difficulty": "Zor",
        "domain": "Hata Senaryosu",
        "question": "axi_gpio_example projesini Vivado'da implement ederken hangi DRC hataları veya kritik uyarılar çıkabilir? NSTD-1 (IOSTANDARD tanımsız), UCIO-1 (tanımsız pin), CFGBVS-1 (config bank voltajı) ve TIMING-18 (setup violation) ne zaman tetiklenir? XDC'de `set_property CFGBVS GND` ve `CONFIG_VOLTAGE` ne işe yarar?",
        "key_terms": ["DRC", "NSTD-1", "CFGBVS", "TIMING", "set_property", "CONFIG_VOLTAGE", "critical warning"],
        "key_values": [],
        "key_files": ["nexys_video.xdc"],
    },

    # ═══════════════════════════════════════════════════════════════
    # E-SERİSİ — Sınav / Çapraz Analiz
    # ═══════════════════════════════════════════════════════════════
    {
        "id": "E-Q01",
        "project": "axi_gpio_example",
        "category": "Port Listesinden Tasarım Çıkarma",
        "difficulty": "Zor",
        "domain": "Kurgu",
        "question": "Top-level wrapper'ın port listesi: `clk_100mhz_clk_n`, `clk_100mhz_clk_p`, `led_8bits_tri_o[7:0]`, `reset`. Bu port listesinden tasarımın hangi IP'leri içerdiğini, clock tipini (diferansiyel LVDS) ve GPIO yönünü (yalnızca çıkış) çıkarın.",
        "key_terms": ["LVDS", "diferansiyel", "clk_wiz", "GPIO", "MicroBlaze", "proc_sys_reset"],
        "key_values": ["R4", "T4"],
        "key_files": ["nexys_video.xdc", "axi_gpio_wrapper.v"],
    },
    {
        "id": "E-Q02",
        "project": "nexys_a7_dma_audio",
        "category": "440 Hz INCREMENT Hesabı",
        "difficulty": "Orta",
        "domain": "RTL Analiz",
        "question": "`tone_generator.v`'de mevcut `localparam INCREMENT = 32'h00B22D0E` değeri 261 Hz için hesaplanmış. DDS formülü: `INCREMENT = (frekans × 2^ACCUMULATOR_DEPTH) / AUD_SAMPLE_FREQ`. 440 Hz (La notası) için yeni INCREMENT değeri nedir? `ACCUMULATOR_DEPTH=32`, `AUD_SAMPLE_FREQ=96000`. Decimal ve hex cinsinden ver.",
        "key_terms": ["INCREMENT", "DDS", "ACCUMULATOR_DEPTH", "AUD_SAMPLE_FREQ", "440", "19685267"],
        "key_values": ["0x012C5F93", "19685267"],
        "key_files": ["tone_generator.v"],
    },
    {
        "id": "E-Q03",
        "project": "nexys_a7_dma_audio",
        "category": "FIFO Empty Debug",
        "difficulty": "Zor",
        "domain": "Debug",
        "question": "`fifo2audpwm` modülünde FIFO tamamen boşaldığında sinyal zinciri nasıl ilerliyor? `fifo_empty=1` → `fifo_rd_en` → `aud_en` → PWM çıkışı adım adım açıkla. `count` sayacı çalışmaya devam eder mi? `duty` register'ları sıfırlanır mı?",
        "key_terms": ["fifo_empty", "fifo_rd_en", "aud_en", "aud_pwm", "duty", "count"],
        "key_values": [],
        "key_files": ["fifo2audpwm.v"],
    },
    {
        "id": "E-Q04",
        "project": "axi_gpio_example",
        "category": "Adres Çakışması Analizi",
        "difficulty": "Orta",
        "domain": "Yazılım",
        "question": "axi_gpio_example projesinde `0x40000000` AXI GPIO'ya, DMA Audio projesinde `0x40000000` GPIO_IN'e atanmış. Bu iki adres aynı fiziksel register'a mı erişiyor? Farklı projelerde aynı base adres kullanılabilir mi? AXI Interconnect segment atamalarını karşılaştır.",
        "key_terms": ["0x40000000", "SEG_axi_gpio_0", "GPIO_IN", "adres haritası", "segment"],
        "key_values": ["0x40000000", "64 KB"],
        "key_files": ["add_axi_gpio.tcl", "design_1.tcl"],
    },
    {
        "id": "E-Q05",
        "project": "nexys_a7_dma_audio",
        "category": "Ses Kesintisi Root Cause",
        "difficulty": "Zor",
        "domain": "Debug",
        "question": "Kullanıcı raporluyor: 'Ses 170 ms sonra kesilip ~1 ms sessizlik oluyor, tekrar çalıyor.' `helloworld.c`'deki polling tabanlı DMA yönetimi bu davranışa nasıl yol açıyor? Buffer boyutu (128 byte × 96 kHz × 4 byte/sample) ile hesapla. Interrupt + double buffering nasıl çözer?",
        "key_terms": ["polling", "buffer", "double buffering", "interrupt", "underrun", "BUFFER_SIZE"],
        "key_values": ["128"],
        "key_files": ["helloworld.c"],
    },
    {
        "id": "E-Q06",
        "project": "axi_gpio_example",
        "category": "Constraint Çatışması Tespiti",
        "difficulty": "Orta",
        "domain": "Sentez",
        "question": "`vivado_axi_simple` variant'ında clock pini R4 için `IOSTANDARD LVCMOS33` atanmış. Nexys Video'daki R4 pini diferansiyel LVDS clock girişi — banka voltajı LVCMOS33 ile uyumsuz. Vivado hangi DRC kodlarını üretir? `BIVC-1`, `Place 30-574` ve `Opt 31-35` hatalarını açıkla.",
        "key_terms": ["LVCMOS33", "LVDS", "BIVC-1", "DRC", "banka voltajı", "diferansiyel", "constraint"],
        "key_values": ["R4", "1.8V", "3.3V"],
        "key_files": ["nexys_video.xdc", "axi_gpio_wrapper.v"],
    },
    {
        "id": "E-Q07",
        "project": "nexys_a7_dma_audio",
        "category": "32→8 Bit Veri Bütünlüğü",
        "difficulty": "Zor",
        "domain": "RTL Analiz",
        "question": "Yazılım (`dma_sw_tone_gen`) 8-bit sample üretip 32-bit DMA buffer'a paketliyor. `axis2fifo.v` bu 32-bit veriyi `axis_tdata[15:0]` ile 16-bit'e kesiyor. `fifo2audpwm.v` ise `fifo_rd_data[7:0]` ile 8-bit alıyor. Bu zincirde hangi bitler kayboluyor? `tdata[31:16]` ne zaman atılıyor? Ses frekansına etkisi nedir?",
        "key_terms": ["axis_tdata", "tdata", "truncation", "fifo_rd_data", "bit loss", "16", "axis2fifo"],
        "key_values": ["31:16", "15:0", "7:0"],
        "key_files": ["axis2fifo.v", "fifo2audpwm.v", "helloworld.c"],
    },
    {
        "id": "E-Q08",
        "project": "nexys_a7_dma_audio",
        "category": "Polling'den Interrupt'a Geçiş",
        "difficulty": "Zor",
        "domain": "Yazılım",
        "question": "DMA Audio projesinde `xlconcat_0` ve AXI INTC (0x41200000) donanımda hazır ama kullanılmıyor. Polling'den interrupt tabanlı DMA'ya geçiş için `helloworld.c`'de hangi değişiklikler gerekli? `XIntc_Initialize`, `XAxiDma_IntrGetIrq`, `XAxiDma_IntrAckIrq` fonksiyonları nasıl kullanılır?",
        "key_terms": ["XIntc_Initialize", "XAxiDma_IntrGetIrq", "XAxiDma_IntrAckIrq", "interrupt", "xlconcat", "0x41200000"],
        "key_values": [],
        "key_files": ["helloworld.c", "design_1.tcl"],
    },
    {
        "id": "E-Q09",
        "project": "axi_gpio_example",
        "category": "AXI Bus Topoloji Karşılaştırma",
        "difficulty": "Orta",
        "domain": "Kurgu",
        "question": "axi_gpio_example (1×1 AXI4-Lite) ile DMA Audio projesinin AXI bus topolojilerini karşılaştır. DMA Audio'da kaç AXI master ve slave var? AXI-Stream pipeline nerede? `microblaze_0_axi_periph` 1×5 mi 1×1 mi? `axi_interconnect_0` DDR2'ye kaç master erişiyor?",
        "key_terms": ["1×1", "1×5", "AXI-Stream", "microblaze_0_axi_periph", "axi_interconnect_0", "DDR2", "master", "slave"],
        "key_values": [],
        "key_files": ["design_1.tcl", "add_axi_gpio.tcl"],
    },
    {
        "id": "E-Q10",
        "project": "axi_gpio_example",
        "category": "Sentez Öncesi Checklist",
        "difficulty": "Orta",
        "domain": "Sentez",
        "question": "axi_gpio_example projesini sentezlemeden önce kontrol edilmesi gereken 8 maddelik checklist oluştur: (1) Clock kaynağı, (2) Reset zinciri, (3) Adres haritası, (4) AXI bağlantıları, (5) MicroBlaze yapılandırması, (6) GPIO genişlik/yön, (7) Timing constraint, (8) TCL build akışı. Her madde için mevcut projenin durumunu belirt.",
        "key_terms": ["checklist", "clock", "reset", "adres", "AXI", "GPIO", "timing", "TCL"],
        "key_values": [],
        "key_files": ["create_minimal_microblaze.tcl", "nexys_video.xdc"],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# PUANLAMA — test_v2_20q.py ile aynı mantık
# ─────────────────────────────────────────────────────────────────────────────

def score_answer(answer: str, tc: dict) -> dict:
    ans = answer.lower()

    term_hits  = [t for t in tc["key_terms"]  if t.lower() in ans]
    term_miss  = [t for t in tc["key_terms"]  if t.lower() not in ans]
    value_hits = [v for v in tc["key_values"] if v.lower() in ans]
    value_miss = [v for v in tc["key_values"] if v.lower() not in ans]
    file_hits  = [f for f in tc["key_files"]  if f.lower() in ans]
    file_miss  = [f for f in tc["key_files"]  if f.lower() not in ans]

    t_score = len(term_hits)  / max(len(tc["key_terms"]),  1)
    v_score = len(value_hits) / max(len(tc["key_values"]), 1) if tc["key_values"] else 1.0
    f_score = len(file_hits)  / max(len(tc["key_files"]),  1) if tc["key_files"]  else 1.0

    score = t_score * 0.50 + v_score * 0.35 + f_score * 0.15
    return {
        "score": score,
        "term_hits": term_hits, "term_misses": term_miss,
        "value_hits": value_hits, "value_misses": value_miss,
        "file_hits": file_hits, "file_misses": file_miss,
    }

def grade(score: float) -> str:
    if score >= 0.80: return "A"
    if score >= 0.65: return "B"
    if score >= 0.50: return "C"
    if score >= 0.35: return "D"
    return "F"


# ─────────────────────────────────────────────────────────────────────────────
# SİSTEM YÜKLEME + LLM
# ─────────────────────────────────────────────────────────────────────────────

def load_v2_system():
    from rag_v2.graph_store import GraphStore
    from rag_v2.vector_store_v2 import VectorStoreV2
    from rag_v2.query_router import QueryRouter
    from rag_v2.hallucination_gate import HallucinationGate
    from rag_v2.source_chunk_store import SourceChunkStore

    graph_path  = str(_ROOT / "db" / "graph" / "fpga_rag_v2_graph.json")
    chroma_path = str(_ROOT / "db" / "chroma_graph_nodes")
    source_path = str(_ROOT / "db" / "chroma_source_chunks")

    print(f"  [1] Graph: {graph_path}")
    gs = GraphStore(persist_path=graph_path)
    print(f"  [2] VectorStore: {chroma_path}")
    vs = VectorStoreV2(persist_directory=chroma_path, threshold=0.35)
    print(f"  [3] SourceChunks: {source_path}")
    sc = SourceChunkStore(persist_directory=source_path)
    print(f"  [4] QueryRouter + HallucinationGate...")
    router = QueryRouter(gs, vs, n_vector_results=6, source_chunk_store=sc, n_source_results=10)
    gate   = HallucinationGate(gs)

    stats = gs.stats()
    print(f"  Graph: {stats['total_nodes']} nodes, {stats['total_edges']} edges")
    print(f"  Vector: {vs.count()} docs | Source chunks: {sc.count()}")
    return gs, vs, sc, router, gate


def get_llm():
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key and not anthropic_key.startswith("your-"):
        from rag.claude_generator import ClaudeGenerator
        return ClaudeGenerator(api_key=anthropic_key, model_name="claude-haiku-4-5-20251001")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key and not openai_key.startswith("your-"):
        from rag.openai_generator import OpenAIGenerator
        return OpenAIGenerator(api_key=openai_key, model_name="gpt-4o-mini")
    return None


def run_question(question, router, gate, llm, system_prompt):
    from rag_v2.response_builder import build_llm_context
    t0 = time.time()
    qt = router.classify(question)
    qr = router.route(question, qt)
    all_nodes = qr.all_nodes()
    gr = gate.check(all_nodes, qr.graph_edges)
    ctx = build_llm_context(qr, gr, max_nodes=10, max_chars=12000)
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
        llm_answer = "[LLM yok]"
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
        "elapsed_s": round(time.time() - t0, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("  FPGA RAG v2 — C+E Serisi Değerlendirme (20 Soru)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    print("\n[SİSTEM YÜKLEME]")
    gs, vs, sc, router, gate = load_v2_system()

    llm = None if args.no_llm else get_llm()
    if llm:
        print(f"  [5] LLM: {llm.__class__.__name__} ({getattr(llm, 'model_name', '?')}) ✓")
    else:
        print(f"  [5] LLM: DEVRE DIŞI")

    from rag_v2.response_builder import FPGA_RAG_SYSTEM_PROMPT
    system_prompt = FPGA_RAG_SYSTEM_PROMPT.split("CONTEXT:")[0].strip()

    print(f"\n{'=' * 72}")
    print(f"  TEST — {len(TEST_CASES)} SORU (C-Serisi + E-Serisi)")
    print(f"{'=' * 72}")

    all_results  = []
    scores_by_series   = {"C-Serisi": [], "E-Serisi": []}
    scores_by_domain   = {}
    scores_by_difficulty = {"Kolay": [], "Orta": [], "Zor": []}

    # Hedef kategoriler
    target_cats = {
        "Bitstream":   [],
        "Simülasyon":  [],
        "Implementasyon": [],
        "Hata Senaryosu": [],
    }

    for i, tc in enumerate(TEST_CASES, 1):
        series = "C-Serisi" if tc["id"].startswith("C") else "E-Serisi"
        print(f"\n[{i:02d}/20] {tc['id']} — {tc['category']}")
        print(f"         Proje: {tc['project']} | Zorluk: {tc['difficulty']} | Alan: {tc['domain']}")
        print(f"         Soru: {tc['question'][:80]}...")

        result = run_question(tc["question"], router, gate, llm, system_prompt)
        scoring = score_answer(result["answer"], tc)
        g = grade(scoring["score"])

        print(f"         → QType: {result['query_type']} | "
              f"vec:{result['vector_hits']} graph:{result['graph_nodes']} "
              f"edges:{result['graph_edges']} chunks:{result['source_chunks']}")
        print(f"         → Güven: {result['confidence']} | Süre: {result['elapsed_s']}s")
        print(f"         → Skor: {scoring['score']:.3f} [{g}] | "
              f"Terim:{len(scoring['term_hits'])}/{len(tc['key_terms'])} | "
              f"Değer:{len(scoring['value_hits'])}/{max(len(tc['key_values']),1)} | "
              f"Dosya:{len(scoring['file_hits'])}/{len(tc['key_files'])}")

        if scoring["term_misses"]:
            print(f"         → Eksik terimler: {scoring['term_misses']}")
        if scoring["value_misses"]:
            print(f"         → Eksik değerler: {scoring['value_misses']}")

        if args.verbose and result["answer"]:
            print(f"\n--- LLM CEVAP ---\n{result['answer'][:800]}\n")

        # Accumulate
        scores_by_series[series].append(scoring["score"])
        scores_by_domain.setdefault(tc["domain"], []).append(scoring["score"])
        scores_by_difficulty[tc["difficulty"]].append(scoring["score"])

        # Hedef kategoriler
        dom = tc["domain"]
        if dom == "Bitstream":
            target_cats["Bitstream"].append(scoring["score"])
        elif dom == "Simülasyon":
            target_cats["Simülasyon"].append(scoring["score"])
        elif dom == "Implementasyon":
            target_cats["Implementasyon"].append(scoring["score"])
        elif dom == "Hata Senaryosu":
            target_cats["Hata Senaryosu"].append(scoring["score"])

        all_results.append({
            "id": tc["id"], "series": series, "category": tc["category"],
            "domain": tc["domain"], "difficulty": tc["difficulty"],
            "score": scoring["score"], "grade": g,
            "confidence": result["confidence"],
            "term_hits": scoring["term_hits"], "term_misses": scoring["term_misses"],
            "value_hits": scoring["value_hits"], "value_misses": scoring["value_misses"],
            "file_hits": scoring["file_hits"], "file_misses": scoring["file_misses"],
            "elapsed_s": result["elapsed_s"], "answer_preview": result["answer"][:300],
        })

    # ── ÖZET ──────────────────────────────────────────────────────────────────
    all_scores = [r["score"] for r in all_results]
    avg = sum(all_scores) / len(all_scores)
    g_dist = {"A":0,"B":0,"C":0,"D":0,"F":0}
    for s in all_scores:
        g_dist[grade(s)] += 1

    print(f"\n{'=' * 72}")
    print(f"  ÖZET ANALİZ")
    print(f"{'=' * 72}")
    print(f"\n  Toplam soru    : {len(all_results)}")
    print(f"  Ortalama skor  : {avg:.3f} [{grade(avg)}]")
    print(f"  Min / Max      : {min(all_scores):.3f} / {max(all_scores):.3f}")

    print(f"\n  Not dağılımı:")
    for g, cnt in g_dist.items():
        bar = "█" * cnt
        print(f"    {g}: {bar} ({cnt})")

    print(f"\n  Seri bazlı:")
    for s, sc_list in scores_by_series.items():
        if sc_list:
            avg_s = sum(sc_list)/len(sc_list)
            print(f"    {s:<30}: {avg_s:.3f} [{grade(avg_s)}]  ({len(sc_list)} soru)")

    print(f"\n  Alan bazlı:")
    for d, sc_list in sorted(scores_by_domain.items()):
        avg_d = sum(sc_list)/len(sc_list)
        print(f"    {d:<20}: {avg_d:.3f} [{grade(avg_d)}]  ({len(sc_list)} soru)")

    print(f"\n  Zorluk bazlı:")
    for d, sc_list in scores_by_difficulty.items():
        if sc_list:
            avg_d = sum(sc_list)/len(sc_list)
            print(f"    {d:<10}: {avg_d:.3f} [{grade(avg_d)}]  ({len(sc_list)} soru)")

    print(f"\n  ── Hedef Kategoriler ──────────────────────────────────────────")
    for cat, sc_list in target_cats.items():
        if sc_list:
            avg_c = sum(sc_list)/len(sc_list)
            bar = "█" * int(avg_c * 20)
            print(f"    {cat:<20}: {avg_c:.3f} [{grade(avg_c)}]  {bar}")
        else:
            print(f"    {cat:<20}: — (bu seride soru yok)")

    print(f"\n  Başarı metrikleri:")
    print(f"    Skor ≥ 0.80 (A)    : {sum(1 for s in all_scores if s>=0.80)}/20 = {sum(1 for s in all_scores if s>=0.80)*5}%")
    print(f"    Skor ≥ 0.65 (B+)   : {sum(1 for s in all_scores if s>=0.65)}/20 = {sum(1 for s in all_scores if s>=0.65)*5}%")
    print(f"    Skor ≥ 0.50 (C+)   : {sum(1 for s in all_scores if s>=0.50)}/20 = {sum(1 for s in all_scores if s>=0.50)*5}%")

    worst = sorted(all_results, key=lambda x: x["score"])[:5]
    best  = sorted(all_results, key=lambda x: x["score"], reverse=True)[:3]
    print(f"\n  En iyi 3 soru:")
    for r in best:
        print(f"    {r['id']}  [{r['grade']}] {r['score']:.3f} — {r['category']}")
    print(f"\n  En kötü 5 soru (eğitim hedefleri):")
    for r in worst:
        print(f"    {r['id']}  [{r['grade']}] {r['score']:.3f} — {r['category']} | Eksik: {r['term_misses'][:3]}")

    print(f"\n  {'─'*70}")
    print(f"  GENEL NOT: {grade(avg)} — {'Mükemmel' if avg>=0.80 else 'İyi' if avg>=0.65 else 'Orta' if avg>=0.50 else 'Zayıf'}")
    print(f"  {'─'*70}")
    print(f"\n{'=' * 72}")
    print(f"  DEĞERLENDİRME TAMAMLANDI")
    print(f"{'=' * 72}")

    if args.save:
        out = _ROOT / "evaluation_ce_series.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "avg_score": avg, "grade": grade(avg),
                "results": all_results,
                "target_categories": {k: (sum(v)/len(v) if v else 0) for k,v in target_cats.items()},
            }, f, ensure_ascii=False, indent=2)
        print(f"\n  Sonuçlar kaydedildi: {out}")


if __name__ == "__main__":
    main()
