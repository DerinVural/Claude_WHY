"""
Vector Store V2 — Graph Nodes Collection
Architecture ref: fpga_rag_architecture_v2.md §3 (Vector Store)

Separate from production "documents" collection (4.15M chunks, 14 GB).
This collection stores graph node embeddings only.

Config:
  DB path     : db/chroma_graph_nodes/   (isolated from chroma_db/)
  Collection  : fpga_rag_v2_nodes
  Metric      : cosine
  Embedding   : paraphrase-multilingual-mpnet-base-v2, 768-dim (multilingual)
  Ext embed   : embedding_function=None (embeddings computed externally)
  Threshold   : 0.35 (default — cosine similarity, lowered for technical doc robustness)
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb

# Lazy-load sentence_transformers to avoid import cost at module level
_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        # Use the project's existing SentenceEmbeddings if available
        proj_root = Path(__file__).parent.parent.parent
        src_path = str(proj_root / "src")
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        try:
            from rag.sentence_embeddings import SentenceEmbeddings
            _embedder = SentenceEmbeddings(model_name="paraphrase-multilingual-mpnet-base-v2")
        except ImportError:
            import os
            from sentence_transformers import SentenceTransformer
            os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
            _model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2", device="cpu")
            class _Wrapper:
                def embed_text(self, text):
                    return _model.encode(text).tolist()
                def embed_texts(self, texts):
                    return _model.encode(texts).tolist()
            _embedder = _Wrapper()
    return _embedder


# ---------------------------------------------------------------------------
# Text builder — what gets embedded per node
# ---------------------------------------------------------------------------

def build_node_text(node: Dict[str, Any]) -> str:
    """
    Architecture §3 Phase 6: embed node text.
    Format: "{node_type} {name} {description} {key_logic} {acceptance_criteria}"
    """
    def _s(v):
        if isinstance(v, list): return " ".join(str(x) for x in v)
        return str(v) if v else ""

    parts = [
        _s(node.get("node_type", "")),
        _s(node.get("node_id", "")),
        _s(node.get("name", "")),
        _s(node.get("description", "")),
        _s(node.get("key_logic", "")),
        _s(node.get("acceptance_criteria", "")),
        _s(node.get("rationale", "")),
        _s(node.get("summary", "")),
    ]
    return " ".join(p for p in parts if p).strip()


# ---------------------------------------------------------------------------
# VectorStoreV2
# ---------------------------------------------------------------------------

class VectorStoreV2:
    """
    ChromaDB wrapper for graph node embeddings.

    Collection: "fpga_rag_v2_nodes"
    Isolated from production chroma_db/documents collection.
    """

    COLLECTION_NAME = "fpga_rag_v2_nodes"
    DEFAULT_THRESHOLD = 0.35

    def __init__(
        self,
        persist_directory: str = "db/chroma_graph_nodes",
        threshold: float = DEFAULT_THRESHOLD,
    ):
        self._persist_dir = Path(persist_directory)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self.threshold = threshold

        self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,  # external embeddings
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_node(self, node: Dict[str, Any]) -> None:
        """Embed and store a single graph node."""
        node_id = node.get("node_id")
        if not node_id:
            raise ValueError("Node must have 'node_id'")

        text = build_node_text(node)
        if not text:
            return  # skip empty nodes

        embedder = _get_embedder()
        embedding = embedder.embed_text(text)

        metadata = {
            "node_id": node_id,
            "node_type": node.get("node_type", ""),
            "project": node.get("project", ""),
            "confidence": node.get("confidence", ""),
            "version": str(node.get("version", "")),
            "name": node.get("name", node_id)[:512],
        }

        self._collection.upsert(
            ids=[node_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata],
        )

    def add_nodes_batch(self, nodes: List[Dict[str, Any]], batch_size: int = 50) -> int:
        """
        Batch embed and store multiple nodes.
        Returns count of nodes actually stored.
        """
        embedder = _get_embedder()
        stored = 0

        for i in range(0, len(nodes), batch_size):
            batch = nodes[i: i + batch_size]
            ids, texts, metadatas = [], [], []

            for node in batch:
                node_id = node.get("node_id")
                if not node_id:
                    continue
                text = build_node_text(node)
                if not text:
                    continue
                ids.append(node_id)
                texts.append(text)
                metadatas.append({
                    "node_id": node_id,
                    "node_type": node.get("node_type", ""),
                    "project": node.get("project", ""),
                    "confidence": node.get("confidence", ""),
                    "version": str(node.get("version", "")),
                    "name": node.get("name", node_id)[:512],
                })

            if not ids:
                continue

            embeddings = embedder.embed_texts(texts)
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            stored += len(ids)

        return stored

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        question: str,
        n_results: int = 5,
        node_type_filter: Optional[str] = None,
        project_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over graph nodes.
        Returns nodes with cosine similarity >= threshold.
        """
        embedder = _get_embedder()
        query_embedding = embedder.embed_text(question)

        where: Optional[Dict] = None
        filters = {}
        if node_type_filter:
            filters["node_type"] = node_type_filter
        if project_filter:
            filters["project"] = project_filter
        if len(filters) == 1:
            where = filters
        elif len(filters) > 1:
            where = {"$and": [{k: v} for k, v in filters.items()]}

        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(n_results, max(1, self._collection.count())),
            "include": ["metadatas", "documents", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        output = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        documents = results.get("documents", [[]])[0]

        for nid, dist, meta, doc in zip(ids, distances, metadatas, documents):
            # ChromaDB cosine distance: 0=identical, 2=opposite
            # similarity = 1 - (distance / 2) for normalized vectors
            # But chromadb with hnsw:space=cosine returns 1-cosine_sim
            similarity = 1.0 - dist
            if similarity >= self.threshold:
                output.append({
                    "node_id": nid,
                    "similarity": round(similarity, 4),
                    "metadata": meta,
                    "text": doc,
                })

        return sorted(output, key=lambda x: x["similarity"], reverse=True)

    def query_by_embedding(
        self,
        embedding: List[float],
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Query with a pre-computed embedding vector."""
        count = self._collection.count()
        if count == 0:
            return []

        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(n_results, count),
            include=["metadatas", "documents", "distances"],
        )

        output = []
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        documents = results.get("documents", [[]])[0]

        for nid, dist, meta, doc in zip(ids, distances, metadatas, documents):
            similarity = 1.0 - dist
            if similarity >= self.threshold:
                output.append({
                    "node_id": nid,
                    "similarity": round(similarity, 4),
                    "metadata": meta,
                    "text": doc,
                })

        return sorted(output, key=lambda x: x["similarity"], reverse=True)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def count(self) -> int:
        return self._collection.count()

    def is_empty(self) -> bool:
        return self._collection.count() == 0

    def stats(self) -> Dict[str, Any]:
        return {
            "collection": self.COLLECTION_NAME,
            "persist_dir": str(self._persist_dir),
            "count": self.count(),
            "threshold": self.threshold,
        }

    def __repr__(self) -> str:
        return (f"VectorStoreV2(collection='{self.COLLECTION_NAME}', "
                f"count={self.count()}, threshold={self.threshold})")
