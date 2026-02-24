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
    """Embedding service using Google GenAI API (new google.genai package)."""

    def __init__(self, api_key: str = None, model_name: str = "gemini-embedding-001"):
        """Initialize Google GenAI embeddings.

        Args:
            api_key: Google API key
            model_name: Embedding model name (e.g., gemini-embedding-exp-03-07, text-embedding-004)
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model_name = model_name
        self._client = None

    def _get_client(self):
        """Lazy load the GenAI client."""
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                raise RuntimeError(f"Google GenAI başlatılamadı: {e}")
        return self._client

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: Input text

        Returns:
            Embedding vector
        """
        import time
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                client = self._get_client()
                result = client.models.embed_content(
                    model=self.model_name,
                    contents=text
                )
                return list(result.embeddings[0].values)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"  ⚠️ Embedding hatası, {wait_time}s bekleyip tekrar deneniyor: {e}")
                    time.sleep(wait_time)
                    continue
                raise RuntimeError(f"Embedding oluşturulamadı: {e}")

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts

        Returns:
            List of embedding vectors
        """
        import time
        embeddings = []
        batch_size = 100  # Process in batches
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                client = self._get_client()
                result = client.models.embed_content(
                    model=self.model_name,
                    contents=batch
                )
                batch_embeddings = [list(e.values) for e in result.embeddings]
                embeddings.extend(batch_embeddings)
                print(f"  📊 Vektörleştirme: {min(i + batch_size, len(texts))}/{len(texts)}")
            except Exception as e:
                # Fallback to single text embedding if batch fails
                print(f"  ⚠️ Batch embedding başarısız, tek tek deneniyor: {e}")
                for j, text in enumerate(batch):
                    embedding = self.embed_text(text)
                    embeddings.append(embedding)
                    if (i + j + 1) % 10 == 0:
                        print(f"  📊 Vektörleştirme: {i + j + 1}/{len(texts)}")
                    time.sleep(0.1)  # Rate limiting
        
        print(f"  📊 Vektörleştirme: {len(texts)}/{len(texts)} ✅")
        return embeddings
