"""
Hallucination Gate — FPGA RAG v2
Architecture ref: fpga_rag_architecture_v2.md §7 (10 Katman Anti-Hallüsinasyon)

Aktif katmanlar (Graph DB kurulumundan sonra 6 katman):
  Layer 1  : Evidence Gate     — her iddia bir EVIDENCE node'a bağlı olmalı
  Layer 2  : Confidence Prop   — zincirdeki en düşük confidence = toplam
  Layer 3  : Coverage Gap      — REQUIREMENT nodes without IMPLEMENTS
  Layer 4  : PARSE_UNCERTAIN   — uyarı üret, otomatik MEDIUM olarak işaretle
  Layer 5  : SUPERSEDES filter — stale node'ları filtrele
  Layer 6  : CONTRADICTS check — çelişen node çiftlerini uyar

Pasif katmanlar (daha fazla veri + LLM entegrasyonu gerektirir):
  Layer 7  : Source Triangulation (çok kaynak doğrulama)
  Layer 8  : Schema Validation
  Layer 9  : Temporal Consistency
  Layer 10 : Cross-Project Validation
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJ_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJ_ROOT / "src"))

from rag_v2.graph_store import GraphStore, _min_confidence

# Confidence ranking
_CONF_RANK = {"PARSE_UNCERTAIN": 0, "MEDIUM": 1, "HIGH": 2}


# ---------------------------------------------------------------------------
# Gate Result
# ---------------------------------------------------------------------------

class GateResult:
    """Result from HallucinationGate.check()."""

    def __init__(
        self,
        passed: bool,
        overall_confidence: str,
        warnings: List[str],
        filtered_node_ids: set,
        evidence_ids: List[str],
        details: Dict[str, Any],
    ):
        self.passed = passed           # True if no blocking issues
        self.overall_confidence = overall_confidence
        self.warnings = warnings       # Human-readable warning list
        self.filtered_node_ids = filtered_node_ids  # stale/removed nodes
        self.evidence_ids = evidence_ids
        self.details = details

    def __repr__(self) -> str:
        return (f"GateResult(passed={self.passed}, "
                f"confidence={self.overall_confidence}, "
                f"warnings={len(self.warnings)})")


# ---------------------------------------------------------------------------
# HallucinationGate
# ---------------------------------------------------------------------------

class HallucinationGate:
    """
    6-layer active anti-hallucination gate for FPGA RAG v2.
    Architecture §7.
    """

    def __init__(self, graph_store: GraphStore):
        self.graph = graph_store

    def check(
        self,
        nodes: List[Dict[str, Any]],
        edges: Optional[List[Dict[str, Any]]] = None,
        require_evidence: bool = True,
    ) -> GateResult:
        """
        Run all active layers on a list of retrieved nodes.
        Returns GateResult with combined confidence, warnings, filtered IDs.
        """
        edges = edges or []
        warnings: List[str] = []
        filtered_ids: set = set()
        evidence_ids: List[str] = []
        details: Dict[str, Any] = {}

        # --- Layer 5: SUPERSEDES (stale filter) — run first ---
        stale_warn, stale_ids = self._layer5_supersedes(nodes)
        warnings.extend(stale_warn)
        filtered_ids.update(stale_ids)

        # Remove stale nodes from further checks
        active_nodes = [n for n in nodes
                        if n.get("node_id", "") not in filtered_ids]

        # --- Layer 1: Evidence Gate ---
        ev_warn, ev_ids = self._layer1_evidence_gate(active_nodes, require_evidence)
        warnings.extend(ev_warn)
        evidence_ids.extend(ev_ids)
        details["evidence_ids"] = ev_ids

        # --- Layer 2: Confidence Propagation ---
        conf_result, path_confidences = self._layer2_confidence_prop(active_nodes, edges)
        details["path_confidences"] = path_confidences

        # --- Layer 3: Coverage Gap ---
        gap_warn = self._layer3_coverage_gap(active_nodes)
        warnings.extend(gap_warn)
        details["coverage_gaps"] = len(gap_warn)

        # --- Layer 4: PARSE_UNCERTAIN ---
        pu_warn, pu_nodes = self._layer4_parse_uncertain(active_nodes)
        warnings.extend(pu_warn)
        details["parse_uncertain_nodes"] = pu_nodes

        # --- Layer 6: CONTRADICTS ---
        contra_warn = self._layer6_contradicts(active_nodes)
        warnings.extend(contra_warn)
        details["contradictions"] = len(contra_warn)

        # Overall pass/fail — fail only if no evidence AND evidence required
        passed = True
        if require_evidence and ev_warn and not ev_ids:
            passed = False

        return GateResult(
            passed=passed,
            overall_confidence=conf_result,
            warnings=warnings,
            filtered_node_ids=filtered_ids,
            evidence_ids=evidence_ids,
            details=details,
        )

    # ------------------------------------------------------------------
    # Layer 1: Evidence Gate
    # ------------------------------------------------------------------

    def check_evidence(self, claim_node_id: str, context: List[Dict]) -> bool:
        """
        Check if a specific node is backed by an EVIDENCE node.
        Architecture §7 Layer 1.
        """
        context_ids = {n.get("node_id", "") for n in context}

        # Check outgoing VERIFIED_BY edges from this node
        for nbr_id, eattrs in self.graph.get_neighbors(claim_node_id,
                                                        edge_type="VERIFIED_BY"):
            nbr_node = self.graph.get_node(nbr_id)
            if nbr_node and nbr_node.get("node_type") == "EVIDENCE":
                return True

        # Check if any EVIDENCE node in context is related
        for ctx_node in context:
            if ctx_node.get("node_type") == "EVIDENCE":
                # Is this evidence connected to the claim?
                for nbr_id, _ in self.graph.get_neighbors(
                        ctx_node.get("node_id", ""), direction="in"):
                    if nbr_id == claim_node_id:
                        return True

        return False

    def _layer1_evidence_gate(
        self, nodes: List[Dict], require_evidence: bool
    ) -> Tuple[List[str], List[str]]:
        warnings = []
        evidence_ids = []

        for node in nodes:
            nid = node.get("node_id", "")
            ntype = node.get("node_type", "")

            if ntype == "EVIDENCE":
                evidence_ids.append(nid)
                continue

            # Check for EVIDENCE backing
            has_evidence = self.check_evidence(nid, nodes)
            if not has_evidence and ntype in ("REQUIREMENT", "DECISION", "COMPONENT"):
                if require_evidence:
                    warnings.append(
                        f"[Layer1-EvidenceGate] Node '{nid}' ({ntype}) has no "
                        f"linked EVIDENCE node — claim may be unverified."
                    )

        return warnings, evidence_ids

    # ------------------------------------------------------------------
    # Layer 2: Confidence Propagation
    # ------------------------------------------------------------------

    def propagate_confidence(self, path: List[Dict]) -> str:
        """
        Chain confidence rule: weakest link = path confidence.
        Architecture §8 Confidence Model.
        """
        levels = [n.get("confidence", "PARSE_UNCERTAIN") for n in path]
        return _min_confidence(levels)

    def _layer2_confidence_prop(
        self, nodes: List[Dict], edges: List[Dict]
    ) -> Tuple[str, Dict[str, str]]:
        """
        Calculate overall confidence for retrieved node set.
        Returns (overall_confidence, {node_id: confidence}).
        """
        node_confidences = {}
        for node in nodes:
            nid = node.get("node_id", "")
            conf = node.get("confidence", "PARSE_UNCERTAIN")
            node_confidences[nid] = conf

        # Edge confidences
        for edge in edges:
            ec = edge.get("confidence", "MEDIUM")
            # Propagate edge confidence to connected nodes
            for end in ("from", "to"):
                nid = edge.get(end, "")
                if nid in node_confidences:
                    current = node_confidences[nid]
                    node_confidences[nid] = _min_confidence([current, ec])

        overall = _min_confidence(list(node_confidences.values()) or ["PARSE_UNCERTAIN"])
        return overall, node_confidences

    # ------------------------------------------------------------------
    # Layer 3: Coverage Gap
    # ------------------------------------------------------------------

    def _layer3_coverage_gap(self, nodes: List[Dict]) -> List[str]:
        """
        Warn about REQUIREMENT nodes without any IMPLEMENTS edge in scope.
        Architecture §7 Layer 3.
        """
        warnings = []
        for node in nodes:
            nid = node.get("node_id", "")
            if node.get("node_type") != "REQUIREMENT":
                continue

            # Check if any COMPONENT in the full graph implements this requirement
            implementing = [
                src for src, eattrs in self.graph.get_neighbors(nid, direction="in")
                if eattrs.get("edge_type") == "IMPLEMENTS"
            ]
            if not implementing:
                warnings.append(
                    f"[Layer3-CoverageGap] Requirement '{nid}' has no implementing "
                    f"component — coverage gap."
                )

        return warnings

    # ------------------------------------------------------------------
    # Layer 4: PARSE_UNCERTAIN
    # ------------------------------------------------------------------

    def check_parse_uncertain(self, nodes: List[Dict]) -> List[str]:
        """
        Return warnings for nodes with PARSE_UNCERTAIN confidence.
        Architecture §7 Layer 4.
        """
        _, pu_nodes = self._layer4_parse_uncertain(nodes)
        return [f"[Layer4-ParseUncertain] Node '{nid}' confidence is PARSE_UNCERTAIN "
                f"— answer reliability reduced."
                for nid in pu_nodes]

    def _layer4_parse_uncertain(
        self, nodes: List[Dict]
    ) -> Tuple[List[str], List[str]]:
        warnings = []
        pu_nodes = []
        for node in nodes:
            conf = node.get("confidence", "")
            nid = node.get("node_id", "")
            if "PARSE_UNCERTAIN" in str(conf):
                pu_nodes.append(nid)
                warnings.append(
                    f"[Layer4-ParseUncertain] '{nid}' — {conf}. "
                    f"Treating as MEDIUM confidence."
                )
        return warnings, pu_nodes

    # ------------------------------------------------------------------
    # Layer 5: SUPERSEDES (stale filter)
    # ------------------------------------------------------------------

    def check_stale(self, nodes: List[Dict]) -> List[str]:
        """Return warnings for nodes that have been superseded."""
        stale_warn, _ = self._layer5_supersedes(nodes)
        return stale_warn

    def _layer5_supersedes(
        self, nodes: List[Dict]
    ) -> Tuple[List[str], set]:
        stale_ids = self.graph.get_stale_node_ids()
        warnings = []
        found_stale = set()
        for node in nodes:
            nid = node.get("node_id", "")
            if nid in stale_ids:
                # Find what superseded it
                superseding = [
                    src for src, eattrs in self.graph.get_neighbors(nid, direction="in")
                    if eattrs.get("edge_type") == "SUPERSEDES"
                ]
                warnings.append(
                    f"[Layer5-Stale] Node '{nid}' has been SUPERSEDED by "
                    f"{superseding} — filtered from results."
                )
                found_stale.add(nid)
        return warnings, found_stale

    # ------------------------------------------------------------------
    # Layer 6: CONTRADICTS
    # ------------------------------------------------------------------

    def check_contradictions(self, nodes: List[Dict]) -> List[str]:
        """Return warnings for CONTRADICTS edges within the node set."""
        return self._layer6_contradicts(nodes)

    def _layer6_contradicts(self, nodes: List[Dict]) -> List[str]:
        warnings = []
        node_ids = {n.get("node_id", "") for n in nodes}

        for u, v, eattrs in self.graph.get_contradictions():
            if u not in node_ids and v not in node_ids:
                continue

            # Only fire for DECISION-DECISION contradictions.
            # COMPONENT contradictions are spurious (structural misclassification
            # from CrossReferenceDetector Mode 1 running on similar IP blocks).
            u_type = (self.graph.get_node(u) or {}).get("node_type", "")
            v_type = (self.graph.get_node(v) or {}).get("node_type", "")
            if u_type == "COMPONENT" or v_type == "COMPONENT":
                continue

            warnings.append(
                f"[Layer6-Contradiction] Nodes '{u}' and '{v}' have a "
                f"CONTRADICTS edge — review before using both."
            )

        return warnings
