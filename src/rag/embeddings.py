"""Embedding service for document vectorization."""

from typing import List
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel


class EmbeddingService:
    """Service for generating text embeddings using Vertex AI."""

    def __init__(self, project_id: str, location: str = "us-central1"):
        """Initialize the embedding service.

        Args:
            project_id: GCP project ID
            location: GCP region for Vertex AI
        """
        self.project_id = project_id
        self.location = location
        aiplatform.init(project=project_id, location=location)
        self.model = TextEmbeddingModel.from_pretrained("textembedding-gecko@003")

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            List of float values representing the embedding
        """
        embeddings = self.model.get_embeddings([text])
        return embeddings[0].values

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts to embed

        Returns:
            List of embeddings
        """
        embeddings = self.model.get_embeddings(texts)
        return [e.values for e in embeddings]
