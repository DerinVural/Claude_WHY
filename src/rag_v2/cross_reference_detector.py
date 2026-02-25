"""
Cross-Reference Detector — Stage 5 of FPGA RAG v2 Pipeline

Automatically detects cross-project similarities, contradictions,
and pattern reuse between nodes from different projects.

4 detection modes:
  1. Structural similarity  → ANALOGOUS_TO (HIGH)    — same IP type / name pattern
  2. Problem similarity     → ANALOGOUS_TO (MEDIUM)  — similar ISSUE nodes (vector)
  3. Pattern reuse          → REUSES_PATTERN (MEDIUM) — COMPONENT uses known PATTERN
  4. Contradiction          → CONTRADICTS   (MEDIUM)  — opposing DECISION outcomes

Thresholds:
  Problem similarity:   cosine >= 0.80
  Contradiction:        cosine >= 0.85 + opposing language detection

Co-existence rule:
  Never overwrites edges whose source != "auto".

Usage:
  from rag_v2.cross_reference_detector import CrossReferenceDetector
  detector = CrossReferenceDetector(graph_store, vector_store)
  report = detector.run(apply=True)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .graph_store import GraphStore
from .vector_store_v2 import VectorStoreV2

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROBLEM_SIM_THRESHOLD    = 0.80
CONTRADICTION_THRESHOLD  = 0.85
MIN_BASE_NAME_LEN        = 4

# Generic component types that are too broad for structural matching
# (e.g. all custom RTL modules share "RTL_Module" — not meaningful)
_GENERIC_TYPES = {"rtl_module", "rtl_module_vhdl", "ip_core", "component", "module"}

# Vocabulary for contradiction detection
_POSITIVE_TERMS = {"seçildi", "kullanıldı", "tercih", "önerilir", "gerekli",
                   "zorunlu", "uygun", "selected", "preferred", "required"}
_NEGATIVE_TERMS = {"elendi", "reddedildi", "kullanılmaz", "önerilmez",
                   "gereksiz", "alternatif", "rejected", "eliminated", "unnecessary"}


# ---------------------------------------------------------------------------
# CrossReferenceDetector
# ---------------------------------------------------------------------------

class CrossReferenceDetector:
    """
    Detects cross-project relationships and writes them as edges
    (ANALOGOUS_TO, REUSES_PATTERN, CONTRADICTS) into GraphStore.
    """

    def __init__(self, graph_store: GraphStore, vector_store: VectorStoreV2) -> None:
        self.gs = graph_store
        self.vs = vector_store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, apply: bool = False) -> Dict[str, Any]:
        """
        Run all 4 detection modes.

        apply=True  → write edges to graph + save
        apply=False → dry-run; return detections without modifying graph
        """
        comps     = self.gs.get_nodes_by_type("COMPONENT")
        issues    = self.gs.get_nodes_by_type("ISSUE")
        decisions = self.gs.get_nodes_by_type("DECISION")
        patterns  = self.gs.get_nodes_by_type("PATTERN")

        print(f"[CrossReferenceDetector] COMPs={len(comps)}  ISSUEs={len(issues)}  "
              f"DECs={len(decisions)}  PATTERNs={len(patterns)}")

        # Mode 1: Structural similarity
        r1 = self._detect_structural(comps)
        print(f"  M1 structural     : {len(r1):3d} pairs")

        # Mode 2: Problem similarity
        r2 = self._detect_problem_similarity(issues)
        print(f"  M2 problem_sim    : {len(r2):3d} pairs")

        # Mode 3: Pattern reuse
        r3 = self._detect_pattern_reuse(comps, patterns)
        print(f"  M3 pattern_reuse  : {len(r3):3d} links")

        # Mode 4: Contradictions
        r4 = self._detect_contradictions(decisions)
        print(f"  M4 contradictions : {len(r4):3d} pairs")

        all_edges = r1 + r2 + r3 + r4
        print(f"  Total detections  : {len(all_edges):3d}")

        added = 0
        if apply:
            added = self._apply_edges(all_edges)
            self.gs.save()
            print(f"  Applied           : {added} new edges written to graph")

        return {
            "structural":        r1,
            "problem_similarity": r2,
            "pattern_reuse":     r3,
            "contradictions":    r4,
            "total":             len(all_edges),
            "applied":           added,
        }

    # ------------------------------------------------------------------
    # Mode 1 — Structural similarity
    # ------------------------------------------------------------------

    def _detect_structural(
        self, comps: List[Dict]
    ) -> List[Tuple[str, str, str, str, str]]:
        """
        Find COMPONENT pairs from different projects that share the same
        IP type or base name pattern.
        Returns list of (from_id, to_id, edge_type, confidence, evidence).
        """
        results: List[Tuple] = []
        seen_pairs: set = set()

        def add(c1: Dict, c2: Dict, confidence: str, evidence: str):
            if c1.get("project") == c2.get("project"):
                return
            pair = tuple(sorted([c1["node_id"], c2["node_id"]]))
            if pair in seen_pairs:
                return
            seen_pairs.add(pair)
            results.append((c1["node_id"], c2["node_id"], "ANALOGOUS_TO", confidence, evidence))

        # Group by IP type / vlnv
        by_type: Dict[str, List[Dict]] = {}
        for comp in comps:
            # Try to extract a normalised type key
            vlnv = comp.get("vlnv", "")
            ip_type = (
                comp.get("ip_type")
                or (vlnv.split(":")[2] if vlnv.count(":") >= 2 else None)
                or comp.get("component_type")
            )
            if ip_type:
                key = ip_type.lower()
                by_type.setdefault(key, []).append(comp)

        for key, group in by_type.items():
            if key.lower() in _GENERIC_TYPES:
                continue   # skip generic catch-all types
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    add(group[i], group[j], "HIGH", f"Same IP type: {key}")

        # Group by normalised base name
        # e.g. "axis2fifo — AXI-Stream..." → base "axis2fifo"
        by_base: Dict[str, List[Dict]] = {}
        for comp in comps:
            raw  = comp.get("name", comp["node_id"])
            base = raw.split("—")[0].strip().lower()
            base = re.sub(r'[\s_\-]+\d+$', '', base)   # remove trailing numbers
            if len(base) >= MIN_BASE_NAME_LEN:
                by_base.setdefault(base, []).append(comp)

        for base, group in by_base.items():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    add(group[i], group[j], "HIGH", f"Same base name: {base}")

        return results

    # ------------------------------------------------------------------
    # Mode 2 — Problem similarity
    # ------------------------------------------------------------------

    def _detect_problem_similarity(
        self, issues: List[Dict]
    ) -> List[Tuple[str, str, str, str, str]]:
        """
        Embed each ISSUE and query VectorStoreV2 for similar ISSUEs in
        other projects.  Only pairs with cosine >= PROBLEM_SIM_THRESHOLD.
        """
        results: List[Tuple] = []
        seen_pairs: set = set()

        for issue in issues:
            iid   = issue["node_id"]
            iprj  = issue.get("project")
            query = " ".join([
                str(issue.get("name",        "")),
                str(issue.get("description", "")),
                str(issue.get("summary",     "")),
            ])

            try:
                hits = self.vs.query(query, n_results=8, node_type_filter="ISSUE")
                for hit in hits:
                    oid = hit["node_id"]
                    if oid == iid:
                        continue
                    other = self.gs.get_node(oid)
                    if not other or other.get("project") == iprj:
                        continue
                    sim = hit.get("similarity", 0.0)
                    if sim < PROBLEM_SIM_THRESHOLD:
                        continue
                    pair = tuple(sorted([iid, oid]))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    results.append((
                        iid, oid, "ANALOGOUS_TO", "MEDIUM",
                        f"Problem similarity: {sim:.4f}",
                    ))
            except Exception:
                pass

        return results

    # ------------------------------------------------------------------
    # Mode 3 — Pattern reuse
    # ------------------------------------------------------------------

    def _detect_pattern_reuse(
        self, comps: List[Dict], patterns: List[Dict]
    ) -> List[Tuple[str, str, str, str, str]]:
        """
        Find COMPONENT nodes that exhibit the key behaviours described
        in PATTERN nodes.  Uses keyword overlap on key_logic / description.
        """
        results: List[Tuple] = []

        for pattern in patterns:
            pid = pattern["node_id"]

            # Build pattern keyword set from key_logic + description
            pat_text = " ".join([
                str(pattern.get("key_logic",   "")),
                str(pattern.get("description", "")),
                str(pattern.get("name",        "")),
            ]).lower()
            pat_words = {w for w in re.findall(r'\w+', pat_text) if len(w) >= 4}
            if len(pat_words) < 3:
                continue

            for comp in comps:
                cid = comp["node_id"]

                # Skip if edge already exists
                if self.gs.get_edge(cid, pid):
                    continue

                comp_text = " ".join([
                    str(comp.get("key_logic",   "")),
                    str(comp.get("description", "")),
                    str(comp.get("name",        "")),
                ]).lower()

                overlap = sum(1 for w in pat_words if w in comp_text)
                ratio   = overlap / len(pat_words)

                if overlap >= 3 and ratio >= 0.30:
                    results.append((
                        cid, pid, "REUSES_PATTERN", "MEDIUM",
                        f"Keyword overlap: {overlap}/{len(pat_words)} ({ratio:.0%})",
                    ))

        return results

    # ------------------------------------------------------------------
    # Mode 4 — Contradictions
    # ------------------------------------------------------------------

    def _detect_contradictions(
        self, decisions: List[Dict]
    ) -> List[Tuple[str, str, str, str, str]]:
        """
        Find DECISION pairs from different projects with:
          (a) high topic similarity (cosine >= CONTRADICTION_THRESHOLD), AND
          (b) opposing outcome language (one positive, one negative).
        """
        results: List[Tuple] = []
        seen_pairs: set = set()

        for dec in decisions:
            did  = dec["node_id"]
            dprj = dec.get("project")
            query = " ".join([
                str(dec.get("title",       "")),
                str(dec.get("description", "")),
            ])

            try:
                hits = self.vs.query(query, n_results=8, node_type_filter="DECISION")
                for hit in hits:
                    oid = hit["node_id"]
                    if oid == did:
                        continue
                    other = self.gs.get_node(oid)
                    if not other or other.get("project") == dprj:
                        continue
                    sim = hit.get("similarity", 0.0)
                    if sim < CONTRADICTION_THRESHOLD:
                        continue

                    dec_text   = str(dec.get("description",   "")).lower()
                    other_text = str(other.get("description", "")).lower()

                    dec_pos   = any(t in dec_text   for t in _POSITIVE_TERMS)
                    dec_neg   = any(t in dec_text   for t in _NEGATIVE_TERMS)
                    other_pos = any(t in other_text for t in _POSITIVE_TERMS)
                    other_neg = any(t in other_text for t in _NEGATIVE_TERMS)

                    is_contradiction = (
                        (dec_pos and other_neg) or (dec_neg and other_pos)
                    )
                    if not is_contradiction:
                        continue

                    pair = tuple(sorted([did, oid]))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    results.append((
                        did, oid, "CONTRADICTS", "MEDIUM",
                        f"Topic sim {sim:.4f} + opposing outcome language",
                    ))
            except Exception:
                pass

        return results

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def _apply_edges(
        self, edges: List[Tuple[str, str, str, str, str]]
    ) -> int:
        """
        Write detected edges to GraphStore.
        Co-existence rule: skip if edge already exists with source != "auto".
        """
        added = 0
        for from_id, to_id, edge_type, confidence, evidence in edges:
            existing = self.gs.get_edge(from_id, to_id)
            if existing is not None and existing.get("source") != "auto":
                continue  # preserve manual edges
            try:
                self.gs.add_edge(
                    from_id, to_id, edge_type,
                    attrs={
                        "confidence":    confidence,
                        "source":        "auto",
                        "match_evidence": evidence,
                    },
                )
                added += 1
            except Exception as exc:
                print(f"  [WARN] Could not add edge {from_id}→{to_id}: {exc}")
        return added
