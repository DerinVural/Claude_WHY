#!/usr/bin/env python3
"""
FPGA RAG v2 — CLI Query Interface
Architecture ref: fpga_rag_architecture_v2.md §6

3-store federated query:
  Vector Store + Graph Store + Req Tree
  → Anti-Hallucination Gate
  → Structured Response (optional: Gemini LLM)

Usage:
    python scripts/query_v2.py "DMA nedir?"
    python scripts/query_v2.py "AXI neden 4KB burst sınırı var?" --type Why
    python scripts/query_v2.py "DMA-REQ-L1-001 hangi bileşen karşılıyor?" --type Trace
    python scripts/query_v2.py --interactive
    python scripts/query_v2.py --stats
    python scripts/query_v2.py "soru" --no-llm    # context only, no Gemini call
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

# .env yükle (OPENAI_API_KEY, GOOGLE_API_KEY)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

_PROJ_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJ_ROOT / "src"))

from rag_v2.graph_store import GraphStore
from rag_v2.vector_store_v2 import VectorStoreV2
from rag_v2.query_router import QueryRouter, QueryType
from rag_v2.hallucination_gate import HallucinationGate
from rag_v2.response_builder import (
    build_llm_context,
    build_structured_response,
    FPGA_RAG_SYSTEM_PROMPT,
)

DEFAULT_GRAPH_DB = str(_PROJ_ROOT / "db" / "graph" / "fpga_rag_v2_graph.json")
DEFAULT_CHROMA_DIR = str(_PROJ_ROOT / "db" / "chroma_graph_nodes")


# ---------------------------------------------------------------------------
# Store initialization (shared across queries)
# ---------------------------------------------------------------------------

def init_stores(graph_db: str, chroma_dir: str, threshold: float):
    graph_store = GraphStore(persist_path=graph_db)
    vector_store = VectorStoreV2(persist_directory=chroma_dir, threshold=threshold)

    if graph_store.stats()["total_nodes"] == 0:
        print("[ERROR] Graph DB is empty. Run: python scripts/build_graph_db.py")
        sys.exit(1)
    if vector_store.is_empty():
        print("[ERROR] Vector store is empty. Run: python scripts/build_graph_db.py")
        sys.exit(1)

    return graph_store, vector_store


# ---------------------------------------------------------------------------
# Single query
# ---------------------------------------------------------------------------

def run_query(
    question: str,
    router: QueryRouter,
    gate: HallucinationGate,
    query_type_str: Optional[str] = None,
    use_llm: bool = True,
    llm_provider: str = "openai",   # "openai" veya "gemini"
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    verbose: bool = True,
) -> dict:
    # Classify
    if query_type_str:
        qt_map = {qt.value: qt for qt in QueryType}
        query_type = qt_map.get(query_type_str, None)
        if query_type is None:
            print(f"[WARN] Unknown type '{query_type_str}', using auto-classify.")
            query_type = router.classify(question)
    else:
        query_type = router.classify(question)

    if verbose:
        print(f"\n[Query] '{question}'")
        print(f"[Query] Type: {query_type.value}")

    # Route
    query_result = router.route(question, query_type)

    if verbose:
        print(f"[Query] Vector hits : {len(query_result.vector_hits)}")
        print(f"[Query] Graph nodes : {len(query_result.graph_nodes)}")
        print(f"[Query] Graph edges : {len(query_result.graph_edges)}")
        print(f"[Query] Req tree    : {len(query_result.req_tree)}")

    # Gate
    all_nodes = query_result.all_nodes()
    gate_result = gate.check(all_nodes, query_result.graph_edges)

    if verbose:
        print(f"[Gate]  Confidence  : {gate_result.overall_confidence}")
        print(f"[Gate]  Warnings    : {len(gate_result.warnings)}")
        print(f"[Gate]  Stale filt  : {len(gate_result.filtered_node_ids)}")

    # LLM call (optional)
    llm_answer = None
    if use_llm:
        context_str = build_llm_context(query_result, gate_result)
        system = FPGA_RAG_SYSTEM_PROMPT.split("CONTEXT:")[0].strip()

        if llm_provider == "openai":
            resolved_key = api_key or os.environ.get("OPENAI_API_KEY", "")
            resolved_model = model_name or "gpt-4o-mini"
            if not resolved_key:
                if verbose:
                    print("[LLM] No OPENAI_API_KEY — skipping LLM call.")
            else:
                try:
                    from rag.openai_generator import OpenAIGenerator
                    gen = OpenAIGenerator(api_key=resolved_key, model_name=resolved_model)
                    if verbose:
                        print(f"[LLM] Provider: OpenAI ({resolved_model})")
                    llm_answer = gen.generate(
                        query=question,
                        context_documents=[context_str],
                        system_prompt=system,
                        temperature=0.3,
                    )
                except Exception as e:
                    if verbose:
                        print(f"[LLM] Error: {e}")
                    llm_answer = f"(LLM hatası: {e})"
        else:  # gemini
            resolved_key = api_key or os.environ.get("GOOGLE_API_KEY", "")
            resolved_model = model_name or "gemini-2.0-flash"
            if not resolved_key:
                if verbose:
                    print("[LLM] No GOOGLE_API_KEY — skipping LLM call.")
            else:
                try:
                    from rag.gemini_generator import GeminiGenerator
                    gen = GeminiGenerator(api_key=resolved_key, model_name=resolved_model)
                    if verbose:
                        print(f"[LLM] Provider: Gemini ({resolved_model})")
                    llm_answer = gen.generate(
                        query=question,
                        context_documents=[context_str],
                        system_prompt=system,
                        temperature=0.3,
                    )
                    if isinstance(llm_answer, dict):
                        llm_answer = llm_answer.get("answer", str(llm_answer))
                except Exception as e:
                    if verbose:
                        print(f"[LLM] Error: {e}")
                    llm_answer = f"(LLM hatası: {e})"
    else:
        # Return context only
        llm_answer = build_llm_context(query_result, gate_result)

    # Build response
    response = build_structured_response(
        query=question,
        query_result=query_result,
        gate_result=gate_result,
        llm_answer=llm_answer,
    )

    print("\n" + response["answer"])
    return response


# ---------------------------------------------------------------------------
# Stats display
# ---------------------------------------------------------------------------

def show_stats(graph_store: GraphStore, vector_store: VectorStoreV2) -> None:
    gs = graph_store.stats()
    vs = vector_store.stats()

    print("\n=== FPGA RAG v2 DB Stats ===")
    print(f"Graph nodes  : {gs['total_nodes']}")
    print(f"Graph edges  : {gs['total_edges']}")
    print(f"Vector docs  : {vs['count']}")
    print(f"Threshold    : {vs['threshold']}")

    print("\nNode types:")
    for nt, cnt in sorted(gs['node_types'].items()):
        print(f"  {nt:<22} {cnt}")

    print("\nEdge types:")
    for et, cnt in sorted(gs['edge_types'].items()):
        print(f"  {et:<28} {cnt}")

    gaps = graph_store.get_coverage_gaps()
    orphans = graph_store.get_orphan_components()
    print(f"\nCoverage gaps : {len(gaps)}")
    print(f"Orphan comps  : {len(orphans)}")
    if gaps:
        print("  Gap requirements:")
        for g in gaps:
            print(f"    - {g['node_id']}: {g.get('description','')[:60]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="FPGA RAG v2 — CLI Query Interface"
    )
    parser.add_argument("question", nargs="?", help="Question to ask")
    parser.add_argument("--type", choices=["What", "How", "Why", "Trace", "CrossRef"],
                        help="Force query type (default: auto-classify)")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Interactive mode")
    parser.add_argument("--stats", action="store_true",
                        help="Show DB stats and exit")
    parser.add_argument("--no-llm", action="store_true",
                        help="LLM çağrısını atla, yalnızca context döndür")
    parser.add_argument("--llm", choices=["openai", "gemini"], default="openai",
                        help="LLM sağlayıcı: openai (varsayılan) veya gemini")
    parser.add_argument("--model",
                        help="Model adı (openai: gpt-4o-mini, gpt-4o, gpt-4-turbo | gemini: gemini-2.0-flash)")
    parser.add_argument("--api-key",
                        help="API anahtarı (yoksa OPENAI_API_KEY / GOOGLE_API_KEY env'den okunur)")
    parser.add_argument("--graph-db", default=DEFAULT_GRAPH_DB)
    parser.add_argument("--chroma-dir", default=DEFAULT_CHROMA_DIR)
    parser.add_argument("--threshold", type=float, default=0.35)
    parser.add_argument("--n-results", type=int, default=5)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    verbose = not args.quiet

    # Init stores
    graph_store, vector_store = init_stores(args.graph_db, args.chroma_dir, args.threshold)
    router = QueryRouter(graph_store, vector_store, n_vector_results=args.n_results)
    gate = HallucinationGate(graph_store)

    # Stats mode
    if args.stats:
        show_stats(graph_store, vector_store)
        return

    use_llm = not args.no_llm

    # Interactive mode
    if args.interactive:
        print("\nFPGA RAG v2 — Interactive Mode")
        print("Komutlar: 'exit' çıkış, 'stats' istatistik, 'type:<What|How|Why|Trace|CrossRef> soru'")
        print("-" * 60)
        while True:
            try:
                line = input("\nSoru> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nÇıkılıyor...")
                break

            if not line:
                continue
            if line.lower() in ("exit", "quit", "q"):
                break
            if line.lower() == "stats":
                show_stats(graph_store, vector_store)
                continue

            # Parse inline type override
            qt_str = None
            if line.startswith("type:"):
                parts = line.split(" ", 1)
                qt_str = parts[0].split(":")[1]
                line = parts[1] if len(parts) > 1 else ""

            if line:
                run_query(line, router, gate, qt_str, use_llm,
                          llm_provider=args.llm, api_key=args.api_key,
                          model_name=args.model, verbose=verbose)
        return

    # Single question mode
    if args.question:
        run_query(args.question, router, gate, args.type, use_llm,
                  llm_provider=args.llm, api_key=args.api_key,
                  model_name=args.model, verbose=verbose)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
