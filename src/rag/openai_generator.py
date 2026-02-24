"""OpenAI LLM for response generation — GeminiGenerator ile aynı arayüz."""

from typing import List, Dict, Any, Optional
import os
from dotenv import load_dotenv

load_dotenv()


class OpenAIGenerator:
    """
    Response generator using OpenAI Chat Completion API.
    GeminiGenerator ile birebir aynı metot imzaları — kolayca swap edilebilir.

    Desteklenen modeller: gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo
    """

    def __init__(
        self,
        api_key: str = None,
        model_name: str = "gpt-4o-mini",
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            except Exception as e:
                raise RuntimeError(f"OpenAI başlatılamadı: {e}")
        return self._client

    def generate(
        self,
        query: str,
        context_documents: List[Any],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        """
        GeminiGenerator.generate() ile aynı imza.

        context_documents: str listesi (build_llm_context çıktısı) veya
                           dict listesi (eski RAG pipeline formatı) kabul eder.
        """
        client = self._get_client()

        # Context oluştur — iki format destekleniyor
        context_parts = []
        for i, doc in enumerate(context_documents, 1):
            if isinstance(doc, str):
                context_parts.append(doc)
            elif isinstance(doc, dict):
                source = doc.get("metadata", {}).get("filename", f"Kaynak {i}")
                content = doc.get("content", doc.get("document", ""))
                context_parts.append(f"[{source}]\n{content}")
        context = "\n\n---\n\n".join(context_parts)

        default_system = (
            "Sen bir FPGA mühendislik asistanısın. "
            "Sana verilen kaynak belgeler FPGA RAG v2 sisteminden alınmıştır. "
            "Yalnızca bu belgelerdeki bilgileri kullan, asla tahmin üretme. "
            "Yanıtını Türkçe ver."
        )
        system = system_prompt or default_system

        user_message = f"CONTEXT:\n{context}\n\nSOURU: {query}"

        response = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=2048,
        )

        return response.choices[0].message.content

    def chat(self, message: str) -> str:
        """Basit sohbet, RAG context olmadan."""
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": message}],
            temperature=0.7,
        )
        return response.choices[0].message.content
