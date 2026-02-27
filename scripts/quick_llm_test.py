#!/usr/bin/env python3
"""
LLM bağlantı testi — Claude Code CLI üzerinden.
Terminalden çalıştırın (Claude Code dışında):

    cd /home/test123/GC-RAG-VIVADO-2
    source .venv/bin/activate
    python3 scripts/quick_llm_test.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from rag.llm_factory import get_llm

print("=" * 50)
print("  LLM Bağlantı Testi")
print("=" * 50)

llm = get_llm("claude-sonnet-4-6")
if llm is None:
    print("HATA: LLM başlatılamadı.")
    sys.exit(1)

print(f"Generator: {type(llm).__name__}")
print("Test sorgusu gönderiliyor...")

cevap = llm.generate(
    query="Bu bir test. 'Bağlantı başarılı' yaz.",
    context_documents=["Test context."],
)
print(f"\nCevap: {cevap[:200]}")
print("\n✓ Test başarılı!")
