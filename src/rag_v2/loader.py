"""
Loader — pipeline_graph.json → GraphStore + VectorStoreV2
Architecture ref: fpga_rag_architecture_v2.md §3 Phase 6 (Graph+Vector Commit)

pipeline_graph.json uses JavaScript-style // comments (not valid JSON).
This loader strips them before parsing.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Resolve project root so imports work regardless of cwd
_PROJ_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJ_ROOT / "src"))

from rag_v2.graph_store import GraphStore, NODE_TYPES, EDGE_TYPES
from rag_v2.vector_store_v2 import VectorStoreV2


# ---------------------------------------------------------------------------
# JSON comment stripper
# ---------------------------------------------------------------------------

def _strip_js_comments(text: str) -> str:
    """
    Remove JavaScript-style // and /* */ comments from a string.
    Simple regex approach — safe for FPGA RAG pipeline_graph.json format.
    """
    # Remove /* ... */ block comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # Remove // line comments (not inside strings)
    # This regex avoids matching // inside quoted strings
    text = re.sub(r'(?<!["\'])//[^\n]*', '', text)
    return text


def load_pipeline_graph(json_path: str) -> Tuple[List[Dict], List[Dict], Dict]:
    """
    Parse pipeline_graph.json.
    Returns: (nodes, edges, meta)
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"pipeline_graph.json not found: {path}")

    raw = path.read_text(encoding="utf-8")
    cleaned = _strip_js_comments(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse error after stripping comments: {e}") from e

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    meta = data.get("meta", {})

    return nodes, edges, meta


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class PipelineGraphLoader:
    """
    Loads pipeline_graph.json into GraphStore and VectorStoreV2.

    Usage:
        loader = PipelineGraphLoader(json_path, graph_store, vector_store)
        stats = loader.load(verbose=True)
    """

    def __init__(
        self,
        json_path: str,
        graph_store: GraphStore,
        vector_store: VectorStoreV2,
    ):
        self.json_path = json_path
        self.graph_store = graph_store
        self.vector_store = vector_store

    def load(self, verbose: bool = True) -> Dict[str, Any]:
        """
        Full load: parse → graph nodes → graph edges → vector embeddings.
        Returns summary stats dict.
        """
        if verbose:
            print(f"[Loader] Parsing {self.json_path} ...")

        nodes, edges, meta = load_pipeline_graph(self.json_path)

        if verbose:
            print(f"[Loader] Found {len(nodes)} nodes, {len(edges)} edges")
            print(f"[Loader] Projects: {meta.get('projects', [])}")
            print(f"[Loader] Pipeline version: {meta.get('pipeline_version', '?')}")

        # --- Phase A: Load nodes into GraphStore ---
        graph_ok, graph_skip = self._load_nodes_to_graph(nodes, verbose)

        # --- Phase B: Load edges into GraphStore ---
        edge_ok, edge_skip = self._load_edges_to_graph(edges, verbose)

        # --- Phase C: Persist graph ---
        if verbose:
            print("[Loader] Saving graph to disk ...")
        self.graph_store.save()

        # --- Phase D: Embed nodes into VectorStore ---
        if verbose:
            print("[Loader] Embedding nodes into VectorStoreV2 ...")
        vec_stored = self._load_nodes_to_vector(nodes, verbose)

        stats = {
            "meta": meta,
            "graph_nodes_loaded": graph_ok,
            "graph_nodes_skipped": graph_skip,
            "graph_edges_loaded": edge_ok,
            "graph_edges_skipped": edge_skip,
            "vector_nodes_stored": vec_stored,
        }

        if verbose:
            print("\n[Loader] === Load Complete ===")
            print(f"  Graph nodes  : {graph_ok} loaded, {graph_skip} skipped")
            print(f"  Graph edges  : {edge_ok} loaded, {edge_skip} skipped")
            print(f"  Vector nodes : {vec_stored} embedded")
            gs = self.graph_store.stats()
            print(f"  Graph total  : {gs['total_nodes']} nodes, {gs['total_edges']} edges")
            print(f"  Vector total : {self.vector_store.count()} docs")

        return stats

    def _load_nodes_to_graph(
        self, nodes: List[Dict], verbose: bool
    ) -> Tuple[int, int]:
        ok = 0
        skip = 0
        for node in nodes:
            node_id = node.get("node_id")
            node_type = node.get("node_type", "")

            if not node_id:
                skip += 1
                continue

            if node_type not in NODE_TYPES:
                if verbose:
                    print(f"  [Graph] SKIP node '{node_id}': unknown type '{node_type}'")
                skip += 1
                continue

            # Flatten complex fields to strings for graph storage
            flat = _flatten_node(node)
            try:
                self.graph_store.add_node(node_id, flat)
                ok += 1
            except Exception as e:
                if verbose:
                    print(f"  [Graph] ERROR node '{node_id}': {e}")
                skip += 1

        if verbose:
            print(f"[Loader] Graph nodes: {ok} added, {skip} skipped")
        return ok, skip

    def _load_edges_to_graph(
        self, edges: List[Dict], verbose: bool
    ) -> Tuple[int, int]:
        ok = 0
        skip = 0
        for edge in edges:
            from_id = edge.get("from")
            to_id = edge.get("to")
            edge_type = edge.get("edge_type", "")

            if not from_id or not to_id:
                skip += 1
                continue

            if edge_type not in EDGE_TYPES:
                if verbose:
                    print(f"  [Graph] SKIP edge {from_id}→{to_id}: unknown type '{edge_type}'")
                skip += 1
                continue

            # Flatten edge attrs
            edge_attrs = {k: v for k, v in edge.items()
                          if k not in ("from", "to", "edge_type")}
            edge_attrs = _flatten_dict(edge_attrs)

            try:
                # Auto-add missing endpoint nodes as stubs
                if not self.graph_store.get_node(from_id):
                    self.graph_store._graph.add_node(from_id, node_id=from_id,
                                                      node_type="UNKNOWN", _stub=True)
                if not self.graph_store.get_node(to_id):
                    self.graph_store._graph.add_node(to_id, node_id=to_id,
                                                      node_type="UNKNOWN", _stub=True)
                self.graph_store.add_edge(from_id, to_id, edge_type, edge_attrs)
                ok += 1
            except Exception as e:
                if verbose:
                    print(f"  [Graph] ERROR edge {from_id}→{to_id}: {e}")
                skip += 1

        if verbose:
            print(f"[Loader] Graph edges: {ok} added, {skip} skipped")
        return ok, skip

    def _load_nodes_to_vector(
        self, nodes: List[Dict], verbose: bool
    ) -> int:
        # Flatten for vector store (same format)
        flat_nodes = [_flatten_node(n) for n in nodes if n.get("node_id")]
        stored = self.vector_store.add_nodes_batch(flat_nodes, batch_size=32)
        return stored


# ---------------------------------------------------------------------------
# Helper: flatten nested dicts/lists to strings for ChromaDB/NetworkX compat
# ---------------------------------------------------------------------------

def _flatten_node(node: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with nested dicts/lists serialized to JSON strings."""
    flat = {}
    for k, v in node.items():
        flat[k] = _serialize_value(v)
    return flat


def _flatten_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    flat = {}
    for k, v in d.items():
        flat[k] = _serialize_value(v)
    return flat


def _serialize_value(v: Any) -> Any:
    """Convert non-scalar values to JSON strings."""
    if v is None:
        return ""
    if isinstance(v, (str, int, float, bool)):
        return v
    return json.dumps(v, ensure_ascii=False)
