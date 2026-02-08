"""Gemini LLM for response generation."""

from typing import List, Dict, Any, Optional
import os
from dotenv import load_dotenv

load_dotenv()


class GeminiGenerator:
    """Response generator using Gemini Flash model."""

    def __init__(
        self,
        api_key: str = None,
        model_name: str = "gemini-2.0-flash",
    ):
        """Initialize Gemini generator.

        Args:
            api_key: Google API key
            model_name: Gemini model name
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        """Lazy load the Gemini model."""
        if self._model is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._model = genai.GenerativeModel(self.model_name)
            except Exception as e:
                raise RuntimeError(f"Gemini başlatılamadı: {e}")
        return self._model

    def generate(
        self,
        query: str,
        context_documents: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        """Generate a response based on query and retrieved context.

        Args:
            query: User question
            context_documents: Retrieved documents for context
            system_prompt: Optional system instructions
            temperature: Generation temperature

        Returns:
            Generated response text
        """
        model = self._get_model()

        # Build context from retrieved documents
        context_parts = []
        for i, doc in enumerate(context_documents, 1):
            source = doc.get("metadata", {}).get("filename", f"Kaynak {i}")
            content = doc.get("content", doc.get("document", ""))
            context_parts.append(f"[{source}]\n{content}")
        
        context = "\n\n---\n\n".join(context_parts)

        # Build the prompt
        default_system = """Sen yardımsever bir asistansın. Sana verilen kaynak belgelere dayanarak soruları yanıtla.
        
Kurallar:
- Sadece verilen kaynaklardaki bilgileri kullan
- Eğer kaynaklarda bilgi yoksa, bunu açıkça belirt
- Yanıtını Türkçe ver
- Kaynak belirtirken dosya adını kullan"""

        system = system_prompt or default_system

        full_prompt = f"""{system}

📚 KAYNAK BELGELER:
{context}

❓ SORU: {query}

💡 YANIT:"""

        # Generate response
        response = model.generate_content(
            full_prompt,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": 2048,
            },
        )

        return response.text

    def chat(self, message: str) -> str:
        """Simple chat without RAG context.

        Args:
            message: User message

        Returns:
            Response text
        """
        model = self._get_model()
        response = model.generate_content(message)
        return response.text
