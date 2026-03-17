"""
embedder.py — Shared SentenceTransformer singleton

Tüm RAG v2 store'ları (VectorStoreV2, SourceChunkStore, DocStore) bu modülü
kullanır. Böylece aynı process içinde model tek kez yüklenir (~500MB bellek tasarrufu).

Model   : paraphrase-multilingual-mpnet-base-v2
Dim     : 768
Device  : cuda (GB10 GPU — 11.8× hızlanma, batch_size=256)
          CUDA 12.1 UserWarning beklenen — hata değil, çalışır.
"""

from __future__ import annotations

import warnings
from typing import List

# Process-level singleton — import edilince model hemen yüklenmez (lazy)
_model = None
_MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"
_BATCH_SIZE  = 256   # GPU için optimize (CPU'da 64 yeterliydi)


def _get_model():
    global _model
    if _model is None:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")   # CUDA 12.1 UserWarning bastır
            _model = SentenceTransformer(_MODEL_NAME, device=device)

        print(f"[embedder] model={_MODEL_NAME} device={_model.device} batch={_BATCH_SIZE}")
    return _model


def embed_text(text: str) -> List[float]:
    """Tek metin → 768-dim float listesi."""
    return _get_model().encode(text, convert_to_numpy=True).tolist()


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Metin listesi → embedding listesi (GPU batch, daha verimli)."""
    return _get_model().encode(
        texts,
        batch_size=_BATCH_SIZE,
        convert_to_numpy=True,
        show_progress_bar=len(texts) > 500,
    ).tolist()


def model_name() -> str:
    return _MODEL_NAME


def embedding_dim() -> int:
    return 768


# chromadb embedding_function uyumlu wrapper
class ChromaEmbeddingFunction:
    """
    ChromaDB embedding_function protokolü için wrapper.
    DocStore'da external embedding yerine bu kullanılır.
    """

    def __call__(self, input: List[str]) -> List[List[float]]:  # noqa: A002
        return embed_texts(input)
