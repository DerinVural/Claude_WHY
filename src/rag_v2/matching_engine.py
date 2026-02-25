"""
Matching Engine — Stage 4 of FPGA RAG v2 Pipeline

Automatically links REQUIREMENT nodes to COMPONENT/EVIDENCE/CONSTRAINT nodes.

5 strategies (in priority order):
  1. Name/Identifier match    → IMPLEMENTS    (HIGH)
  2. Semantic match            → IMPLEMENTS    (MEDIUM)
  3. Structural inference      → IMPLEMENTS    (MEDIUM, indirect via DEPENDS_ON)
  4. Evidence binding          → VERIFIED_BY   (HIGH)
  5. Constraint binding        → CONSTRAINED_BY (HIGH)

Thresholds (conservative — high precision, lower recall):
  Semantic:    cosine >= 0.75
  Structural:  follow DEPENDS_ON up to depth 2

Co-existence rule:
  Never overwrites an edge whose source != "auto".
  Manual edges are always preserved.

Usage:
  from rag_v2.matching_engine import MatchingEngine
  engine = MatchingEngine(graph_store, vector_store, llm=claude_generator)
  report = engine.run(apply=True)
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .graph_store import GraphStore
from .vector_store_v2 import VectorStoreV2

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEMANTIC_THRESHOLD = 0.75      # cosine similarity for strategy 2
STRUCTURAL_DEPTH   = 2         # DEPENDS_ON hops for strategy 3
MIN_TERM_LEN       = 4         # minimum character length for name matching

_CONF_RANK = {"HIGH": 2, "MEDIUM": 1, "PARSE_UNCERTAIN": 0}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    req_id:    str
    target_id: str
    edge_type: str
    strategy:  str
    confidence: str
    evidence:  List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (f"Match({self.req_id} →[{self.edge_type}/{self.confidence}]→ "
                f"{self.target_id}  via {self.strategy})")


# ---------------------------------------------------------------------------
# MatchingEngine
# ---------------------------------------------------------------------------

class MatchingEngine:
    """
    Runs 5 matching strategies between REQUIREMENT nodes and
    COMPONENT / EVIDENCE / CONSTRAINT nodes, then writes the
    resulting edges into GraphStore.
    """

    def __init__(
        self,
        graph_store: GraphStore,
        vector_store: VectorStoreV2,
        llm=None,
    ) -> None:
        self.gs  = graph_store
        self.vs  = vector_store
        self.llm = llm  # Optional: for LLM-based criteria parsing (strategy 4)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, apply: bool = False) -> Dict[str, Any]:
        """
        Run all 5 strategies.

        apply=True  → write new edges to graph + save
        apply=False → dry-run; return matches without modifying graph
        """
        reqs        = self.gs.get_nodes_by_type("REQUIREMENT")
        comps       = self.gs.get_nodes_by_type("COMPONENT")
        evidences   = self.gs.get_nodes_by_type("EVIDENCE")
        constraints = self.gs.get_nodes_by_type("CONSTRAINT")

        print(f"[MatchingEngine] REQs={len(reqs)}  COMPs={len(comps)}  "
              f"EVIDs={len(evidences)}  CONSTRs={len(constraints)}")

        # --- Strategy 1: name/identifier ---
        s1 = self._strategy_1_name(reqs, comps)
        print(f"  S1 name_match    : {len(s1):3d} matches")

        # --- Strategy 2: semantic ---
        s2 = self._strategy_2_semantic(reqs)
        print(f"  S2 semantic      : {len(s2):3d} matches")

        # --- Strategy 3: structural (via S1+S2 anchors) ---
        s3 = self._strategy_3_structural(reqs, s1 + s2)
        print(f"  S3 structural    : {len(s3):3d} matches")

        # --- Strategy 4: evidence binding ---
        s4 = self._strategy_4_evidence(reqs, evidences)
        print(f"  S4 evidence_bind : {len(s4):3d} matches")

        # --- Strategy 5: constraint binding ---
        s5 = self._strategy_5_constraint(reqs, constraints)
        print(f"  S5 constraint    : {len(s5):3d} matches")

        all_matches = self._deduplicate(s1 + s2 + s3 + s4 + s5)
        print(f"  Deduplicated     : {len(all_matches):3d} unique matches")

        gaps    = self._find_coverage_gaps(reqs, all_matches)
        orphans = self._find_orphan_components(comps, all_matches)
        print(f"  Coverage gaps    : {len(gaps)} REQs without IMPLEMENTS")
        print(f"  Orphan COMPs     : {len(orphans)} COMPs without IMPLEMENTS")

        added = 0
        if apply:
            added = self._apply_matches(all_matches)
            self.gs.save()
            print(f"  Applied          : {added} new edges written to graph")

        return {
            "matches":            all_matches,
            "coverage_gaps":      gaps,
            "orphan_components":  orphans,
            "total_matches":      len(all_matches),
            "applied":            added,
        }

    # ------------------------------------------------------------------
    # Strategy 1 — Name / Identifier match
    # ------------------------------------------------------------------

    def _strategy_1_name(
        self, reqs: List[Dict], comps: List[Dict]
    ) -> List[MatchResult]:
        """
        Extract technical identifiers from REQ text and match against
        COMPONENT names, node_ids, and source_file names.
        Only cross-checks within the same project.
        """
        # Build term → comp_id lookup (normalized to lowercase)
        term_to_comp: Dict[str, str] = {}
        for comp in comps:
            cid  = comp["node_id"]
            name = comp.get("name", "")
            src  = comp.get("source_file", "")

            candidates = [
                cid,
                name.lower(),
                name.split("—")[0].strip().lower(),
                # strip path prefix and extension from source_file
                re.sub(r'^.*/', '', src).replace(".v", "").replace(".c", "").lower(),
            ]
            for term in candidates:
                if term and len(term) >= MIN_TERM_LEN:
                    term_to_comp[term] = cid
                # also index underscore-split parts (e.g. "axis2fifo" from "COMP-A-axis2fifo_0")
                for part in re.split(r'[-_]', term):
                    if len(part) >= MIN_TERM_LEN:
                        term_to_comp.setdefault(part, cid)

        results: List[MatchResult] = []
        for req in reqs:
            rid  = req["node_id"]
            rprj = req.get("project")
            text = " ".join([
                str(req.get("title",              "")),
                str(req.get("name",               "")),
                str(req.get("description",        "")),
                str(req.get("acceptance_criteria","")),
            ]).lower()

            seen_comp_ids: set = set()
            for term, cid in term_to_comp.items():
                if cid in seen_comp_ids:
                    continue
                comp_node = self.gs.get_node(cid)
                if comp_node and comp_node.get("project") != rprj:
                    continue   # different project — skip
                if term in text:
                    seen_comp_ids.add(cid)
                    results.append(MatchResult(
                        req_id=rid, target_id=cid,
                        edge_type="IMPLEMENTS", strategy="name_match",
                        confidence="HIGH",
                        evidence=[f"Term '{term}' found in REQ text"],
                    ))

        return results

    # ------------------------------------------------------------------
    # Strategy 2 — Semantic match
    # ------------------------------------------------------------------

    def _strategy_2_semantic(self, reqs: List[Dict]) -> List[MatchResult]:
        """
        Embed each REQ's text and query VectorStoreV2 for similar COMPONENT nodes.
        Only matches with cosine >= SEMANTIC_THRESHOLD are kept.
        """
        results: List[MatchResult] = []
        for req in reqs:
            rid     = req["node_id"]
            project = req.get("project")
            query   = " ".join([
                str(req.get("title",              "")),
                str(req.get("description",        "")),
                str(req.get("acceptance_criteria","")),
            ])
            try:
                hits = self.vs.query(
                    query,
                    n_results=5,
                    node_type_filter="COMPONENT",
                    project_filter=project,
                )
                for hit in hits:
                    sim = hit.get("similarity", 0.0)
                    if sim >= SEMANTIC_THRESHOLD:
                        results.append(MatchResult(
                            req_id=rid, target_id=hit["node_id"],
                            edge_type="IMPLEMENTS", strategy="semantic",
                            confidence="MEDIUM",
                            evidence=[f"Cosine similarity: {sim:.4f}"],
                        ))
            except Exception:
                pass
        return results

    # ------------------------------------------------------------------
    # Strategy 3 — Structural inference (DEPENDS_ON traversal)
    # ------------------------------------------------------------------

    def _strategy_3_structural(
        self,
        reqs: List[Dict],
        prior_matches: List[MatchResult],
    ) -> List[MatchResult]:
        """
        For each REQ, follow DEPENDS_ON edges from already-matched COMPs
        (anchors from S1+S2) up to STRUCTURAL_DEPTH hops.
        Transitive dependencies are added as indirect IMPLEMENTS (MEDIUM).
        """
        # Group prior anchor comp_ids per req_id
        req_anchors: Dict[str, set] = defaultdict(set)
        for m in prior_matches:
            if m.edge_type == "IMPLEMENTS":
                req_anchors[m.req_id].add(m.target_id)

        results: List[MatchResult] = []

        for req in reqs:
            rid     = req["node_id"]
            rprj    = req.get("project")
            anchors = req_anchors.get(rid, set())
            if not anchors:
                continue

            # BFS over DEPENDS_ON from all anchors
            visited:    set = set(anchors)
            queue:      list = [(cid, 0) for cid in anchors]
            transitive: set = set()

            while queue:
                current, depth = queue.pop(0)
                if depth >= STRUCTURAL_DEPTH:
                    continue
                for dep_id, _ in self.gs.get_neighbors(current, edge_type="DEPENDS_ON"):
                    if dep_id not in visited:
                        visited.add(dep_id)
                        transitive.add(dep_id)
                        queue.append((dep_id, depth + 1))

            for trans_cid in transitive:
                comp_node = self.gs.get_node(trans_cid)
                if not comp_node:
                    continue
                if comp_node.get("project") != rprj:
                    continue
                results.append(MatchResult(
                    req_id=rid, target_id=trans_cid,
                    edge_type="IMPLEMENTS", strategy="structural_indirect",
                    confidence="MEDIUM",
                    evidence=[f"Transitive DEPENDS_ON from anchor(s): {list(anchors)[:2]}"],
                ))

        return results

    # ------------------------------------------------------------------
    # Strategy 4 — Evidence binding
    # ------------------------------------------------------------------

    def _strategy_4_evidence(
        self, reqs: List[Dict], evidences: List[Dict]
    ) -> List[MatchResult]:
        """
        Parse acceptance_criteria (via LLM if available, else keyword fallback)
        into structured metrics, then match EVIDENCE nodes that contain
        those metrics in their text.
        """
        results: List[MatchResult] = []

        for req in reqs:
            rid      = req["node_id"]
            rprj     = req.get("project")
            criteria = req.get("acceptance_criteria", "")
            if not criteria:
                continue

            structured = self._parse_acceptance_criteria(criteria)
            if not structured:
                continue

            metric_terms = [c["metric"].lower() for c in structured
                            if c.get("metric") and len(c["metric"]) >= 3]
            if not metric_terms:
                continue

            for evid in evidences:
                eid   = evid["node_id"]
                eprj  = evid.get("project")
                if eprj and eprj != rprj:
                    continue

                evid_text = " ".join([
                    str(evid.get("description", "")),
                    str(evid.get("summary",     "")),
                    str(evid.get("key_logic",   "")),
                    str(evid.get("name",        "")),
                ]).lower()

                matched = [m for m in metric_terms if m in evid_text]
                if matched:
                    results.append(MatchResult(
                        req_id=rid, target_id=eid,
                        edge_type="VERIFIED_BY", strategy="evidence_bind",
                        confidence="HIGH",
                        evidence=[f"Criteria metrics in evidence text: {matched}"],
                    ))

        return results

    def _parse_acceptance_criteria(self, raw) -> List[Dict[str, Any]]:
        """
        Parse acceptance_criteria (string or JSON list) into structured
        metric dicts: [{metric, operator, value, unit, original, PARSE_UNCERTAIN?}]

        Uses LLM if available, otherwise falls back to keyword extraction.
        """
        # Normalise to list of strings
        if isinstance(raw, str):
            try:
                items = json.loads(raw)
                if not isinstance(items, list):
                    items = [raw]
            except json.JSONDecodeError:
                items = [raw]
        elif isinstance(raw, list):
            items = [str(i) for i in raw]
        else:
            items = [str(raw)]

        if self.llm:
            return self._llm_parse_criteria(items)
        return self._keyword_parse_criteria(items)

    def _llm_parse_criteria(self, criteria_list: List[str]) -> List[Dict]:
        """Use LLM to extract metric/operator/value tuples from criteria text."""
        text = "\n".join(f"- {c}" for c in criteria_list)
        prompt = (
            "Aşağıdaki kabul kriterlerinden ölçülebilir metrikleri çıkar.\n"
            "Yanıt formatı — sadece JSON array, başka metin yazma:\n"
            "[\n"
            '  {"metric": "WNS", "operator": ">=", "value": "0", "unit": "ns", "original": "..."},\n'
            '  {"metric": "utilization", "operator": "<=", "value": "80", "unit": "%", "original": "..."},\n'
            '  {"metric": "latency", "operator": "minimize", "value": null, "unit": null, "original": "..."}\n'
            "]\n"
            "Eğer bir kriterden metrik çıkaramazsan 'PARSE_UNCERTAIN': true ekle.\n\n"
            f"Kriterler:\n{text}"
        )
        try:
            response = self.llm.generate(prompt, context_documents=[], temperature=0.1)
            m = re.search(r'\[.*?\]', response, re.DOTALL)
            if m:
                parsed = json.loads(m.group())
                if isinstance(parsed, list):
                    return parsed
        except Exception:
            pass
        return self._keyword_parse_criteria(criteria_list)

    def _keyword_parse_criteria(self, criteria_list: List[str]) -> List[Dict]:
        """Keyword-based metric extraction fallback (no LLM)."""
        keywords = [
            "wns", "tns", "timing", "utilization", "lut", "ff", "bram",
            "clock", "frequency", "mhz", "latency", "throughput",
            "drc", "power", "bandwidth", "fifo", "dma", "audio",
            "pwm", "sample", "rate", "period", "setup", "hold",
        ]
        results = []
        for crit in criteria_list:
            low = crit.lower()
            for kw in keywords:
                if kw in low:
                    results.append({"metric": kw, "original": crit})
                    break
        return results

    # ------------------------------------------------------------------
    # Strategy 5 — Constraint binding
    # ------------------------------------------------------------------

    def _strategy_5_constraint(
        self, reqs: List[Dict], constraints: List[Dict]
    ) -> List[MatchResult]:
        """
        Match REQ constraints/requirements to CONSTRAINT nodes by
        shared technical category keywords.
        """
        categories: Dict[str, List[str]] = {
            "timing":    ["timing", "clock", "period", "wns", "setup", "hold", "mhz"],
            "pin":       ["pin", "package_pin", "iostandard", "loc", "xdc"],
            "power":     ["power", "current", "voltage", "supply"],
            "interface": ["axi", "protocol", "interface", "bus", "stream"],
        }

        results: List[MatchResult] = []

        for req in reqs:
            rid  = req["node_id"]
            rprj = req.get("project")
            req_text = " ".join([
                str(req.get("description",        "")),
                str(req.get("acceptance_criteria","")),
                str(req.get("title",              "")),
            ]).lower()

            for cons in constraints:
                cid  = cons["node_id"]
                cprj = cons.get("project")
                if cprj and cprj != rprj:
                    continue

                cons_text = " ".join([
                    str(cons.get("description", "")),
                    str(cons.get("summary",     "")),
                    str(cons.get("spec",        "")),
                    str(cons.get("key_logic",   "")),
                ]).lower()

                for cat, kws in categories.items():
                    req_has  = any(kw in req_text  for kw in kws)
                    cons_has = any(kw in cons_text for kw in kws)
                    if req_has and cons_has:
                        results.append(MatchResult(
                            req_id=rid, target_id=cid,
                            edge_type="CONSTRAINED_BY", strategy="constraint_bind",
                            confidence="HIGH",
                            evidence=[f"Shared constraint category: {cat}"],
                        ))
                        break   # one match per (req, constraint) pair is enough

        return results

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _deduplicate(self, matches: List[MatchResult]) -> List[MatchResult]:
        """
        Keep one MatchResult per (req_id, target_id, edge_type).
        When duplicates exist, prefer higher confidence.
        """
        best: Dict[tuple, MatchResult] = {}
        for m in matches:
            key = (m.req_id, m.target_id, m.edge_type)
            if key not in best:
                best[key] = m
            elif _CONF_RANK.get(m.confidence, 0) > _CONF_RANK.get(best[key].confidence, 0):
                best[key] = m
        return list(best.values())

    # ------------------------------------------------------------------
    # Coverage / orphan helpers
    # ------------------------------------------------------------------

    def _find_coverage_gaps(
        self, reqs: List[Dict], matches: List[MatchResult]
    ) -> List[str]:
        """REQ node_ids that have no IMPLEMENTS (auto or manual)."""
        covered: set = {m.req_id for m in matches if m.edge_type == "IMPLEMENTS"}
        for req in reqs:
            rid = req["node_id"]
            # Check existing manual IMPLEMENTS (incoming to REQ)
            if self.gs.get_neighbors(rid, edge_type="IMPLEMENTS", direction="in"):
                covered.add(rid)
        return [r["node_id"] for r in reqs if r["node_id"] not in covered]

    def _find_orphan_components(
        self, comps: List[Dict], matches: List[MatchResult]
    ) -> List[str]:
        """COMPONENT node_ids that have no IMPLEMENTS (auto or manual)."""
        linked: set = {m.target_id for m in matches if m.edge_type == "IMPLEMENTS"}
        for comp in comps:
            cid = comp["node_id"]
            if self.gs.get_neighbors(cid, edge_type="IMPLEMENTS", direction="out"):
                linked.add(cid)
        return [c["node_id"] for c in comps if c["node_id"] not in linked]

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def _apply_matches(self, matches: List[MatchResult]) -> int:
        """
        Write matches to GraphStore as edges.
        Co-existence rule: skip if an edge already exists with source != "auto"
        (i.e. never overwrite a manually created edge).
        """
        added = 0
        for m in matches:
            existing = self.gs.get_edge(m.req_id, m.target_id)
            if existing is not None:
                # Preserve manual edges; only overwrite previous auto-edges
                if existing.get("source") != "auto":
                    continue
            try:
                self.gs.add_edge(
                    m.req_id, m.target_id, m.edge_type,
                    attrs={
                        "confidence":    m.confidence,
                        "source":        "auto",
                        "strategy":      m.strategy,
                        "match_evidence": m.evidence,
                    },
                )
                added += 1
            except Exception as exc:
                print(f"  [WARN] Could not add edge {m.req_id}→{m.target_id}: {exc}")
        return added
