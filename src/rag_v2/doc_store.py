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
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJ_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJ_ROOT / "src"))

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
        self._bm25 = None          # lazy
        self._bm25_docs: List[str] = []
        self._bm25_ids: List[str] = []
        self._bm25_cache_path = Path(self._persist_dir) / "bm25_cache.pkl"

    # ------------------------------------------------------------------
    # ChromaDB lazy init
    # ------------------------------------------------------------------

    def _get_collection(self):
        if self._collection is None:
            import chromadb
            from chromadb.utils import embedding_functions as ef
            Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=self._persist_dir)
            emb_fn = ef.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            self._collection = client.get_or_create_collection(
                name=self._CHROMA_COLLECTION,
                embedding_function=emb_fn,
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

        col = self._get_collection()
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            col.add(
                ids=[c.chunk_id for c in batch],
                documents=[c.content for c in batch],
                metadatas=[{
                    "doc_id": c.doc_id,
                    "doc_title": c.doc_title,
                    "section": c.section,
                    "page_num": c.page_num,
                } for c in batch],
            )

        # BM25 cache'i geçersiz kıl
        self._bm25 = None
        self._bm25_docs = []
        self._bm25_ids = []
        if self._bm25_cache_path.exists():
            self._bm25_cache_path.unlink()

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
        sem_res = col.query(
            query_texts=[query],
            n_results=n_candidates,
            include=["documents", "metadatas", "distances"],
        )
        sem_ids = sem_res["ids"][0] if sem_res["ids"] else []
        sem_docs = sem_res["documents"][0] if sem_res["documents"] else []
        sem_metas = sem_res["metadatas"][0] if sem_res["metadatas"] else []
        sem_dists = sem_res["distances"][0] if sem_res["distances"] else []

        # 2. BM25 search
        bm25_ranked = self._bm25_search(query, n_candidates)

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

        for rank, (cid, content, meta) in enumerate(bm25_ranked):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
            if cid not in id_to_data:
                id_to_data[cid] = {
                    "chunk_id": cid,
                    "content": content,
                    "doc_id": meta.get("doc_id", ""),
                    "doc_title": meta.get("doc_title", ""),
                    "section": meta.get("section", ""),
                    "page_num": meta.get("page_num", 0),
                    "similarity": 0.0,
                }

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for cid, rrf_score in ranked[:k]:
            d = id_to_data[cid]
            d["rrf_score"] = round(rrf_score, 4)
            # Eşik filtresi — düşük puanlı doc chunk'ları context'i kirletir
            if d["similarity"] >= DOC_SIM_THRESHOLD or rrf_score >= 1.0 / (RRF_K + 2):
                results.append(d)

        return results

    # ------------------------------------------------------------------
    # BM25
    # ------------------------------------------------------------------

    def _build_bm25(self):
        """Lazy BM25 index. Disk cache'i kontrol et."""
        col = self._get_collection()
        total = col.count()
        if total == 0:
            return

        # Disk cache geçerli mi?
        if self._bm25_cache_path.exists():
            try:
                with open(self._bm25_cache_path, "rb") as f:
                    cached = pickle.load(f)
                if cached.get("count") == total:
                    self._bm25 = cached["bm25"]
                    self._bm25_docs = cached["docs"]
                    self._bm25_ids = cached["ids"]
                    self._bm25_metas = cached.get("metas", [])
                    return
            except Exception:
                pass

        # Tüm chunk'ları al
        res = col.get(include=["documents", "metadatas"])
        ids = res.get("ids", [])
        docs = res.get("documents", [])
        metas = res.get("metadatas", [])

        # Tokenize
        tok_re = re.compile(r'[a-zA-Z0-9_]+')
        tokenized = []
        for d in docs:
            tokens = tok_re.findall(d.lower())
            # Alt çizgi split: set_dont_touch → set_dont_touch, set, dont, touch
            expanded = []
            for t in tokens:
                expanded.append(t)
                if "_" in t:
                    expanded.extend(t.split("_"))
            tokenized.append(expanded)

        from rank_bm25 import BM25Okapi
        self._bm25 = BM25Okapi(tokenized)
        self._bm25_docs = docs
        self._bm25_ids = ids
        self._bm25_metas = metas

        # Disk'e yaz
        Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
        try:
            with open(self._bm25_cache_path, "wb") as f:
                pickle.dump({
                    "count": total,
                    "bm25": self._bm25,
                    "docs": docs,
                    "ids": ids,
                    "metas": metas,
                }, f)
        except Exception:
            pass

    def _bm25_search(self, query: str, n: int) -> List[Tuple[str, str, Dict]]:
        """BM25 arama — [(chunk_id, content, meta)] döndürür."""
        try:
            if self._bm25 is None:
                self._build_bm25()
            if self._bm25 is None:
                return []

            tok_re = re.compile(r'[a-zA-Z0-9_]+')
            q_tokens = tok_re.findall(query.lower())
            expanded = []
            for t in q_tokens:
                expanded.append(t)
                if "_" in t:
                    expanded.extend(t.split("_"))

            scores = self._bm25.get_scores(expanded)
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n]
            results = []
            for i in top_indices:
                if scores[i] > 0:
                    meta = self._bm25_metas[i] if hasattr(self, "_bm25_metas") else {}
                    results.append((self._bm25_ids[i], self._bm25_docs[i], meta))
            return results
        except Exception:
            return []

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
                # Büyük bölümü paragraf sınırında böl
                parts = self._split_text(sec_text)
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
