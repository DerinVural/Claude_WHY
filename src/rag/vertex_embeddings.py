"""Vertex AI Embeddings service using text-embedding-004 model."""

from typing import List
import os
from dotenv import load_dotenv

load_dotenv()


class VertexEmbeddings:
    """Embedding service using Vertex AI text-embedding-004 model."""

    def __init__(
        self,
        project_id: str = None,
        location: str = "us-central1",
        model_name: str = "text-embedding-004",
    ):
        """Initialize Vertex AI embeddings.

        Args:
            project_id: GCP project ID
            location: GCP region
            model_name: Embedding model name
        """
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self.location = location
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        """Lazy load the embedding model."""
        if self._model is None:
            try:
                from vertexai.language_models import TextEmbeddingModel
                import vertexai
                
                vertexai.init(project=self.project_id, location=self.location)
                self._model = TextEmbeddingModel.from_pretrained(self.model_name)
            except Exception as e:
                raise RuntimeError(f"Vertex AI başlatılamadı: {e}")
        return self._model

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        model = self._get_model()
        embeddings = model.get_embeddings([text])
        return embeddings[0].values

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        model = self._get_model()
        
        # Batch processing with progress
        all_embeddings = []
        batch_size = 5  # Vertex AI batch limit
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = model.get_embeddings(batch)
            all_embeddings.extend([e.values for e in embeddings])
            print(f"  📊 Vektörleştirme: {min(i + batch_size, len(texts))}/{len(texts)}")
        
        return all_embeddings


class GoogleGenAIEmbeddings:
    """Embedding service using Google GenAI API (API key based)."""

    def __init__(self, api_key: str = None, model_name: str = "models/gemini-embedding-001"):
        """Initialize Google GenAI embeddings.

        Args:
            api_key: Google API key
            model_name: Embedding model name
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model_name = model_name
        self._client = None

    def _get_client(self):
        """Lazy load the GenAI client."""
        if self._client is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai
            except Exception as e:
                raise RuntimeError(f"Google GenAI başlatılamadı: {e}")
        return self._client

    def embed_text_rest(self, text: str) -> List[float]:
        """Generate embedding using REST API (avoids grpc DNS issues).

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        import requests
        import time
        
        url = f"https://generativelanguage.googleapis.com/v1beta/{self.model_name}:embedContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": self.api_key}
        data = {
            "model": self.model_name,
            "content": {"parts": [{"text": text}]}
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(url, headers=headers, params=params, json=data, timeout=30)
                response.raise_for_status()
                result = response.json()
                return result["embedding"]["values"]
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise RuntimeError(f"REST API embedding hatası: {e}")

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        # Try REST API first (more reliable with DNS issues)
        try:
            return self.embed_text_rest(text)
        except Exception as rest_error:
            print(f"  ⚠️ REST API başarısız, grpc deneniyor: {rest_error}")
            # Fallback to grpc
            client = self._get_client()
            result = client.embed_content(
                model=self.model_name,
                content=text
            )
            return result["embedding"]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        embeddings = []
        for i, text in enumerate(texts):
            embedding = self.embed_text(text)
            embeddings.append(embedding)
            if (i + 1) % 10 == 0:
                print(f"  📊 Vektörleştirme: {i + 1}/{len(texts)}")
        
        print(f"  📊 Vektörleştirme: {len(texts)}/{len(texts)} ✅")
        return embeddings
