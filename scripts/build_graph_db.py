#!/usr/bin/env python3
"""
Build Graph DB — FPGA RAG v2
Architecture ref: fpga_rag_architecture_v2.md §3 Phase 6

Loads pipeline_graph.json into:
  - GraphStore   → db/graph/fpga_rag_v2_graph.json
  - VectorStoreV2 → db/chroma_graph_nodes/ (collection: fpga_rag_v2_nodes)

Usage:
    python scripts/build_graph_db.py
    python scripts/build_graph_db.py --json data/fpga_rag_v2_output/pipeline_graph.json
    python scripts/build_graph_db.py --stats          # show DB stats only
    python scripts/build_graph_db.py --reset          # wipe and rebuild
"""

import argparse
import sys
from pathlib import Path

# Resolve project root
_PROJ_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJ_ROOT / "src"))

from rag_v2.graph_store import GraphStore
from rag_v2.vector_store_v2 import VectorStoreV2
from rag_v2.loader import PipelineGraphLoader


DEFAULT_JSON = str(_PROJ_ROOT / "data" / "fpga_rag_v2_output" / "pipeline_graph.json")
DEFAULT_GRAPH_DB = str(_PROJ_ROOT / "db" / "graph" / "fpga_rag_v2_graph.json")
DEFAULT_CHROMA_DIR = str(_PROJ_ROOT / "db" / "chroma_graph_nodes")


def print_stats(graph_store: GraphStore, vector_store: VectorStoreV2) -> None:
    gs = graph_store.stats()
    vs = vector_store.stats()

    print("\n=== Graph Store Stats ===")
    print(f"  Nodes     : {gs['total_nodes']}")
    print(f"  Edges     : {gs['total_edges']}")
    print(f"  Persist   : {gs['persist_path']}")
    print("\n  Node types:")
    for nt, cnt in sorted(gs['node_types'].items()):
        print(f"    {nt:<20} {cnt}")
    print("\n  Edge types:")
    for et, cnt in sorted(gs['edge_types'].items()):
        print(f"    {et:<25} {cnt}")

    print("\n=== Vector Store Stats ===")
    print(f"  Collection: {vs['collection']}")
    print(f"  Count     : {vs['count']}")
    print(f"  Threshold : {vs['threshold']}")
    print(f"  Persist   : {vs['persist_dir']}")

    # Anti-hallucination quick check
    gaps = graph_store.get_coverage_gaps()
    orphans = graph_store.get_orphan_components()
    contras = graph_store.get_contradictions()
    stale = graph_store.get_stale_node_ids()

    print("\n=== Anti-Hallucination Summary ===")
    print(f"  Coverage gaps (REQ without IMPLEMENTS): {len(gaps)}")
    print(f"  Orphan components (COMP without IMPL) : {len(orphans)}")
    print(f"  Contradictions                        : {len(contras)}")
    print(f"  Stale nodes (SUPERSEDED)              : {len(stale)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build FPGA RAG v2 Graph + Vector DB from pipeline_graph.json"
    )
    parser.add_argument(
        "--json", default=DEFAULT_JSON,
        help="Path to pipeline_graph.json"
    )
    parser.add_argument(
        "--graph-db", default=DEFAULT_GRAPH_DB,
        help="Path for GraphStore JSON file"
    )
    parser.add_argument(
        "--chroma-dir", default=DEFAULT_CHROMA_DIR,
        help="Directory for ChromaDB graph nodes"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.45,
        help="Cosine similarity threshold for vector search (default: 0.45)"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Show DB stats and exit (no loading)"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Delete existing DBs before loading"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress verbose output"
    )
    args = parser.parse_args()

    verbose = not args.quiet

    # Handle reset
    if args.reset:
        import shutil
        graph_path = Path(args.graph_db)
        chroma_path = Path(args.chroma_dir)
        if graph_path.exists():
            graph_path.unlink()
            print(f"[Reset] Deleted {graph_path}")
        if chroma_path.exists():
            shutil.rmtree(chroma_path)
            print(f"[Reset] Deleted {chroma_path}")

    # Initialize stores
    graph_store = GraphStore(persist_path=args.graph_db)
    vector_store = VectorStoreV2(persist_directory=args.chroma_dir, threshold=args.threshold)

    # Stats-only mode
    if args.stats:
        print_stats(graph_store, vector_store)
        return

    # Check if already populated
    if not args.reset and graph_store.stats()["total_nodes"] > 0:
        print(f"[Build] Graph DB already has {graph_store.stats()['total_nodes']} nodes.")
        print("[Build] Use --reset to rebuild from scratch.")
        print_stats(graph_store, vector_store)
        return

    # Load
    loader = PipelineGraphLoader(
        json_path=args.json,
        graph_store=graph_store,
        vector_store=vector_store,
    )

    print(f"\n[Build] Starting FPGA RAG v2 DB build")
    print(f"  Source : {args.json}")
    print(f"  Graph  : {args.graph_db}")
    print(f"  Chroma : {args.chroma_dir}")
    print(f"  Thresh : {args.threshold}")
    print()

    stats = loader.load(verbose=verbose)

    # Final stats
    print_stats(graph_store, vector_store)
    print("\n[Build] Done.")


if __name__ == "__main__":
    main()
