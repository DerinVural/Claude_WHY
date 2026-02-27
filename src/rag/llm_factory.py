"""
LLM Factory — Claude Code CLI öncelikli generator seçici.

Öncelik:
  1. ClaudeCodeGenerator (claude --print, API key yok, subscription kullanır)
  2. ClaudeGenerator     (ANTHROPIC_API_KEY, API kredi kullanır)

Kullanım:
    from rag.llm_factory import get_llm
    llm = get_llm()          # claude-sonnet-4-6 döner
    llm = get_llm("claude-sonnet-4-6")
"""

from __future__ import annotations
import os


def get_llm(model_name: str = "claude-sonnet-4-6"):
    """
    Kullanılabilir en iyi Claude generator'ı döndür.

    1. Claude Code CLI (API key gerektirmez) — öncelikli
    2. Anthropic API key (ANTHROPIC_API_KEY) — fallback

    İkisi de yoksa None döner.
    """
    # ── 1. Claude Code CLI ─────────────────────────────────────────────────────
    try:
        from rag.claude_code_generator import ClaudeCodeGenerator, _is_available
        if _is_available():
            llm = ClaudeCodeGenerator(model_name=model_name)
            print(f"[LLM] Claude Code CLI → {model_name}")
            return llm
    except Exception as e:
        print(f"[LLM] Claude Code CLI kurulamadı: {e}")

    # ── 2. Anthropic API key fallback ──────────────────────────────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key and not api_key.startswith("your-"):
        try:
            from rag.claude_generator import ClaudeGenerator
            llm = ClaudeGenerator(api_key=api_key, model_name=model_name)
            print(f"[LLM] Anthropic API key → {model_name}")
            return llm
        except Exception as e:
            print(f"[LLM] Anthropic API key başarısız: {e}")

    print("[LLM] UYARI: Hiçbir LLM backend kullanılamıyor.")
    return None
