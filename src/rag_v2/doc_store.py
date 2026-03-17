"""
DocStore — FPGA RAG v2 — 5th Store
====================================
Vivado / Vitis kullanım dökümanları (Xilinx UG/XAPP PDF'leri) için
ayrı ChromaDB koleksiyonu.

Proje kaynak dosyalarından (SourceChunkStore) bağımsız tutulur:
  SourceChunkStore  → "source_chunks"  (proje kaynak kodu)
  DocStore          → "vivado_docs"    (Xilinx UG/XAPP referans dökümanları)

Neden ayrı koleksiyon?
  - Proje-spesifik retrieval'ı bozmaz (cross-collection noise yok)
  - Dökümanlar statik → BM25 invalidation gerekmez
  - Router, proje sinyali zayıfsa veya genel Vivado sorusu varsa doc_store'a bakar

ChromaDB koleksiyonu: "vivado_docs"
Persist dizini     : db/chroma_docs/
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJ_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJ_ROOT / "src"))

from rag_v2.fts5_index import FTS5Index

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

MAX_CHUNK_CHARS = 1800    # UG'ler daha uzun bölümlere sahip — biraz büyük tut
MIN_CHUNK_CHARS = 80
DOC_SIM_THRESHOLD = 0.35  # Bu eşiğin altındaki doc chunk'ları context'e eklenmez


# ─────────────────────────────────────────────────────────────────────────────
# DocChunk dataclass
# ─────────────────────────────────────────────────────────────────────────────

class DocChunk:
    __slots__ = ("chunk_id", "content", "doc_id", "doc_title", "section", "page_num")

    def __init__(
        self,
        chunk_id: str,
        content: str,
        doc_id: str,
        doc_title: str = "",
        section: str = "",
        page_num: int = 0,
    ):
        self.chunk_id = chunk_id
        self.content = content
        self.doc_id = doc_id
        self.doc_title = doc_title
        self.section = section
        self.page_num = page_num


# ─────────────────────────────────────────────────────────────────────────────
# DocStore
# ─────────────────────────────────────────────────────────────────────────────

class DocStore:
    """
    Vivado/Vitis UG dökümanları için ChromaDB + BM25 hibrit arama.

    Kullanım:
        ds = DocStore()
        ds.index_pdf("/path/to/ug901.pdf", "ug901", "Vivado Synthesis")
        results = ds.search("set_dont_touch synthesis attribute", n_results=4)
    """

    _CHROMA_COLLECTION = "vivado_docs"

    def __init__(self, persist_dir: str = "db/chroma_docs"):
        self._persist_dir = str(_PROJ_ROOT / persist_dir)
        self._collection = None
        # FTS5 keyword index — disk-persistent, incremental, zero cold-start
        _fts_db = _PROJ_ROOT / "db" / "fts5_docs.db"
        self._fts = FTS5Index(str(_fts_db))
        self._fts_synced = False

    # ------------------------------------------------------------------
    # ChromaDB lazy init
    # ------------------------------------------------------------------

    def _get_collection(self):
        if self._collection is None:
            import chromadb
            Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=self._persist_dir)
            # External embeddings (paraphrase-multilingual-mpnet-base-v2, 768-dim)
            # shared singleton from embedder.py — model yalnızca bir kez yüklenir.
            self._collection = client.get_or_create_collection(
                name=self._CHROMA_COLLECTION,
                embedding_function=None,  # external
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    # ------------------------------------------------------------------
    # PDF indexing
    # ------------------------------------------------------------------

    def is_indexed(self, doc_id: str) -> bool:
        """Bu doc_id ile chunk var mı?"""
        col = self._get_collection()
        res = col.get(where={"doc_id": doc_id}, limit=1)
        return len(res.get("ids", [])) > 0

    def index_pdf(self, pdf_path: str, doc_id: str, doc_title: str = "") -> int:
        """
        PDF dosyasını chunk'la ve ChromaDB'ye ekle.
        Zaten indexlenmişse atlar.
        Returns: chunk count added (0 if skipped).
        """
        if self.is_indexed(doc_id):
            return 0

        chunks = self._chunk_pdf(pdf_path, doc_id, doc_title or Path(pdf_path).stem)
        if not chunks:
            return 0

        from rag_v2.embedder import embed_texts
        col = self._get_collection()
        batch_size = 64
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c.content for c in batch]
            embeddings = embed_texts(texts)
            col.add(
                ids=[c.chunk_id for c in batch],
                documents=texts,
                embeddings=embeddings,
                metadatas=[{
                    "doc_id": c.doc_id,
                    "doc_title": c.doc_title,
                    "section": c.section,
                    "page_num": c.page_num,
                } for c in batch],
            )

        # FTS5'e incremental ekle
        fts_items = []
        for c in chunks:
            fts_items.append({
                "chunk_id": c.chunk_id,
                "content":  c.content,
                "doc_id":   c.doc_id,
                "doc_title": c.doc_title,
                "section":  c.section,
                "page_num": c.page_num,
            })
        self._fts.add_batch(fts_items)
        self._fts_synced = True

        return len(chunks)

    def count(self) -> int:
        """Toplam chunk sayısı."""
        try:
            return self._get_collection().count()
        except Exception:
            return 0

    def indexed_docs(self) -> List[str]:
        """Index'teki tüm doc_id'leri döndür."""
        col = self._get_collection()
        res = col.get(include=["metadatas"])
        return list({m.get("doc_id", "") for m in res.get("metadatas", []) if m.get("doc_id")})

    # ------------------------------------------------------------------
    # Search — BM25 + semantic hybrid
    # ------------------------------------------------------------------

    def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        BM25 + semantic embedding hibrit arama (RRF birleştirme).
        Sadece DOC_SIM_THRESHOLD üzerindeki sonuçları döndürür.
        """
        col = self._get_collection()
        total = col.count()
        if total == 0:
            return []

        k = min(n_results, total)
        n_candidates = min(n_results * 4, total)

        # 1. Semantic search
        from rag_v2.embedder import embed_text
        q_emb = embed_text(query)
        sem_res = col.query(
            query_embeddings=[q_emb],
            n_results=n_candidates,
            include=["documents", "metadatas", "distances"],
        )
        sem_ids = sem_res["ids"][0] if sem_res["ids"] else []
        sem_docs = sem_res["documents"][0] if sem_res["documents"] else []
        sem_metas = sem_res["metadatas"][0] if sem_res["metadatas"] else []
        sem_dists = sem_res["distances"][0] if sem_res["distances"] else []

        # 2. FTS5 BM25 search
        self._ensure_fts5()
        fts_raw = self._fts.search(query, n_candidates)

        # 3. RRF merge
        RRF_K = 60
        scores: Dict[str, float] = {}
        id_to_data: Dict[str, Dict] = {}

        for rank, (cid, content, meta, dist) in enumerate(
            zip(sem_ids, sem_docs, sem_metas, sem_dists)
        ):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
            similarity = max(0.0, 1.0 - dist)
            id_to_data[cid] = {
                "chunk_id": cid,
                "content": content,
                "doc_id": meta.get("doc_id", ""),
                "doc_title": meta.get("doc_title", ""),
                "section": meta.get("section", ""),
                "page_num": meta.get("page_num", 0),
                "similarity": round(similarity, 4),
            }

        for rank, h in enumerate(fts_raw):
            cid = h["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
            if cid not in id_to_data:
                id_to_data[cid] = {
                    "chunk_id": cid,
                    "content": h["content"],
                    "doc_id": h.get("doc_id", ""),
                    "doc_title": h.get("doc_title", ""),
                    "section": h.get("section", ""),
                    "page_num": h.get("page_num", 0),
                    "similarity": 0.0,
                }

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for cid, rrf_score in ranked[:k]:
            d = id_to_data[cid]
            d["rrf_score"] = round(rrf_score, 4)
            if d["similarity"] >= DOC_SIM_THRESHOLD:
                results.append(d)

        return results

    def search_in_docs(
        self, query: str, doc_ids: List[str], n_per_doc: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Belirli doc_id'lere filtrelenmiş semantic arama.
        IP→Doc yapısal retrieval için: her doc_id için sorguya en yakın n_per_doc chunk döner.
        DOC_SIM_THRESHOLD uygulanmaz — yapısal retrieval, garantili ilgili dok.
        """
        if not doc_ids:
            return []
        col = self._get_collection()
        if col.count() == 0:
            return []

        from rag_v2.embedder import embed_text
        q_emb = embed_text(query)

        results: List[Dict[str, Any]] = []
        seen_ids: set = set()

        for doc_id in doc_ids:
            try:
                res = col.query(
                    query_embeddings=[q_emb],
                    n_results=n_per_doc,
                    where={"doc_id": doc_id},
                    include=["documents", "metadatas", "distances"],
                )
                if not res["ids"] or not res["ids"][0]:
                    continue
                for cid, doc, meta, dist in zip(
                    res["ids"][0], res["documents"][0],
                    res["metadatas"][0], res["distances"][0],
                ):
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        results.append({
                            "chunk_id":  cid,
                            "content":   doc,
                            "doc_id":    meta.get("doc_id", ""),
                            "doc_title": meta.get("doc_title", ""),
                            "section":   meta.get("section", ""),
                            "page_num":  meta.get("page_num", 0),
                            "similarity": round(max(0.0, 1.0 - dist), 4),
                        })
            except Exception:
                continue

        return results

    # ------------------------------------------------------------------
    # FTS5
    # ------------------------------------------------------------------

    def _ensure_fts5(self):
        """
        FTS5 index ChromaDB ile senkron mu kontrol et.
        Değilse tüm koleksiyonu FTS5'e backfill et (tek seferlik, ~5-10 saniye 17K chunk için).
        """
        if self._fts_synced:
            return
        col = self._get_collection()
        chroma_count = col.count()
        if chroma_count == 0:
            self._fts_synced = True
            return
        fts_count = self._fts.count()
        if fts_count == chroma_count:
            self._fts_synced = True
            return
        print(f"  [FTS5-docs] Backfill başlıyor: {chroma_count} chunk ChromaDB → FTS5 ...")
        self._fts.reset()
        # Büyük koleksiyonlar için batch okuma (175K+ chunk desteği)
        BATCH = 2000
        offset = 0
        while True:
            res = col.get(limit=BATCH, offset=offset, include=["documents", "metadatas"])
            ids   = res.get("ids", [])
            if not ids:
                break
            docs  = res.get("documents", [])
            metas = res.get("metadatas", [])
            items = []
            for cid, doc, meta in zip(ids, docs, metas):
                items.append({
                    "chunk_id":  cid,
                    "content":   doc,
                    "doc_id":    meta.get("doc_id", ""),
                    "doc_title": meta.get("doc_title", ""),
                    "section":   meta.get("section", ""),
                    "page_num":  meta.get("page_num", 0),
                })
            self._fts.add_batch(items)
            offset += BATCH
        print(f"  [FTS5-docs] Backfill tamamlandı: {self._fts.count()} chunk")
        self._fts_synced = True

    # ------------------------------------------------------------------
    # PDF chunking — UG format aware
    # ------------------------------------------------------------------

    # Xilinx UG section heading patterns:
    # "Chapter 1: Getting Started"
    # "1 Overview"
    # "1.1 Introduction"
    # "Appendix A: Directives"
    _UG_SECTION_RE = re.compile(
        r'(?m)^[ \t]*'
        r'(?:'
        r'(?:Chapter|Appendix)\s+\w+\s*[:\.\-]\s*[A-Z]'  # Chapter 1: Foo
        r'|(?:[1-9]|[12]\d)(?:\.\d+)*\s+[A-Z][A-Za-z]{2,}'  # 1.1 Foo Bar
        r')'
        r'.{0,80}$'
    )

    # Boilerplate footer patterns for Xilinx UG PDFs
    _FOOTER_RE = re.compile(
        r'(?:'
        r'(?:UG|XAPP|WP|XCN)\d+\s*\([vV][\d\.]+\)[^\n]*\n'  # UG901 (v2019.1) ...
        r'|(?:www\.xilinx\.com|www\.amd\.com)[^\n]*\n'
        r'|Send Feedback[^\n]*\n'
        r'|Xilinx is[^\n]*\n'
        r'|AMD[,\s]+the AMD[^\n]*\n'
        r'|Copyright[^\n]*Xilinx[^\n]*\n'
        r'|Copyright[^\n]*AMD[^\n]*\n'
        r'|Chapter\s+\d+[:\s]*\n'           # standalone "Chapter N:" lines
        r')',
        re.IGNORECASE,
    )

    def _chunk_pdf(self, pdf_path: str, doc_id: str, doc_title: str) -> List[DocChunk]:
        """PDF dosyasını UG section yapısına göre chunk'la."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return []

        try:
            doc = fitz.open(str(pdf_path))
            page_blocks: List[Tuple[int, str]] = []
            for i, page in enumerate(doc):
                txt = page.get_text("text")
                if txt.strip():
                    page_blocks.append((i + 1, txt))
            doc.close()
        except Exception:
            return []

        if not page_blocks:
            return []

        # Tüm sayfaları birleştir — [PAGE N] işaretçileri ile
        full_text = ""
        for pnum, ptxt in page_blocks:
            cleaned = self._FOOTER_RE.sub("", ptxt).strip()
            if cleaned:
                full_text += f"\n[PAGE {pnum}]\n{cleaned}\n"

        # Section sınırlarını bul
        boundaries: List[Tuple[int, str, int]] = []  # (char_pos, title, page_num)
        for m in self._UG_SECTION_RE.finditer(full_text):
            title = m.group(0).strip()
            # Sayfa numarasını çıkar (önceki [PAGE N]'e bak)
            preceding = full_text[:m.start()]
            page_m = re.findall(r'\[PAGE (\d+)\]', preceding)
            pnum = int(page_m[-1]) if page_m else 0
            boundaries.append((m.start(), title, pnum))

        # Fallback: section bulunamazsa → 2'şer sayfa birleştir
        if not boundaries:
            return self._chunk_pdf_pages(page_blocks, doc_id, doc_title)

        boundaries.append((len(full_text), "_end", 0))

        chunks: List[DocChunk] = []
        fname = Path(pdf_path).stem

        for i, (pos, title, pnum) in enumerate(boundaries[:-1]):
            next_pos = boundaries[i + 1][0]
            sec_text = full_text[pos:next_pos].strip()

            if len(sec_text) < MIN_CHUNK_CHARS:
                continue

            label = re.sub(r'[^\w\s]', '_', title)[:50]

            if len(sec_text) <= MAX_CHUNK_CHARS:
                chunks.append(DocChunk(
                    chunk_id=f"{doc_id}_s{i}",
                    content=sec_text,
                    doc_id=doc_id,
                    doc_title=doc_title,
                    section=label,
                    page_num=pnum,
                ))
            else:
                # Büyük bölümü overlap'li paragraf sınırında böl (G2: tablo satırları bölünmez)
                parts = self._split_pdf_text(sec_text)
                for j, part in enumerate(parts):
                    chunks.append(DocChunk(
                        chunk_id=f"{doc_id}_s{i}_{j}",
                        content=part,
                        doc_id=doc_id,
                        doc_title=doc_title,
                        section=f"{label} (p{j+1})",
                        page_num=pnum,
                    ))

        return chunks

    def _chunk_pdf_pages(
        self, page_blocks: List[Tuple[int, str]], doc_id: str, doc_title: str
    ) -> List[DocChunk]:
        """Fallback: 2 sayfa birleştirip chunk yap."""
        chunks = []
        i = 0
        while i < len(page_blocks):
            batch = page_blocks[i:i + 2]
            text = "\n".join(f"[PAGE {p}]\n{t}" for p, t in batch).strip()
            if len(text) >= MIN_CHUNK_CHARS:
                pnum = batch[0][0]
                chunks.append(DocChunk(
                    chunk_id=f"{doc_id}_p{pnum}",
                    content=text[:MAX_CHUNK_CHARS],
                    doc_id=doc_id,
                    doc_title=doc_title,
                    section=f"page {pnum}",
                    page_num=pnum,
                ))
            i += 2
        return chunks

    def _split_text(self, text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
        """Büyük metni paragraf sınırında böl."""
        if len(text) <= max_chars:
            return [text]
        parts = []
        while len(text) > max_chars:
            split_at = text.rfind("\n\n", 0, max_chars)
            if split_at == -1:
                split_at = text.rfind("\n", 0, max_chars)
            if split_at == -1:
                split_at = max_chars
            parts.append(text[:split_at].strip())
            text = text[split_at:].strip()
        if text:
            parts.append(text)
        return [p for p in parts if len(p) >= MIN_CHUNK_CHARS]

    _TABLE_ROW_RE = re.compile(r'^\s*\d+[:\s\|]', re.MULTILINE)

    def _split_pdf_text(
        self, text: str, max_chars: int = MAX_CHUNK_CHARS, overlap: int = 250
    ) -> List[str]:
        """
        G2: PDF için overlap'li bölümleme.
        - Ardışık chunk'lar arasında 250 karakter örtüşme — register tablo satırları kaybolmaz.
        - Split noktası tablo ortasına denk geliyorsa bir önceki boş satıra geri çekilir.
        """
        if len(text) <= max_chars:
            return [text]

        parts: List[str] = []
        prev_tail = ""

        while len(text) > max_chars:
            # Önce \n\n, sonra \n ile bölme noktası bul
            split_at = text.rfind("\n\n", 0, max_chars)
            if split_at == -1:
                split_at = text.rfind("\n", 0, max_chars)
            if split_at <= 0:
                split_at = max_chars

            # Tablo ortasında mı? Son 5 satır tablo satırı ise geri çekil
            candidate_tail = text[:split_at].split("\n")[-5:]
            table_rows = sum(
                1 for ln in candidate_tail
                if self._TABLE_ROW_RE.match(ln) or "\t" in ln
            )
            if table_rows >= 3:
                alt = text.rfind("\n\n", 0, split_at - 1)
                if alt > split_at // 2:
                    split_at = alt

            chunk = (prev_tail + text[:split_at]).strip()
            parts.append(chunk)
            # Overlap: sonraki chunk için önceki chunk'ın sonunu al
            prev_tail = text[max(0, split_at - overlap):split_at]
            text = text[split_at:].strip()

        if text:
            parts.append((prev_tail + text).strip())

        return [p for p in parts if len(p) >= MIN_CHUNK_CHARS]
