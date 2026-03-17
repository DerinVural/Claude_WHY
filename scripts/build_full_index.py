#!/usr/bin/env python3
"""
FPGA RAG v2 — Full Index Pipeline
====================================
Tüm adımları sırayla çalıştırır. Yarıda kalırsa --resume ile devam eder.

Adımlar:
  1. projects.yaml'a yeni projeleri ekle (discover_projects.py --scan --write)
  2. LLM ile graph node üret (generate_project_node.py --all --skip-existing)
  3. Tüm projeleri kaynak indexle (index_source_files.py)
  4. PDF'leri DocStore'a indexle (index_docs.py --pdfs)

Kullanım:
    python scripts/build_full_index.py
    python scripts/build_full_index.py --resume      # tamamlananları atla
    python scripts/build_full_index.py --status      # ilerleme göster
    python scripts/build_full_index.py --skip-pdfs   # PDF adımını atla
"""

from __future__ import annotations

import sys
import time
import argparse
import subprocess
import json
from pathlib import Path
from datetime import datetime

_ROOT = Path(__file__).parent.parent
_STATE_FILE = _ROOT / "pipeline_state" / "build_full_index_state.json"
_LOG_FILE   = _ROOT / "pipeline_state" / "build_full_index.log"

STEPS = [
    {
        "id": "discover",
        "name": "Proje Keşfi → projects.yaml",
        "cmd": [sys.executable, "scripts/discover_projects.py", "--scan", "--write"],
    },
    {
        "id": "node_gen",
        "name": "LLM Graph Node Üretimi (95 proje)",
        "cmd": [sys.executable, "scripts/generate_project_node.py", "--all", "--skip-existing"],
    },
    {
        "id": "source_index",
        "name": "Kaynak Dosya İndeksleme",
        "cmd": [sys.executable, "scripts/index_source_files.py"],
    },
    {
        "id": "pdf_index",
        "name": "PDF Döküman İndeksleme",
        "cmd": [sys.executable, "scripts/index_docs.py", "--pdfs", "--xilinx-only"],
    },
]


def _load_state() -> dict:
    if _STATE_FILE.exists():
        return json.loads(_STATE_FILE.read_text())
    return {}


def _save_state(state: dict):
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _run_step(step: dict) -> bool:
    """Adımı çalıştır. Başarılıysa True döner."""
    cmd = step["cmd"]
    _log(f">>> Başlıyor: {step['name']}")
    _log(f"    Komut: {' '.join(cmd)}")

    t_start = time.time()
    result = subprocess.run(
        cmd,
        cwd=str(_ROOT),
        capture_output=False,
        text=True,
    )
    elapsed = time.time() - t_start

    if result.returncode == 0:
        _log(f"    ✓ Tamamlandı ({elapsed:.0f}s)")
        return True
    else:
        _log(f"    ✗ HATA (rc={result.returncode}, {elapsed:.0f}s)")
        return False


def run_pipeline(resume: bool = False, skip_pdfs: bool = False):
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = _load_state() if resume else {}

    _log("=" * 72)
    _log("  FPGA RAG v2 — Full Index Pipeline")
    _log(f"  Başlangıç: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _log(f"  Resume: {resume} | Skip PDFs: {skip_pdfs}")
    _log("=" * 72)

    steps = STEPS.copy()
    if skip_pdfs:
        steps = [s for s in steps if s["id"] != "pdf_index"]

    pipeline_start = time.time()
    failed = False

    for step in steps:
        sid = step["id"]

        if resume and state.get(sid) == "done":
            _log(f"  [ATLA] {step['name']} (zaten tamamlandı)")
            continue

        success = _run_step(step)
        state[sid] = "done" if success else "failed"
        _save_state(state)

        if not success:
            _log(f"\n  PIPELINE DURDU: {step['name']} başarısız.")
            _log(f"  Devam etmek için: python scripts/build_full_index.py --resume")
            failed = True
            break

    total = time.time() - pipeline_start
    _log("=" * 72)
    if not failed:
        _log(f"  ✅ TÜM ADIMLAR TAMAMLANDI ({total/60:.1f} dakika)")
        _log(f"  UI: http://localhost:8501")
    else:
        _log(f"  Geçen süre: {total/60:.1f} dakika")
    _log("=" * 72)


def show_status():
    state = _load_state()
    print("\n  Pipeline Durumu:")
    print(f"  {'─' * 50}")
    for step in STEPS:
        sid = step["id"]
        status = state.get(sid, "bekliyor")
        icon = {"done": "✓", "failed": "✗", "bekliyor": "○"}.get(status, "?")
        print(f"  {icon} {step['name']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="FPGA RAG v2 Full Index Pipeline")
    parser.add_argument("--resume",     action="store_true", help="Kaldığı yerden devam et")
    parser.add_argument("--status",     action="store_true", help="Adım durumlarını göster")
    parser.add_argument("--skip-pdfs",  action="store_true", help="PDF adımını atla")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    run_pipeline(resume=args.resume, skip_pdfs=args.skip_pdfs)


if __name__ == "__main__":
    main()
