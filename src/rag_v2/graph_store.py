"""
Graph Store — FPGA RAG v2
Architecture ref: fpga_rag_architecture_v2.md §1, §2, §4

Node types  (9): PROJECT, REQUIREMENT, DECISION, COMPONENT,
                  CONSTRAINT, EVIDENCE, PATTERN, SOURCE_DOC, ISSUE
Edge types (12): DECOMPOSES_TO, MOTIVATED_BY, ALTERNATIVE_TO,
                 IMPLEMENTS, VERIFIED_BY, CONSTRAINED_BY, DEPENDS_ON,
                 ANALOGOUS_TO, CONTRADICTS, INFORMED_BY,
                 REUSES_PATTERN, SUPERSEDES

Confidence model: HIGH > MEDIUM > PARSE_UNCERTAIN
Chain rule      : weakest link in traversal path = path confidence
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx
from networkx.readwrite import json_graph

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NODE_TYPES = {
    "PROJECT", "REQUIREMENT", "DECISION", "COMPONENT",
    "CONSTRAINT", "EVIDENCE", "PATTERN", "SOURCE_DOC", "ISSUE",
}

EDGE_TYPES = {
    "DECOMPOSES_TO", "MOTIVATED_BY", "ALTERNATIVE_TO",
    "IMPLEMENTS", "VERIFIED_BY", "CONSTRAINED_BY", "DEPENDS_ON",
    "ANALOGOUS_TO", "CONTRADICTS", "INFORMED_BY",
    "REUSES_PATTERN", "SUPERSEDES",
}

# Confidence ranking (lower index = lower confidence)
_CONF_RANK = {"PARSE_UNCERTAIN": 0, "MEDIUM": 1, "HIGH": 2}


def _min_confidence(levels: List[str]) -> str:
    """Return the weakest confidence level in a list (chain propagation rule)."""
    if not levels:
        return "PARSE_UNCERTAIN"
    ranked = [_CONF_RANK.get(c.split("_")[0] if c.startswith("PARSE") else c, 0)
              for c in levels]
    min_rank = min(ranked)
    for conf, rank in _CONF_RANK.items():
        if rank == min_rank:
            return conf
    return "PARSE_UNCERTAIN"


# ---------------------------------------------------------------------------
# GraphStore
# ---------------------------------------------------------------------------

class GraphStore:
    """
    NetworkX DiGraph wrapper for FPGA RAG v2 graph operations.

    Persistence: JSON node-link format (nx.readwrite.json_graph.node_link_data)
    Storage    : db/graph/fpga_rag_v2_graph.json
    """

    def __init__(self, persist_path: str = "db/graph/fpga_rag_v2_graph.json"):
        self._path = Path(persist_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            self._graph: nx.DiGraph = self._load()
        else:
            self._graph = nx.DiGraph()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> nx.DiGraph:
        with open(self._path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return json_graph.node_link_graph(data, directed=True, multigraph=False)

    def save(self) -> None:
        data = json_graph.node_link_data(self._graph)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Node CRUD
    # ------------------------------------------------------------------

    def add_node(self, node_id: str, attrs: Dict[str, Any]) -> None:
        """Add or update a node. node_type must be in NODE_TYPES."""
        node_type = attrs.get("node_type", "")
        if node_type not in NODE_TYPES:
            raise ValueError(f"Unknown node_type '{node_type}'. Valid: {NODE_TYPES}")
        self._graph.add_node(node_id, **attrs)

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Return node attributes dict or None if not found."""
        if self._graph.has_node(node_id):
            return dict(self._graph.nodes[node_id])
        return None

    def get_nodes_by_type(self, node_type: str) -> List[Dict[str, Any]]:
        """Return all nodes of a given type with their attrs + node_id."""
        result = []
        for nid, attrs in self._graph.nodes(data=True):
            if attrs.get("node_type") == node_type:
                result.append({"node_id": nid, **attrs})
        return result

    def get_all_nodes(self) -> List[Dict[str, Any]]:
        return [{"node_id": nid, **attrs}
                for nid, attrs in self._graph.nodes(data=True)]

    # ------------------------------------------------------------------
    # Edge CRUD
    # ------------------------------------------------------------------

    def add_edge(self, from_id: str, to_id: str, edge_type: str,
                 attrs: Optional[Dict[str, Any]] = None) -> None:
        """Add a directed edge. edge_type must be in EDGE_TYPES."""
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"Unknown edge_type '{edge_type}'. Valid: {EDGE_TYPES}")
        edge_attrs = {"edge_type": edge_type, **(attrs or {})}
        self._graph.add_edge(from_id, to_id, **edge_attrs)

    def get_edge(self, from_id: str, to_id: str) -> Optional[Dict[str, Any]]:
        if self._graph.has_edge(from_id, to_id):
            return dict(self._graph.edges[from_id, to_id])
        return None

    # ------------------------------------------------------------------
    # Traversal API (architecture §4)
    # ------------------------------------------------------------------

    def get_neighbors(
        self,
        node_id: str,
        edge_type: Optional[str] = None,
        direction: str = "out",
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Return list of (neighbor_id, edge_attrs) for a node.
        direction: "out" (successors), "in" (predecessors), "both"
        """
        results: List[Tuple[str, Dict[str, Any]]] = []
        if direction in ("out", "both"):
            for _, nbr, eattrs in self._graph.out_edges(node_id, data=True):
                if edge_type is None or eattrs.get("edge_type") == edge_type:
                    results.append((nbr, dict(eattrs)))
        if direction in ("in", "both"):
            for src, _, eattrs in self._graph.in_edges(node_id, data=True):
                if edge_type is None or eattrs.get("edge_type") == edge_type:
                    results.append((src, dict(eattrs)))
        return results

    def find_path(self, from_id: str, to_id: str) -> List[str]:
        """Shortest directed path between two nodes. Returns [] if none."""
        try:
            return nx.shortest_path(self._graph, from_id, to_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_chain_confidence(self, path: List[str]) -> str:
        """
        Confidence for a traversal path.
        Architecture rule: weakest link in the path.
        """
        levels: List[str] = []
        for nid in path:
            node = self.get_node(nid)
            if node:
                levels.append(node.get("confidence", "PARSE_UNCERTAIN"))
        return _min_confidence(levels)

    # ------------------------------------------------------------------
    # Requirement Tree (DECOMPOSES_TO traversal)
    # ------------------------------------------------------------------

    def get_req_tree(self, root_id: str) -> List[Dict[str, Any]]:
        """
        BFS traversal of DECOMPOSES_TO edges from root_id.
        Returns ordered list of nodes (root first).
        """
        visited: List[str] = []
        queue = [root_id]
        seen = set()
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            node = self.get_node(current)
            if node:
                visited.append({"node_id": current, **node})
            for child_id, _ in self.get_neighbors(current, edge_type="DECOMPOSES_TO"):
                if child_id not in seen:
                    queue.append(child_id)
        return visited

    # ------------------------------------------------------------------
    # Anti-Hallucination helpers (architecture §7)
    # ------------------------------------------------------------------

    def get_coverage_gaps(self) -> List[Dict[str, Any]]:
        """
        REQUIREMENT nodes that have no outgoing IMPLEMENTS edge.
        (Architecture Layer 3: Coverage Gap)
        """
        gaps = []
        for node in self.get_nodes_by_type("REQUIREMENT"):
            nid = node["node_id"]
            has_impl = any(
                eattrs.get("edge_type") == "IMPLEMENTS"
                for _, eattrs in self.get_neighbors(nid, direction="in")
            )
            if not has_impl:
                gaps.append(node)
        return gaps

    def get_orphan_components(self) -> List[Dict[str, Any]]:
        """
        COMPONENT nodes that have no outgoing IMPLEMENTS edge.
        (Architecture Layer 3: Orphan Component)
        """
        orphans = []
        for node in self.get_nodes_by_type("COMPONENT"):
            nid = node["node_id"]
            has_impl = any(
                eattrs.get("edge_type") == "IMPLEMENTS"
                for _, eattrs in self.get_neighbors(nid, direction="out")
            )
            if not has_impl:
                orphans.append(node)
        return orphans

    def get_contradictions(self) -> List[Tuple[str, str, Dict[str, Any]]]:
        """
        All CONTRADICTS edges: returns [(from_id, to_id, edge_attrs), ...]
        (Architecture Layer 6: Contradiction detection)
        """
        result = []
        for u, v, eattrs in self._graph.edges(data=True):
            if eattrs.get("edge_type") == "CONTRADICTS":
                result.append((u, v, dict(eattrs)))
        return result

    def get_superseded(self) -> List[Tuple[str, str]]:
        """
        All SUPERSEDES edges: (new_node_id, old_node_id).
        Old node should be filtered out of query results.
        (Architecture Layer 5: Stale data filter)
        """
        result = []
        for u, v, eattrs in self._graph.edges(data=True):
            if eattrs.get("edge_type") == "SUPERSEDES":
                result.append((u, v))
        return result

    def get_stale_node_ids(self) -> set:
        """Return set of node_ids that have been superseded (stale)."""
        return {old for _, old in self.get_superseded()}

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        node_counts: Dict[str, int] = {}
        for _, attrs in self._graph.nodes(data=True):
            nt = attrs.get("node_type", "UNKNOWN")
            node_counts[nt] = node_counts.get(nt, 0) + 1

        edge_counts: Dict[str, int] = {}
        for _, _, eattrs in self._graph.edges(data=True):
            et = eattrs.get("edge_type", "UNKNOWN")
            edge_counts[et] = edge_counts.get(et, 0) + 1

        return {
            "total_nodes": self._graph.number_of_nodes(),
            "total_edges": self._graph.number_of_edges(),
            "node_types": node_counts,
            "edge_types": edge_counts,
            "persist_path": str(self._path),
        }

    def __repr__(self) -> str:
        s = self.stats()
        return (f"GraphStore(nodes={s['total_nodes']}, "
                f"edges={s['total_edges']}, path={s['persist_path']})")
