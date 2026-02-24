"""Claude LLM for response generation — OpenAIGenerator ile aynı arayüz."""

from typing import List, Any, Optional
import os
from dotenv import load_dotenv

load_dotenv()


class ClaudeGenerator:
    """
    Response generator using Anthropic Claude API.
    OpenAIGenerator / GeminiGenerator ile birebir aynı metot imzaları.

    Desteklenen modeller:
        claude-sonnet-4-6        (varsayılan — hız/kalite dengesi)
        claude-opus-4-6          (en güçlü — aritmetik, derin analiz)
        claude-haiku-4-5-20251001 (en hızlı — düşük maliyet)
    """

    def __init__(
        self,
        api_key: str = None,
        model_name: str = "claude-sonnet-4-6",
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model_name = model_name
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except Exception as e:
                raise RuntimeError(f"Anthropic başlatılamadı: {e}")
        return self._client

    def generate(
        self,
        query: str,
        context_documents: List[Any],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        """
        OpenAIGenerator.generate() ile aynı imza.

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
            "Yanıtını Türkçe ver. Teknik terimleri (sinyal adları, parametre adları) "
            "orijinal haliyle bırak."
        )
        system = system_prompt or default_system

        user_message = f"CONTEXT:\n{context}\n\nSOURU: {query}"

        import time
        for attempt in range(3):
            try:
                response = client.messages.create(
                    model=self.model_name,
                    max_tokens=2048,
                    temperature=temperature,
                    system=system,
                    messages=[
                        {"role": "user", "content": user_message},
                    ],
                )
                return response.content[0].text
            except Exception as e:
                if "overloaded" in str(e).lower() and attempt < 2:
                    time.sleep(10 * (attempt + 1))
                    continue
                raise

    def chat(self, message: str) -> str:
        """Basit sohbet, RAG context olmadan."""
        import time
        client = self._get_client()
        for attempt in range(3):
            try:
                response = client.messages.create(
                    model=self.model_name,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": message}],
                )
                return response.content[0].text
            except Exception as e:
                if "overloaded" in str(e).lower() and attempt < 2:
                    time.sleep(10 * (attempt + 1))
                    continue
                raise
