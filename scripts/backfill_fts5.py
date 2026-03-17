#!/usr/bin/env python3
"""
backfill_fts5.py — ChromaDB → FTS5 tek seferlik migrasyon

Mevcut ChromaDB koleksiyonlarındaki chunk'ları SQLite FTS5'e kopyalar.
re-embed yapmaz, sadece metin içeriğini FTS5'e yükler.
source_chunks backfill ayrıca signals tablosunu da doldurur.

Kullanım:
    python scripts/backfill_fts5.py           # her iki store
    python scripts/backfill_fts5.py --source  # sadece source chunks
    python scripts/backfill_fts5.py --docs    # sadece doc store
    python scripts/backfill_fts5.py --force   # mevcut FTS5 sıfırla
    python scripts/backfill_fts5.py --signals # sadece signals tablosunu yenile (chunk'lar tamam)
"""

import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rag_v2.source_chunk_store import SourceChunkStore, _extract_signals_from_items
from rag_v2.doc_store import DocStore


def backfill_source(force: bool = False):
    sc = SourceChunkStore("db/chroma_source_chunks")
    chroma_count = sc.count()
    fts_count = sc._fts.count()
    sig_count = sc._fts.signal_count()

    print(f"[source_chunks] ChromaDB: {chroma_count} | FTS5: {fts_count} | Signals: {sig_count}")

    if not force and fts_count == chroma_count:
        print("[source_chunks] Zaten senkron — atlandı.")
        return

    if force:
        print("[source_chunks] Force flag — FTS5 sıfırlanıyor...")
        sc._fts.reset()
        sc._fts_synced = False

    t0 = time.time()
    sc._ensure_fts5()
    elapsed = time.time() - t0
    print(f"[source_chunks] Backfill tamamlandı: {sc._fts.count()} chunk, "
          f"{sc._fts.signal_count()} signal ({elapsed:.2f}s)")


def backfill_signals_only():
    """Chunk'lar FTS5'te mevcut ama signals tablosu boşsa yeniden doldur."""
    sc = SourceChunkStore("db/chroma_source_chunks")
    fts_count = sc._fts.count()
    sig_count = sc._fts.signal_count()

    print(f"[source_chunks] FTS5: {fts_count} chunk | Signals: {sig_count}")

    if fts_count == 0:
        print("[source_chunks] FTS5 boş — önce tam backfill çalıştırın.")
        return

    print("[source_chunks] Signals tablosu yeniden oluşturuluyor...")
    # FTS5'ten tüm chunk'ları oku
    rows = sc._fts._conn.execute(
        "SELECT chunk_id, content, project, file_type FROM fts"
    ).fetchall()

    items = []
    for chunk_id, content, project, file_type in rows:
        # chunk_label ve file_path chunk_id'den parse et
        parts = chunk_id.rsplit("_", 1)
        chunk_label = parts[-1] if len(parts) == 2 else chunk_id
        file_path = ""
        items.append({
            "chunk_id": chunk_id,
            "content": content or "",
            "project": project or "",
            "file_type": file_type or "",
            "chunk_label": chunk_label,
            "file_path": file_path,
        })

    t0 = time.time()
    # Signals tablosunu temizle ve yeniden doldur
    sc._fts._conn.execute("DELETE FROM signals")
    sc._fts._conn.commit()

    signals = _extract_signals_from_items(items)
    if signals:
        sc._fts.add_signals(signals)

    elapsed = time.time() - t0
    unique = len(sc._fts.get_unique_signals())
    print(f"[source_chunks] Signals yenilendi: {sc._fts.signal_count()} total, "
          f"{unique} unique ({elapsed:.2f}s)")


def backfill_docs(force: bool = False):
    ds = DocStore()
    chroma_count = ds.count()
    fts_count = ds._fts.count()

    print(f"[vivado_docs] ChromaDB: {chroma_count} | FTS5: {fts_count}")

    if not force and fts_count == chroma_count:
        print("[vivado_docs] Zaten senkron — atlandı.")
        return

    if force:
        print("[vivado_docs] Force flag — FTS5 sıfırlanıyor...")
        ds._fts.reset()
        ds._fts_synced = False

    t0 = time.time()
    ds._ensure_fts5()
    elapsed = time.time() - t0
    print(f"[vivado_docs] Backfill tamamlandı: {ds._fts.count()} chunk ({elapsed:.2f}s)")


def main():
    parser = argparse.ArgumentParser(description="ChromaDB → FTS5 migrasyon")
    parser.add_argument("--source",  action="store_true", help="Sadece source_chunks")
    parser.add_argument("--docs",    action="store_true", help="Sadece vivado_docs")
    parser.add_argument("--force",   action="store_true", help="Mevcut FTS5 sıfırla ve yeniden yükle")
    parser.add_argument("--signals", action="store_true", help="Sadece signals tablosunu yenile")
    args = parser.parse_args()

    if args.signals:
        print("=== FTS5 Signals Backfill ===")
        backfill_signals_only()
        return

    run_source = args.source or (not args.source and not args.docs)
    run_docs   = args.docs   or (not args.source and not args.docs)

    print("=== FTS5 Backfill ===")
    if run_source:
        backfill_source(force=args.force)
    if run_docs:
        backfill_docs(force=args.force)

    print()
    print("FTS5 DB dosyaları:")
    for p in [Path("db/fts5_source.db"), Path("db/fts5_docs.db")]:
        if p.exists():
            size_mb = p.stat().st_size / (1024 * 1024)
            print(f"  {p}: {size_mb:.1f} MB")

    # Signals özeti
    from rag_v2.source_chunk_store import SourceChunkStore
    try:
        sc = SourceChunkStore("db/chroma_source_chunks")
        total = sc._fts.signal_count()
        unique = len(sc._fts.get_unique_signals())
        print(f"\nSignals: {total} total, {unique} unique (proje-özel)")
    except Exception:
        pass


if __name__ == "__main__":
    main()
