"""Local Sentence Transformer Embeddings (768 dimensions)."""

from typing import List
import os


class SentenceEmbeddings:
    """Embedding service using Sentence Transformers (local, no API needed)."""

    def __init__(self, model_name: str = "all-mpnet-base-v2"):
        """Initialize Sentence Transformer embeddings.

        Args:
            model_name: Sentence Transformer model name (default: all-mpnet-base-v2, 768 dims)
        """
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        """Lazy load the embedding model."""
        if self._model is None:
            try:
                import torch
                from sentence_transformers import SentenceTransformer
                device = "cuda" if torch.cuda.is_available() else "cpu"
                self._model = SentenceTransformer(self.model_name, device=device)
                print(f"    [OK] Sentence Transformer modeli yüklendi: {self.model_name} ({device})")
            except Exception as e:
                raise RuntimeError(f"Sentence Transformers başlatılamadı: {e}")
        return self._model

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: Input text

        Returns:
            Embedding vector (768 dimensions)
        """
        model = self._get_model()
        embedding = model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors (768 dimensions each)
        """
        model = self._get_model()
        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return [emb.tolist() for emb in embeddings]
