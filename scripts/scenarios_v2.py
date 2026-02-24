#!/usr/bin/env python3
"""
FPGA RAG v2 — Kullanım Senaryoları
====================================
Mimari dökümandaki 5 sorgu tipini gerçek projeler (PROJECT-A, PROJECT-B) üzerinde gösteren
demo scripti. OpenAI API ile tam LLM yanıtları üretir.

Çalıştırma:
    source .venv/bin/activate
    python scripts/scenarios_v2.py                     # tüm senaryolar
    python scripts/scenarios_v2.py --scenario 1        # tek senaryo
    python scripts/scenarios_v2.py --no-llm            # sadece context (API key gereksiz)
    python scripts/scenarios_v2.py --list              # senaryo listesi
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

_PROJ_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJ_ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(_PROJ_ROOT / ".env")
except ImportError:
    pass

from rag_v2.graph_store import GraphStore
from rag_v2.vector_store_v2 import VectorStoreV2
from rag_v2.query_router import QueryRouter, QueryType
from rag_v2.hallucination_gate import HallucinationGate
from rag_v2.response_builder import (
    build_llm_context,
    build_structured_response,
    FPGA_RAG_SYSTEM_PROMPT,
)

# ---------------------------------------------------------------------------
# Senaryo tanımları
# ---------------------------------------------------------------------------

SCENARIOS = [
    # ── Senaryo 1: WHAT ──────────────────────────────────────────────────
    {
        "id": 1,
        "title": "WHAT — Proje Genel Bakış",
        "query_type": QueryType.WHAT,
        "question": "Nexys A7 DMA audio projesi nedir ve hangi FPGA kullanılıyor?",
        "description": (
            "En genel sorgu tipi. Tüm store'ları paralel sorgular.\n"
            "PROJECT node'u + bağlı SOURCE_DOC ve ISSUE node'ları döner."
        ),
        "expected_nodes": ["PROJECT-A", "PROJECT-B"],
    },
    # ── Senaryo 2: HOW ───────────────────────────────────────────────────
    {
        "id": 2,
        "title": "HOW — Bileşen Detayı",
        "query_type": QueryType.HOW,
        "question": "AXI DMA bileşeni nasıl çalışır, hangi port ve parametrelere sahip?",
        "description": (
            "COMPONENT + PATTERN node'larını önceliklendirir.\n"
            "DEPENDS_ON ve REUSES_PATTERN edge'lerini takip eder."
        ),
        "expected_nodes": ["COMP-A-axi_dma_0"],
    },
    # ── Senaryo 3: WHY ───────────────────────────────────────────────────
    {
        "id": 3,
        "title": "WHY — Mimari Karar Gerekçesi",
        "query_type": QueryType.WHY,
        "question": "neden interrupt yerine polling tercih edildi?",
        "description": (
            "DECISION node'larını + MOTIVATED_BY edge'lerini getirir.\n"
            "Anti-hallüsinasyon: karar için kanıt node'u zorunlu."
        ),
        "expected_nodes": ["DMA-DEC-005"],
    },
    # ── Senaryo 4: TRACE ─────────────────────────────────────────────────
    {
        "id": 4,
        "title": "TRACE — Gereksinim İzleme Zinciri",
        "query_type": QueryType.TRACE,
        "question": "DMA-REQ-L1-001 gereksinimini hangi bileşen karşılıyor?",
        "description": (
            "IMPLEMENTS ve VERIFIED_BY edge'lerini çift yönlü takip eder.\n"
            "Requirement tree BFS ile genişletilir."
        ),
        "expected_nodes": ["COMP-A-axi_dma_0", "DMA-REQ-L1-001"],
    },
    # ── Senaryo 5: CROSSREF ──────────────────────────────────────────────
    {
        "id": 5,
        "title": "CROSSREF — Çapraz Proje Karşılaştırma",
        "query_type": QueryType.CROSSREF,
        "question": "PROJECT-A ve PROJECT-B'deki clk_wiz bileşenleri arasındaki fark nedir?",
        "description": (
            "ANALOGOUS_TO ve CONTRADICTS edge'lerini arar.\n"
            "İki proje arasındaki benzer/farklı pattern'ları gösterir."
        ),
        "expected_nodes": ["COMP-A-clk_wiz_0", "COMP-B-clk_wiz_0"],
    },
    # ── Senaryo 6: Anti-Hallüsinasyon Demo ───────────────────────────────
    {
        "id": 6,
        "title": "ANTI-HALÜSINASYON — Coverage Gap + PARSE_UNCERTAIN",
        "query_type": QueryType.TRACE,
        "question": "DMA-REQ-L0-001 genel gereksinimi hangi bileşen karşılıyor?",
        "description": (
            "DMA-REQ-L0-001'in doğrudan IMPLEMENTS edge'i yok (coverage gap).\n"
            "Layer-3 uyarısı üretmeli: 'no implementing component'."
        ),
        "expected_nodes": ["DMA-REQ-L0-001"],
    },
    # ── Senaryo 7: AXI-B Projesi ─────────────────────────────────────────
    {
        "id": 7,
        "title": "PROJECT-B — AXI GPIO Traceability",
        "query_type": QueryType.TRACE,
        "question": "AXI GPIO wrapper hangi gereksinimi karşılıyor?",
        "description": (
            "PROJECT-B (axi_example) için traceability.\n"
            "axi_gpio_wrapper → AXI-REQ-L2-001 ve AXI-REQ-L1-005 zinciri."
        ),
        "expected_nodes": ["COMP-B-axi_gpio_wrapper", "AXI-REQ-L2-001"],
    },
    # ── Senaryo 8: Otomatik Sınıflandırma ────────────────────────────────
    {
        "id": 8,
        "title": "OTOMATİK SINIFLANDIRMA — Karma Sorgu",
        "query_type": None,  # auto-classify
        "question": "MIG 7-series DDR2 kontrolcüsü neden seçildi ve nasıl çalışır?",
        "description": (
            "Classifier 'neden' → WHY olarak sınıflandırmalı.\n"
            "DECISION + MOTIVATED_BY chain gösterir."
        ),
        "expected_nodes": ["COMP-A-mig_7series_0"],
    },
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class ScenarioRunner:
    def __init__(self, use_llm: bool = True, model: str = "gpt-4o-mini"):
        self.use_llm = use_llm
        self.model = model

        print("[Init] GraphStore yükleniyor...")
        self.gs = GraphStore(persist_path=str(_PROJ_ROOT / "db" / "graph" / "fpga_rag_v2_graph.json"))
        print("[Init] VectorStoreV2 yükleniyor...")
        self.vs = VectorStoreV2(persist_directory=str(_PROJ_ROOT / "db" / "chroma_graph_nodes"),
                                threshold=0.35)
        print("[Init] QueryRouter + HallucinationGate hazır.")
        self.router = QueryRouter(self.gs, self.vs, n_vector_results=5)
        self.gate = HallucinationGate(self.gs)

        self._llm = None
        if use_llm:
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key or api_key.startswith("your-"):
                print("[WARN] OPENAI_API_KEY ayarlanmamış — LLM devre dışı.")
                self.use_llm = False
            else:
                from rag.openai_generator import OpenAIGenerator
                self._llm = OpenAIGenerator(api_key=api_key, model_name=model)
                print(f"[Init] OpenAI ({model}) hazır.\n")

    def run(self, scenario: dict, verbose: bool = True) -> dict:
        sep = "=" * 65
        print(f"\n{sep}")
        print(f"  SENARYO {scenario['id']}: {scenario['title']}")
        print(sep)
        print(f"  Sorgu   : {scenario['question']}")
        print(f"  Tip     : {scenario['query_type'].value if scenario['query_type'] else 'AUTO'}")
        print(f"  Açıklama: {scenario['description']}")
        print("-" * 65)

        t0 = time.time()

        # Route
        qr = self.router.route(scenario["question"], scenario["query_type"])

        # Gate
        all_nodes = qr.all_nodes()
        gr = self.gate.check(all_nodes, qr.graph_edges)

        elapsed_route = time.time() - t0

        # Stats
        print(f"  Vector hits : {len(qr.vector_hits)}")
        print(f"  Graph nodes : {len(qr.graph_nodes)}")
        print(f"  Graph edges : {len(qr.graph_edges)}")
        print(f"  Req tree    : {len(qr.req_tree)}")
        print(f"  Confidence  : {gr.overall_confidence}")
        print(f"  Warnings    : {len(gr.warnings)}")
        print(f"  Stale filt  : {len(gr.filtered_node_ids)}")
        print(f"  Route time  : {elapsed_route:.2f}s")

        # Expected node check
        retrieved_ids = {n.get("node_id", "") for n in all_nodes}
        for exp in scenario.get("expected_nodes", []):
            found = exp in retrieved_ids
            print(f"  Beklenen '{exp}': {'✓' if found else '✗ BULUNAMADI'}")

        # Uyarılar
        if gr.warnings and verbose:
            print("\n  [Anti-Hallüsinasyon Uyarıları]")
            for w in gr.warnings[:5]:
                print(f"    {w}")
            if len(gr.warnings) > 5:
                print(f"    ... ve {len(gr.warnings)-5} uyarı daha")

        # LLM
        llm_answer = None
        if self.use_llm:
            ctx = build_llm_context(qr, gr, max_nodes=8)
            system = FPGA_RAG_SYSTEM_PROMPT.split("CONTEXT:")[0].strip()
            t1 = time.time()
            try:
                llm_answer = self._llm.generate(
                    query=scenario["question"],
                    context_documents=[ctx],
                    system_prompt=system,
                    temperature=0.3,
                )
                print(f"\n  [GPT-4o-mini yanıtı — {time.time()-t1:.1f}s]")
                print("  " + "\n  ".join(llm_answer.splitlines()))
            except Exception as e:
                llm_answer = f"(LLM hatası: {e})"
                print(f"  [LLM] Hata: {e}")
        else:
            ctx = build_llm_context(qr, gr, max_nodes=6)
            print("\n  [Context (LLM devre dışı)]")
            # Sadece ilk 20 satır
            for line in ctx.splitlines()[:20]:
                print(f"  {line}")
            print("  ...")

        resp = build_structured_response(scenario["question"], qr, gr, llm_answer)
        print(f"\n  Toplam süre: {time.time()-t0:.2f}s")
        return resp

    def run_all(self, ids: Optional[List[int]] = None, verbose: bool = True) -> List[dict]:
        results = []
        scenarios = [s for s in SCENARIOS if ids is None or s["id"] in ids]
        for s in scenarios:
            r = self.run(s, verbose=verbose)
            results.append({"scenario_id": s["id"], **r})
        return results


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(results: List[dict]) -> None:
    sep = "=" * 65
    print(f"\n{sep}")
    print("  ÖZET")
    print(sep)
    for r in results:
        sid = r["scenario_id"]
        conf = r.get("confidence", "?")
        srcs = len(r.get("sources", []))
        warns = len(r.get("warnings", []))
        print(f"  Senaryo {sid:2d}: conf={conf:<15} kaynak={srcs:3d}  uyarı={warns:3d}")
    print(sep)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="FPGA RAG v2 — Kullanım Senaryoları Demo"
    )
    parser.add_argument("--scenario", "-s", type=int, nargs="+",
                        help="Çalıştırılacak senaryo ID'leri (örn: --scenario 1 3 5)")
    parser.add_argument("--no-llm", action="store_true",
                        help="LLM çağrısını atla, sadece context göster")
    parser.add_argument("--model", default="gpt-4o-mini",
                        help="OpenAI model (varsayılan: gpt-4o-mini)")
    parser.add_argument("--list", action="store_true",
                        help="Senaryo listesini göster ve çık")
    parser.add_argument("--quiet", action="store_true",
                        help="Detaylı çıktıyı azalt")
    args = parser.parse_args()

    if args.list:
        print("\nFPGA RAG v2 — Senaryo Listesi\n")
        for s in SCENARIOS:
            qt = s["query_type"].value if s["query_type"] else "AUTO"
            print(f"  [{s['id']:2d}] {qt:<10} {s['title']}")
            print(f"       Soru: {s['question']}")
        return

    runner = ScenarioRunner(use_llm=not args.no_llm, model=args.model)
    results = runner.run_all(ids=args.scenario, verbose=not args.quiet)
    print_summary(results)


if __name__ == "__main__":
    main()
