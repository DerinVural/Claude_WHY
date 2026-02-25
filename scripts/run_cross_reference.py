"""
scripts/run_cross_reference.py — Stage 5: Cross-Reference Detector

Usage:
  source .venv/bin/activate

  # Dry-run (no changes):
  python scripts/run_cross_reference.py

  # Apply detected edges to graph:
  python scripts/run_cross_reference.py --apply

  # Show only contradictions:
  python scripts/run_cross_reference.py --contradictions-only
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from rag_v2.graph_store             import GraphStore
from rag_v2.vector_store_v2          import VectorStoreV2
from rag_v2.cross_reference_detector import CrossReferenceDetector


def _print_edges(label: str, edges: list, max_show: int = 15):
    print(f"\n  {label} ({len(edges)}):")
    for item in edges[:max_show]:
        from_id, to_id, edge_type, conf, evidence = item
        print(f"    {from_id} →[{edge_type}/{conf}]→ {to_id}")
        print(f"      evidence: {evidence}")
    if len(edges) > max_show:
        print(f"    ... and {len(edges) - max_show} more")


def main():
    parser = argparse.ArgumentParser(description="FPGA RAG v2 — Stage 5 Cross-Reference Detector")
    parser.add_argument("--apply",               action="store_true", help="Write edges to graph")
    parser.add_argument("--contradictions-only",  action="store_true", help="Show only contradictions")
    args = parser.parse_args()

    print("=" * 60)
    print("  FPGA RAG v2 — Stage 5: Cross-Reference Detector")
    print(f"  Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print("=" * 60)

    print("\n[1] Loading stores...")
    gs = GraphStore()
    vs = VectorStoreV2()
    before = gs.stats()
    print(f"  Graph: {before['total_nodes']} nodes, {before['total_edges']} edges")

    print("\n[2] Running detection modes...")
    detector = CrossReferenceDetector(gs, vs)
    report   = detector.run(apply=args.apply)

    print("\n[3] Results")
    if args.contradictions_only:
        _print_edges("Contradictions", report["contradictions"])
    else:
        _print_edges("Structural similarity (ANALOGOUS_TO)", report["structural"])
        _print_edges("Problem similarity   (ANALOGOUS_TO)", report["problem_similarity"])
        _print_edges("Pattern reuse        (REUSES_PATTERN)", report["pattern_reuse"])
        _print_edges("Contradictions       (CONTRADICTS)",    report["contradictions"])

    print(f"\n  Total detections : {report['total']}")
    if args.apply:
        after = gs.stats()
        print(f"  Edges written    : {report['applied']}")
        print(f"  Graph now        : {after['total_nodes']} nodes, {after['total_edges']} edges")
        new_et = after['edge_types']
        for et in ("ANALOGOUS_TO", "REUSES_PATTERN", "CONTRADICTS"):
            print(f"    {et}: {new_et.get(et, 0)}")
    else:
        print("\n  (Dry-run: no changes written. Use --apply to apply.)")

    print("\nDone.")


if __name__ == "__main__":
    main()
