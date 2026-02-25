"""
scripts/run_matching.py — Stage 4: Automatic Matching Engine

Usage:
  source .venv/bin/activate

  # Dry-run (no changes):
  python scripts/run_matching.py

  # Apply matches to graph:
  python scripts/run_matching.py --apply

  # Show coverage gaps and orphans only:
  python scripts/run_matching.py --report

  # Use Claude LLM for acceptance_criteria parsing:
  python scripts/run_matching.py --apply --llm
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from rag_v2.graph_store    import GraphStore
from rag_v2.vector_store_v2 import VectorStoreV2
from rag_v2.matching_engine import MatchingEngine


def main():
    parser = argparse.ArgumentParser(description="FPGA RAG v2 — Stage 4 Matching Engine")
    parser.add_argument("--apply",  action="store_true", help="Write edges to graph (default: dry-run)")
    parser.add_argument("--report", action="store_true", help="Print coverage gaps and orphan components")
    parser.add_argument("--llm",    action="store_true", help="Use Claude LLM for criteria parsing")
    args = parser.parse_args()

    print("=" * 60)
    print("  FPGA RAG v2 — Stage 4: Matching Engine")
    print(f"  Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print("=" * 60)

    # Load stores
    print("\n[1] Loading stores...")
    gs = GraphStore()
    vs = VectorStoreV2()
    print(f"  Graph: {gs.stats()['total_nodes']} nodes, {gs.stats()['total_edges']} edges")

    # Optional LLM
    llm = None
    if args.llm:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key and not api_key.startswith("your-"):
            from rag.claude_generator import ClaudeGenerator
            llm = ClaudeGenerator(api_key=api_key, model_name="claude-haiku-4-5-20251001")
            print("  LLM: Claude Haiku (for criteria parsing)")
        else:
            print("  LLM: not available (ANTHROPIC_API_KEY missing), using keyword fallback")

    # Run engine
    print("\n[2] Running matching strategies...")
    engine = MatchingEngine(gs, vs, llm=llm)
    report = engine.run(apply=args.apply)

    # Summary
    print("\n[3] Results")
    print(f"  Total matches    : {report['total_matches']}")
    if args.apply:
        print(f"  Edges written    : {report['applied']}")
        new_stats = gs.stats()
        print(f"  Graph now        : {new_stats['total_nodes']} nodes, {new_stats['total_edges']} edges")

    if args.report or not args.apply:
        print(f"\n  Coverage gaps ({len(report['coverage_gaps'])} REQs without IMPLEMENTS):")
        for rid in report['coverage_gaps'][:20]:
            print(f"    - {rid}")
        if len(report['coverage_gaps']) > 20:
            print(f"    ... and {len(report['coverage_gaps']) - 20} more")

        print(f"\n  Orphan components ({len(report['orphan_components'])} COMPs without IMPLEMENTS):")
        for cid in report['orphan_components'][:20]:
            print(f"    - {cid}")
        if len(report['orphan_components']) > 20:
            print(f"    ... and {len(report['orphan_components']) - 20} more")

    if not args.apply:
        print("\n  (Dry-run: no changes written. Use --apply to apply.)")

    print("\nDone.")


if __name__ == "__main__":
    main()
