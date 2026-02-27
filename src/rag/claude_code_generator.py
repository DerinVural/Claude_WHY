"""
ClaudeCodeGenerator — API key gerektirmeyen Claude generator.

Claude Code CLI'nin `--print` modunu subprocess üzerinden çağırır.
Anthropic API kredisi tüketmez; Claude Code subscription kullanır.

Prompt stdin'den geçirilir — uzun context (14K+ char) için güvenli.
"""

from __future__ import annotations

import os
import subprocess
import shutil
import tempfile
import time
from typing import List, Any, Optional


_CLAUDE_BIN: str | None = shutil.which("claude")


def _is_available() -> bool:
    return _CLAUDE_BIN is not None


def _run_claude(full_prompt: str, model: str, timeout: int) -> str:
    """
    claude --print ile LLM çağrısı.
    - Prompt stdin dosyasından okunur (komut satırı arg limiti yok)
    - stdout/stderr temp dosyaya yönlendirilir (pipe hang sorunu yok)
    - CLAUDECODE env unset edilir (nested session engeli kalkar)
    """
    # CLAUDECODE → nested session engelini kaldır
    # ANTHROPIC_API_KEY → claude CLI subscription auth kullanmaya zorla (API key değil)
    _STRIP_KEYS = {"CLAUDECODE", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"}
    env = {k: v for k, v in os.environ.items() if k not in _STRIP_KEYS}
    env["NO_COLOR"] = "1"

    # Temp dosyalar
    with tempfile.NamedTemporaryFile(mode="w", suffix="_in.txt",  delete=False, encoding="utf-8") as f:
        f.write(full_prompt)
        in_path = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix="_out.txt", delete=False) as f:
        out_path = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix="_err.txt", delete=False) as f:
        err_path = f.name

    cmd = [
        _CLAUDE_BIN,
        "--print",
        "--no-session-persistence",
        "--output-format", "text",
        "--model", model,
    ]

    try:
        with open(in_path,  "r", encoding="utf-8") as in_fh, \
             open(out_path, "w") as out_fh, \
             open(err_path, "w") as err_fh:
            p = subprocess.Popen(
                cmd,
                env=env,
                stdin=in_fh,
                stdout=out_fh,
                stderr=err_fh,
            )
            try:
                rc = p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
                raise RuntimeError(f"claude --print zaman aşımı ({timeout}s)")

        with open(out_path, encoding="utf-8") as f:
            stdout = f.read().strip()
        with open(err_path, encoding="utf-8") as f:
            stderr = f.read().strip()

        if rc != 0:
            raise RuntimeError(
                f"claude --print başarısız (rc={rc}): {stderr[:300] or '(stderr boş)'}"
            )

        if not stdout:
            raise RuntimeError("claude --print boş cevap döndü")

        return stdout

    finally:
        for path in (in_path, out_path, err_path):
            try:
                os.unlink(path)
            except OSError:
                pass


class ClaudeCodeGenerator:
    """
    Claude Code CLI üzerinden çalışan LLM generator.
    API key gerektirmez — Claude Code subscription kullanır.
    ClaudeGenerator ile birebir aynı metot imzaları.
    """

    def __init__(self, model_name: str = "claude-sonnet-4-6", timeout: int = 120):
        self.model_name = model_name
        self.timeout = timeout

        if not _is_available():
            raise RuntimeError("claude CLI bulunamadı. Kurulum: https://claude.ai/download")

    def generate(
        self,
        query: str,
        context_documents: List[Any],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ) -> str:
        # Context oluştur
        parts = []
        for i, doc in enumerate(context_documents, 1):
            if isinstance(doc, str):
                parts.append(doc)
            elif isinstance(doc, dict):
                source = doc.get("metadata", {}).get("filename", f"Kaynak {i}")
                content = doc.get("content", doc.get("document", ""))
                parts.append(f"[{source}]\n{content}")
        context = "\n\n---\n\n".join(parts)

        default_system = (
            "Sen bir FPGA mühendislik asistanısın. "
            "Sana verilen kaynak belgeler FPGA RAG v2 sisteminden alınmıştır. "
            "Yalnızca bu belgelerdeki bilgileri kullan, asla tahmin üretme. "
            "Yanıtını Türkçe ver. Teknik terimleri (sinyal adları, parametre adları) "
            "orijinal haliyle bırak."
        )
        system = system_prompt or default_system

        # System + context + soru tek prompt'ta birleştir (stdin üzerinden)
        full_prompt = (
            f"[SİSTEM TALİMATLARI]\n{system}\n\n"
            f"[BAĞLAM]\n{context}\n\n"
            f"[SORU]\n{query}"
        )

        for attempt in range(3):
            try:
                return _run_claude(full_prompt, self.model_name, self.timeout)
            except RuntimeError as e:
                if attempt < 2 and "overload" in str(e).lower():
                    time.sleep(10 * (attempt + 1))
                    continue
                raise

    def chat(self, message: str) -> str:
        """Basit sohbet, RAG context olmadan."""
        for attempt in range(3):
            try:
                return _run_claude(message, self.model_name, self.timeout)
            except RuntimeError:
                if attempt < 2:
                    time.sleep(3)
                    continue
                raise
