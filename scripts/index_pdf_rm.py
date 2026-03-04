#!/usr/bin/env python3
"""
Nexys A7 Reference Manual PDF Indexer
======================================
nexys-a7_rm.pdf'i okur, bölüm bazlı chunk'lara böler ve
SourceChunkStore'a (ChromaDB) ekler.

Çalıştırma:
    python scripts/index_pdf_rm.py
    python scripts/index_pdf_rm.py --dry-run
    python scripts/index_pdf_rm.py --show-chunks

Gereksinim:
    pip install pymupdf   (zaten kurulu)
"""

from __future__ import annotations

import re
import sys
import argparse
from pathlib import Path
from typing import List, Tuple

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

PDF_PATH  = Path("/home/test123/Documents/nexys-a7_rm.pdf")
PROJECT   = "PROJECT-A"
FILE_TYPE = "pdf"

# Bölüm başlığı → ilgili graph node'ları
SECTION_NODE_MAP = {
    "ddr":         ["COMP-A-mig_7series_0"],
    "memory":      ["COMP-A-mig_7series_0"],
    "clock":       ["COMP-A-clk_wiz_0"],
    "oscillator":  ["COMP-A-clk_wiz_0"],
    "audio":       ["COMP-A-tone_generator_0", "COMP-A-fifo2audpwm_0"],
    "pwm":         ["COMP-A-tone_generator_0", "COMP-A-fifo2audpwm_0"],
    "dma":         ["COMP-A-axi_dma_0"],
    "uart":        ["COMP-A-helloworld"],
    "fpga config": [],
    "ethernet":    [],
    "usb":         [],
    "vga":         [],
    "accelerom":   [],
    "temperature": [],
    "microphone":  [],
    "pmod":        [],
}


# ─────────────────────────────────────────────────────────────────────────────
# PDF metin çıkarma (pymupdf)
# ─────────────────────────────────────────────────────────────────────────────

def extract_pages(pdf_path: Path) -> List[Tuple[int, str]]:
    """
    Her sayfanın metnini (sayfa_no, metin) tuple listesi olarak döndür.
    pymupdf (fitz) kullanır.
    """
    import fitz  # pymupdf
    doc = fitz.open(str(pdf_path))
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        pages.append((i + 1, text))
    doc.close()
    return pages


def build_full_text(pages: List[Tuple[int, str]]) -> Tuple[str, List[int]]:
    """
    Tüm sayfaları birleştir.
    Sayfa sınırlarını karakter offset olarak tut (page_offsets[i] = sayfa i'nin başlangıcı).
    """
    parts = []
    offsets = []
    pos = 0
    for _, text in pages:
        offsets.append(pos)
        parts.append(text)
        pos += len(text) + 1  # +1 = ayırıcı \n
    return "\n".join(parts), offsets


def char_to_page(offset: int, page_offsets: List[int]) -> int:
    """Karakter offseti → sayfa numarası."""
    page = 1
    for i, po in enumerate(page_offsets):
        if offset >= po:
            page = i + 1
        else:
            break
    return page


# ─────────────────────────────────────────────────────────────────────────────
# Bölüm tabanlı chunklama
# ─────────────────────────────────────────────────────────────────────────────

# "1 Functional Description", "3.1 DDR2", "15.2 Pulse-Width Modulation"
# PDF metninde bölüm başlıkları genellikle kendi satırında: \n1.1 Başlık\n
_SECTION_RE = re.compile(
    r'(?:^|\n)(\d+(?:\.\d+)?)\s{1,4}([A-Z][A-Za-z0-9/ ()\-]+?)(?:\s*\.{3,}\s*\d+)?\s*\n',
)


def split_sections(full_text: str, page_offsets: List[int]) -> List[dict]:
    """
    Bölüm başlıklarına göre metni böl.
    Her bölüm: {number, title, content, start_page}
    """
    matches = list(_SECTION_RE.finditer(full_text))

    valid = []
    for m in matches:
        title = m.group(2).strip()
        if len(title) < 3:
            continue
        num = m.group(1)
        # Geçersiz bölüm numaralarını filtrele
        # Nexys A7 RM'de 1-15 arası bölümler var; alt bölüm: 1.1, 2.3, ...
        top = int(num.split(".")[0])
        if top > 15:
            continue
        valid.append(m)

    raw_sections = []
    for i, m in enumerate(valid):
        num   = m.group(1)
        title = m.group(2).strip()
        start = m.end()
        end   = valid[i + 1].start() if i + 1 < len(valid) else len(full_text)

        content = full_text[start:end].strip()
        # Çok kısa içerik → TOC satırı, atla
        if len(content) < 80:
            continue

        start_page = char_to_page(m.start(), page_offsets)

        raw_sections.append({
            "number":     num,
            "title":      title,
            "content":    content,
            "start_page": start_page,
        })

    # Aynı bölüm numarası iki kez görünürse (TOC + gerçek içerik):
    # Gerçek içerik asıl sayfasında bulunur (daha yüksek sayfa numarası).
    # TOC sayfaları (1-5) ve özellik tablosu sayfaları (5-6) hariç tutulur.
    # Eğer birden fazla eşleşme varsa: en yüksek start_page olanı tut.
    best: dict[str, dict] = {}
    for sec in raw_sections:
        key = sec["number"]
        if key not in best:
            best[key] = sec
        else:
            # Daha yüksek sayfa = asıl içerik (TOC değil)
            if sec["start_page"] > best[key]["start_page"]:
                best[key] = sec

    # Bölüm numarasına göre sırala
    def sort_key(num: str):
        parts = [int(x) for x in num.split(".")]
        return parts + [0] * (4 - len(parts))

    return sorted(best.values(), key=lambda s: sort_key(s["number"]))


def merge_short_sections(sections: List[dict], min_chars: int = 200) -> List[dict]:
    """
    Çok kısa bölümleri (alt bölüm) bir öncekiyle birleştir.
    Örn: "3.1 DDR2" başlığı bağımsız uzunsa kalsın, çok kısaysa üst bölüme ekle.
    """
    merged = []
    for sec in sections:
        if merged and len(sec["content"]) < min_chars and "." in sec["number"]:
            # Alt bölüm ve kısa → bir öncekiyle birleştir
            merged[-1]["content"] += f"\n\n## {sec['number']} {sec['title']}\n{sec['content']}"
            merged[-1]["title"] += f" + {sec['title']}"
        else:
            merged.append(dict(sec))
    return merged


MAX_CHUNK_CHARS = 3000

def split_long_section(sec: dict) -> List[dict]:
    """3000 karakterden uzun bölümleri parçala."""
    content = sec["content"]
    if len(content) <= MAX_CHUNK_CHARS:
        return [sec]

    parts = []
    # Paragraf sınırında böl (\n\n)
    paragraphs = re.split(r'\n\n+', content)
    current = ""
    part_idx = 0
    for para in paragraphs:
        if len(current) + len(para) + 2 > MAX_CHUNK_CHARS and current:
            parts.append({
                "number":     f"{sec['number']}.p{part_idx}",
                "title":      f"{sec['title']} (devam {part_idx})",
                "content":    current.strip(),
                "start_page": sec["start_page"],
            })
            current = para
            part_idx += 1
        else:
            current = current + "\n\n" + para if current else para

    if current.strip():
        parts.append({
            "number":     f"{sec['number']}.p{part_idx}",
            "title":      f"{sec['title']} (devam {part_idx})" if part_idx > 0 else sec["title"],
            "content":    current.strip(),
            "start_page": sec["start_page"],
        })

    return parts if parts else [sec]


# ─────────────────────────────────────────────────────────────────────────────
# Chunk oluşturma
# ─────────────────────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    """Başlığı chunk_id-safe slug'a dönüştür."""
    t = re.sub(r'[^a-z0-9]+', '_', text.lower())
    return t.strip('_')[:40]


def _get_node_ids(title: str) -> List[str]:
    """Bölüm başlığından ilgili graph node_id'lerini bul."""
    t = title.lower()
    for keyword, nodes in SECTION_NODE_MAP.items():
        if keyword in t:
            return nodes
    return []


def sections_to_chunks(sections: List[dict]) -> List:
    """Section dict listesini SourceChunk listesine dönüştür."""
    from rag_v2.source_chunk_store import SourceChunk

    chunks = []
    seen_ids: set = set()

    for sec in sections:
        for part in split_long_section(sec):
            slug = _slug(f"{part['number']}_{part['title']}")
            chunk_id = f"nexys_a7_rm_{slug}"

            # Çakışma önleme
            if chunk_id in seen_ids:
                chunk_id = f"{chunk_id}_{len(seen_ids)}"
            seen_ids.add(chunk_id)

            # İçerik: başlık + metin
            header = f"[Nexys A7 Reference Manual — Bölüm {part['number']}: {part['title']}]\n"
            content = header + part["content"]
            content = content[:MAX_CHUNK_CHARS]

            node_ids = _get_node_ids(part["title"])

            chunks.append(SourceChunk(
                chunk_id=chunk_id,
                content=content,
                file_path=str(PDF_PATH),
                file_type=FILE_TYPE,
                project=PROJECT,
                start_line=part["start_page"],   # PDF için sayfa numarası
                end_line=part["start_page"],
                chunk_label=f"{part['number']} {part['title']}",
                related_node_ids=node_ids,
            ))

    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# Ana işlev
# ─────────────────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, show_chunks: bool = False):
    print("=" * 70)
    print("  Nexys A7 Reference Manual — PDF Indexer")
    print("=" * 70)

    if not PDF_PATH.exists():
        print(f"  HATA: PDF bulunamadı: {PDF_PATH}")
        sys.exit(1)

    # 1. PDF'den metin çıkar
    print(f"  PDF okunuyor: {PDF_PATH.name}")
    pages = extract_pages(PDF_PATH)
    print(f"  Sayfa sayısı: {len(pages)}")

    full_text, page_offsets = build_full_text(pages)
    print(f"  Toplam metin: {len(full_text):,} karakter")

    # 2. Bölümlere böl
    sections = split_sections(full_text, page_offsets)
    print(f"  Tespit edilen bölüm: {len(sections)}")

    sections = merge_short_sections(sections)
    print(f"  Birleştirme sonrası: {len(sections)}")

    # 3. Chunk'lara dönüştür
    chunks = sections_to_chunks(sections)
    print(f"  Oluşturulan chunk: {len(chunks)}")

    if show_chunks or dry_run:
        print()
        for c in chunks:
            print(f"  [{c.chunk_label:45s}] {len(c.content):4d} chars | sayfa {c.start_line} | nodes: {c.related_node_ids or ['—']}")

    if dry_run:
        print(f"\n  [DRY-RUN] Hiçbir değişiklik yapılmadı.")
        return

    # 4. SourceChunkStore'a ekle
    from rag_v2.source_chunk_store import SourceChunkStore
    store = SourceChunkStore(
        persist_directory=str(_ROOT / "db" / "chroma_source_chunks")
    )

    count_before = store.count()
    print(f"\n  ChromaDB mevcut kayıt: {count_before}")
    print(f"  Ekleniyor...")

    added = store.add_chunks(chunks)

    count_after = store.count()
    print(f"  Eklenen chunk: {added}")
    print(f"  ChromaDB toplam: {count_after}")
    print(f"\n  ✅ Tamamlandı!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nexys A7 RM PDF Indexer")
    parser.add_argument("--dry-run", action="store_true",
                        help="Chunk listesini göster, kaydetme")
    parser.add_argument("--show-chunks", action="store_true",
                        help="Tüm chunk'ları listele")
    args = parser.parse_args()

    run(dry_run=args.dry_run, show_chunks=args.show_chunks)
