#!/usr/bin/env python3
"""
index_docs.py — Vivado/Vitis UG dökümanlarını DocStore'a index'le
===================================================================
Seçili Xilinx PDF'lerini db/chroma_docs/ koleksiyonuna ekler.

Kullanım:
    cd /home/test123/GC-RAG-VIVADO-2
    source .venv/bin/activate
    python scripts/index_docs.py              # sadece yeni/eksik olanları ekle
    python scripts/index_docs.py --reset      # koleksiyonu sıfırlayıp yeniden index'le
    python scripts/index_docs.py --list       # hangi dökümanlar index'li?
    python scripts/index_docs.py --dry-run    # chunk sayısını tahmin et (eklemez)
"""

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

# ─────────────────────────────────────────────────────────────────────────────
# Döküman kataloğu — eklenecek PDF'ler ve metadata
# ─────────────────────────────────────────────────────────────────────────────

_VITIS_DIR = Path("/home/test123/fpga_asist_dev/validation_test/Vitis_Products")

DOC_CATALOG = [
    # ── Vivado Synthesis & Implementation ────────────────────────────────────
    {
        "doc_id": "ug901",
        "doc_title": "Vivado Design Suite User Guide: Synthesis (UG901)",
        "path": _VITIS_DIR / "Vivado/2025.1_English/ug901-vivado-synthesis.pdf",
        "category": "synthesis",
    },
    {
        "doc_id": "ug904",
        "doc_title": "Vivado Design Suite User Guide: Implementation (UG904)",
        "path": _VITIS_DIR / "Vivado/2025.1_English/ug904-vivado-implementation.pdf",
        "category": "implementation",
    },
    # ── Timing Constraints ────────────────────────────────────────────────────
    {
        "doc_id": "ug903",
        "doc_title": "Vivado Design Suite User Guide: Using Constraints (UG903)",
        "path": _VITIS_DIR / "Vivado/2025.1_English/ug903-vivado-using-constraints.pdf",
        "category": "constraints",
    },
    {
        "doc_id": "ug1292",
        "doc_title": "UltraFast Design Methodology: Timing Closure Quick Reference (UG1292)",
        "path": _VITIS_DIR / "Vivado/2025.1_English/ug1292-ultrafast-timing-closure-quick-reference.pdf",
        "category": "constraints",
    },
    # ── MicroBlaze Reference ──────────────────────────────────────────────────
    {
        "doc_id": "ug984",
        "doc_title": "MicroBlaze Processor Reference Guide (UG984)",
        "path": _VITIS_DIR / "Vivado/2025.1_English/ug984-vivado-microblaze-ref.pdf",
        "category": "microblaze",
    },
    # ── IP & Block Design ─────────────────────────────────────────────────────
    {
        "doc_id": "xapp1168",
        "doc_title": "AXI4 IP in IP Integrator (XAPP1168)",
        "path": _VITIS_DIR / "Vivado/xapp1168-axi-ip-integrator.pdf",
        "category": "axi",
    },
    {
        "doc_id": "ug896",
        "doc_title": "Vivado Design Suite User Guide: Designing with IP (UG896)",
        "path": _VITIS_DIR / "Vivado/2025.1_English/ug896-vivado-ip.pdf",
        "category": "ip",
    },
    # ── TCL Scripting ─────────────────────────────────────────────────────────
    {
        "doc_id": "ug894",
        "doc_title": "Vivado Design Suite Tcl Command Reference Guide (UG894)",
        "path": _VITIS_DIR / "Vivado/2025.1_English/ug894-vivado-tcl-scripting.pdf",
        "category": "tcl",
    },
    # ── I/O & Clock Planning ──────────────────────────────────────────────────
    {
        "doc_id": "ug899",
        "doc_title": "Vivado Design Suite User Guide: I/O and Clock Planning (UG899)",
        "path": _VITIS_DIR / "Vivado/2025.1_English/ug899-vivado-io-clock-planning.pdf",
        "category": "io_clock",
    },
    # ── Vitis Embedded (Zynq/MicroBlaze SDK) ─────────────────────────────────
    {
        "doc_id": "ug1400",
        "doc_title": "Vitis Unified Software Platform: Embedded Software Development (UG1400)",
        "path": _VITIS_DIR / "2025.1_English/ug1400-vitis-embedded.pdf",
        "category": "vitis_embedded",
    },
    # ── Quick Reference ───────────────────────────────────────────────────────
    {
        "doc_id": "ug975",
        "doc_title": "Vivado Design Suite Quick Reference Guide (UG975)",
        "path": _VITIS_DIR / "Vivado/ug975-vivado-quick-reference.pdf",
        "category": "reference",
    },
]


def main():
    parser = argparse.ArgumentParser(description="DocStore PDF indexer")
    parser.add_argument("--reset",   action="store_true", help="Koleksiyonu sıfırla ve yeniden index'le")
    parser.add_argument("--list",    action="store_true", help="Index'li dökümanları listele")
    parser.add_argument("--dry-run", action="store_true", help="Index'lemeden önce chunk tahmini yap")
    parser.add_argument("--category", default="", help="Sadece bu kategorideki dökümanları index'le")
    args = parser.parse_args()

    from rag_v2.doc_store import DocStore
    ds = DocStore()

    if args.list:
        indexed = ds.indexed_docs()
        print(f"\nIndex'li dökümanlar ({len(indexed)}):")
        for d in sorted(indexed):
            print(f"  {d}")
        print(f"\nToplam chunk: {ds.count()}")
        return

    if args.reset:
        import shutil
        persist = Path(_ROOT / "db/chroma_docs")
        if persist.exists():
            shutil.rmtree(persist)
            print("✓ chroma_docs koleksiyonu sıfırlandı.")
        ds = DocStore()  # yeniden başlat

    catalog = DOC_CATALOG
    if args.category:
        catalog = [d for d in catalog if d["category"] == args.category]
        print(f"Kategori filtresi: '{args.category}' — {len(catalog)} döküman")

    total_added = 0
    total_skipped = 0
    errors = []

    for entry in catalog:
        doc_id = entry["doc_id"]
        doc_title = entry["doc_title"]
        path = Path(entry["path"])

        if not path.exists():
            print(f"  ⚠ Dosya bulunamadı: {path.name}")
            errors.append(doc_id)
            continue

        size_mb = path.stat().st_size / 1024 / 1024

        if args.dry_run:
            # Chunk sayısı tahmini (dosya boyutuna göre ~500 bytes/chunk)
            est_chunks = max(1, int(path.stat().st_size / 600))
            print(f"  [{doc_id}] {path.name} ({size_mb:.1f} MB) → ~{est_chunks} chunk (tahmin)")
            continue

        if ds.is_indexed(doc_id) and not args.reset:
            print(f"  ✓ {doc_id} — zaten index'li, atlanıyor")
            total_skipped += 1
            continue

        print(f"  ⏳ {doc_id}: {path.name} ({size_mb:.1f} MB) index'leniyor…", end="", flush=True)
        try:
            n = ds.index_pdf(str(path), doc_id, doc_title)
            print(f" → {n} chunk eklendi")
            total_added += n
        except Exception as e:
            print(f" → HATA: {e}")
            errors.append(doc_id)

    if not args.dry_run:
        print(f"\n{'='*50}")
        print(f"Eklendi : {total_added} chunk")
        print(f"Atlandı : {total_skipped} döküman (zaten var)")
        print(f"Toplam  : {ds.count()} chunk")
        if errors:
            print(f"Hata    : {errors}")


if __name__ == "__main__":
    main()
