"""
FTS5Index — SQLite FTS5 tabanlı BM25 keyword arama.

rank-bm25 paketi yerine Python stdlib sqlite3 + FTS5 kullanır.

Avantajlar:
  - Sıfır dış bağımlılık (stdlib sqlite3 + FTS5)
  - Disk-persistent: yeniden başlatmada cold-start yok
  - Incremental insert/delete: tüm corpus'u yeniden tokenize etmez
  - O(log n) arama: 1M+ chunk için ölçeklenebilir
  - FTS5 yerleşik BM25 (rank() fonksiyonu)
  - WAL mode: eşzamanlı okumalar için güvenli

Tokenizer: unicode61 tokenchars '_'
  spi_mosi → tek token "spi_mosi" (kesin eşleşme için)
  Pre-expansion ile "spi" ve "mosi" de eklenir (kısmi eşleşme için)
  → rank-bm25 davranışını tam olarak yansıtır.

Kullanım:
    idx = FTS5Index("db/fts5_source.db")
    idx.add("chunk_id", content, project="prj_a", file_type="xdc")
    results = idx.search("CLK100MHZ PACKAGE_PIN", n_results=5, project="prj_a")
"""

from __future__ import annotations

import re
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Tokenizer — rank-bm25 ile birebir aynı mantık
# ─────────────────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r'[a-zA-Z0-9_]+')


def _tokenize(text: str) -> str:
    """
    text → FTS5 index için token string.

    - [a-zA-Z0-9_]+ token'ları ayır, küçük harfe çevir
    - Underscore içerenleri parçalara da böl:
        spi_mosi → spi_mosi spi mosi  (3 token)
        CLK100MHZ → clk100mhz (1 token)
    - Tekrar eden token'ları kaldır (index boyutu için)

    FTS5 unicode61 tokenizer + tokenchars='_' ile birlikte kullanılır:
    spi_mosi stored token → FTS5 görür "spi_mosi" (tek token, bölünmez).
    """
    full = _TOKEN_RE.findall(text.lower())
    tokens: List[str] = []
    seen: set = set()
    for t in full:
        if t not in seen:
            tokens.append(t)
            seen.add(t)
        if '_' in t:
            for part in t.split('_'):
                if part and part not in seen:
                    tokens.append(part)
                    seen.add(part)
    return ' '.join(tokens)


def _build_fts_query(query: str) -> Optional[str]:
    """
    query → FTS5 MATCH ifadesi.

    - Pre-expand: spi_mosi → spi_mosi, spi, mosi
    - OR ile birleştir: daha geniş geri çağırma, BM25 sıralama doğruluğu sağlar
    - Her token tırnak içinde → FTS5 operatör yorumlamasını önler
    - Boş sonuç → None
    """
    raw = _TOKEN_RE.findall(query.lower())
    expanded: List[str] = []
    seen: set = set()
    for t in raw:
        if t not in seen:
            expanded.append(t)
            seen.add(t)
        if '_' in t:
            for part in t.split('_'):
                if part and part not in seen:
                    expanded.append(part)
                    seen.add(part)
    if not expanded:
        return None
    return ' OR '.join(f'"{t}"' for t in expanded)


# ─────────────────────────────────────────────────────────────────────────────
# FTS5Index
# ─────────────────────────────────────────────────────────────────────────────

class FTS5Index:
    """
    SQLite FTS5 persistent keyword index.
    SourceChunkStore ve DocStore için rank-bm25 yerine kullanılır.

    Schema (iki tablo):
        fts(tokens, chunk_id UNINDEXED, content UNINDEXED,
            project UNINDEXED, file_type UNINDEXED, doc_id UNINDEXED)
        meta(chunk_id PK, file_path, start_line, end_line, chunk_label,
             related_node_ids, doc_title, section, page_num)

    fts.tokens → FTS5 BM25 indexed (pre-tokenized)
    Diğer fts kolonu → UNINDEXED (WHERE filtresi için)
    meta → extended metadata (JOIN ile çekrilir)
    """

    def __init__(self, db_path: str):
        self._db_path = str(Path(db_path).resolve())
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        # WAL: eşzamanlı okuma/yazma için (app_v2.py multi-thread)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-32000")  # 32MB cache
        self._init_schema()

    def _init_schema(self):
        """Tablolar yoksa oluştur."""
        self._conn.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
                tokens,
                chunk_id   UNINDEXED,
                content    UNINDEXED,
                project    UNINDEXED,
                file_type  UNINDEXED,
                doc_id     UNINDEXED,
                tokenize   = 'unicode61 tokenchars ''_'''
            );
            CREATE TABLE IF NOT EXISTS meta (
                chunk_id         TEXT PRIMARY KEY,
                file_path        TEXT DEFAULT '',
                start_line       INTEGER DEFAULT 0,
                end_line         INTEGER DEFAULT 0,
                chunk_label      TEXT DEFAULT '',
                related_node_ids TEXT DEFAULT '[]',
                doc_title        TEXT DEFAULT '',
                section          TEXT DEFAULT '',
                page_num         INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS signals (
                keyword TEXT NOT NULL,
                project TEXT NOT NULL,
                source  TEXT DEFAULT '',
                PRIMARY KEY (keyword, project)
            );
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Insert / Update
    # ------------------------------------------------------------------

    def add(
        self,
        chunk_id: str,
        content: str,
        *,
        project: str = "",
        file_type: str = "",
        doc_id: str = "",
        file_path: str = "",
        start_line: int = 0,
        end_line: int = 0,
        chunk_label: str = "",
        related_node_ids: Optional[List[str]] = None,
        doc_title: str = "",
        section: str = "",
        page_num: int = 0,
    ):
        """Tek chunk ekle veya güncelle (upsert)."""
        # FTS5 UPDATE desteklemez → DELETE + INSERT
        self._conn.execute("DELETE FROM fts WHERE chunk_id = ?", (chunk_id,))
        tokens = _tokenize(content)
        self._conn.execute(
            "INSERT INTO fts(tokens, chunk_id, content, project, file_type, doc_id)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (tokens, chunk_id, content, project, file_type, doc_id),
        )
        self._conn.execute(
            """INSERT OR REPLACE INTO meta
               (chunk_id, file_path, start_line, end_line, chunk_label,
                related_node_ids, doc_title, section, page_num)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chunk_id, file_path, start_line, end_line, chunk_label,
                json.dumps(related_node_ids or []),
                doc_title, section, page_num,
            ),
        )
        self._conn.commit()

    def add_batch(self, items: List[Dict[str, Any]]):
        """
        Toplu ekleme — her item bir chunk.
        Var olan chunk_id'ler silinip yeniden eklenir (upsert).

        Beklenen item anahtarları:
          chunk_id, content, project, file_type, doc_id,
          file_path, start_line, end_line, chunk_label,
          related_node_ids, doc_title, section, page_num
        """
        if not items:
            return

        ids = [it["chunk_id"] for it in items]

        # Var olanları sil (900'lük batch'ler — SQLite parametre limiti)
        for i in range(0, len(ids), 900):
            batch = ids[i:i + 900]
            ph = ','.join('?' * len(batch))
            self._conn.execute(f"DELETE FROM fts WHERE chunk_id IN ({ph})", batch)
            self._conn.execute(f"DELETE FROM meta WHERE chunk_id IN ({ph})", batch)

        fts_rows = []
        meta_rows = []
        for it in items:
            cid = it["chunk_id"]
            content = it.get("content", "")
            tokens = _tokenize(content)
            fts_rows.append((
                tokens, cid, content,
                it.get("project", ""), it.get("file_type", ""), it.get("doc_id", ""),
            ))
            meta_rows.append((
                cid,
                it.get("file_path", ""),
                it.get("start_line", 0),
                it.get("end_line", 0),
                it.get("chunk_label", ""),
                json.dumps(it.get("related_node_ids") or []),
                it.get("doc_title", ""),
                it.get("section", ""),
                it.get("page_num", 0),
            ))

        self._conn.executemany(
            "INSERT INTO fts(tokens, chunk_id, content, project, file_type, doc_id)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            fts_rows,
        )
        self._conn.executemany(
            """INSERT OR REPLACE INTO meta
               (chunk_id, file_path, start_line, end_line, chunk_label,
                related_node_ids, doc_title, section, page_num)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            meta_rows,
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        n_results: int = 10,
        *,
        project: Optional[str] = None,
        file_type: Optional[str] = None,
        doc_id_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        FTS5 BM25 arama.

        Returns: [{"chunk_id", "content", "project", "file_type", "doc_id",
                   "file_path", "start_line", "end_line", "chunk_label",
                   "related_node_ids", "doc_title", "section", "page_num",
                   "bm25_score"}]

        bm25_score: pozitif, büyük = daha iyi eşleşme.
        """
        fts_query = _build_fts_query(query)
        if not fts_query:
            return []

        where_parts = ["fts MATCH ?"]
        params: List[Any] = [fts_query]

        if project:
            where_parts.append("project = ?")
            params.append(project)
        if file_type:
            where_parts.append("file_type = ?")
            params.append(file_type)
        if doc_id_filter:
            where_parts.append("doc_id = ?")
            params.append(doc_id_filter)

        where_clause = " AND ".join(where_parts)
        params.append(n_results)

        sql = f"""
            SELECT f.chunk_id, f.content, f.project, f.file_type, f.doc_id,
                   (-rank) AS bm25_score,
                   m.file_path, m.start_line, m.end_line, m.chunk_label,
                   m.related_node_ids, m.doc_title, m.section, m.page_num
            FROM fts f
            LEFT JOIN meta m ON f.chunk_id = m.chunk_id
            WHERE {where_clause}
            ORDER BY rank
            LIMIT ?
        """
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # FTS5 syntax hatası (boş MATCH vb.) → boş döndür
            return []

        results = []
        for row in rows:
            (cid, content, prj, ft, did, score,
             fp, sl, el, cl, rni, dt, sec, pn) = row
            try:
                related = json.loads(rni) if rni else []
            except Exception:
                related = []
            results.append({
                "chunk_id":         cid,
                "content":          content or "",
                "project":          prj or "",
                "file_type":        ft or "",
                "doc_id":           did or "",
                "bm25_score":       round(float(score), 4) if score else 0.0,
                "file_path":        fp or "",
                "start_line":       sl or 0,
                "end_line":         el or 0,
                "chunk_label":      cl or "",
                "related_node_ids": related,
                "doc_title":        dt or "",
                "section":          sec or "",
                "page_num":         pn or 0,
            })
        return results

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, chunk_id: str):
        """Tek chunk sil."""
        self._conn.execute("DELETE FROM fts WHERE chunk_id = ?", (chunk_id,))
        self._conn.execute("DELETE FROM meta WHERE chunk_id = ?", (chunk_id,))
        self._conn.commit()

    def delete_by_ids(self, chunk_ids: List[str]):
        """Birden fazla chunk_id sil."""
        if not chunk_ids:
            return
        for i in range(0, len(chunk_ids), 900):
            batch = chunk_ids[i:i + 900]
            ph = ','.join('?' * len(batch))
            self._conn.execute(f"DELETE FROM fts WHERE chunk_id IN ({ph})", batch)
            self._conn.execute(f"DELETE FROM meta WHERE chunk_id IN ({ph})", batch)
        self._conn.commit()

    def delete_by_project(self, project: str):
        """Bir projenin tüm chunk'larını sil."""
        # Önce chunk_id'leri al (meta join için)
        rows = self._conn.execute(
            "SELECT chunk_id FROM fts WHERE project = ?", (project,)
        ).fetchall()
        ids = [r[0] for r in rows]
        if ids:
            self.delete_by_ids(ids)

    def delete_by_doc_id(self, doc_id: str):
        """Bir doc_id'nin tüm chunk'larını sil."""
        rows = self._conn.execute(
            "SELECT chunk_id FROM fts WHERE doc_id = ?", (doc_id,)
        ).fetchall()
        ids = [r[0] for r in rows]
        if ids:
            self.delete_by_ids(ids)

    def delete_by_file_path(self, file_path: str):
        """Bir dosyaya ait chunk'ları sil (meta.file_path üzerinden)."""
        rows = self._conn.execute(
            "SELECT chunk_id FROM meta WHERE file_path = ?", (file_path,)
        ).fetchall()
        ids = [r[0] for r in rows]
        if ids:
            self.delete_by_ids(ids)

    def reset(self):
        """Tüm index'i sil ve sıfırla."""
        self._conn.executescript("""
            DELETE FROM fts;
            DELETE FROM meta;
        """)
        self._conn.commit()
        # FTS5 fragmentasyonunu temizle
        try:
            self._conn.execute("INSERT INTO fts(fts) VALUES('optimize')")
            self._conn.commit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Toplam chunk sayısı."""
        try:
            row = self._conn.execute("SELECT COUNT(*) FROM fts").fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def has(self, chunk_id: str) -> bool:
        """chunk_id FTS5 index'te var mı?"""
        row = self._conn.execute(
            "SELECT 1 FROM meta WHERE chunk_id = ? LIMIT 1", (chunk_id,)
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Signals — proje tanımlayıcı keyword tablosu
    # ------------------------------------------------------------------

    def add_signals(self, items: List[Dict[str, str]]):
        """
        Proje sinyal listesini kaydet.
        Her item: {"keyword": str, "project": str, "source": str}
        Mevcut kayıtlar güncellenir (UPSERT).
        """
        if not items:
            return
        rows = [(it["keyword"].lower(), it["project"], it.get("source", ""))
                for it in items if it.get("keyword") and it.get("project")]
        self._conn.executemany(
            "INSERT OR REPLACE INTO signals (keyword, project, source) VALUES (?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def get_unique_signals(self) -> List[tuple]:
        """
        Yalnızca TEK projede geçen keyword'leri döndür.
        → (keyword, project) çiftleri listesi.

        Birden fazla projede geçen keyword'ler routing için belirsiz → dahil edilmez.
        """
        rows = self._conn.execute("""
            SELECT keyword, project
            FROM signals
            GROUP BY keyword
            HAVING COUNT(DISTINCT project) = 1
        """).fetchall()
        return [(r[0], r[1]) for r in rows]

    def get_all_signals(self) -> List[tuple]:
        """Tüm sinyalleri döndür: (keyword, project, source)."""
        rows = self._conn.execute(
            "SELECT keyword, project, source FROM signals ORDER BY project, keyword"
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    def delete_project_signals(self, project: str):
        """Bir projenin tüm sinyallerini sil (re-index öncesi temizlik)."""
        self._conn.execute("DELETE FROM signals WHERE project = ?", (project,))
        self._conn.commit()

    def delete_generic_signals(self, stoplist: set) -> int:
        """
        Stoplist'teki keyword'lere sahip sinyalleri sil.
        Mevcut DB'deki eski/kötü sinyalleri temizlemek için kullanılır.
        Döndürür: silinen satır sayısı.
        """
        if not stoplist:
            return 0
        lower_stop = [kw.lower() for kw in stoplist]
        ph = ','.join('?' * len(lower_stop))
        cur = self._conn.execute(
            f"DELETE FROM signals WHERE keyword IN ({ph})", lower_stop
        )
        self._conn.commit()
        return cur.rowcount

    def signal_count(self) -> int:
        """Toplam kayıtlı sinyal sayısı."""
        row = self._conn.execute("SELECT COUNT(*) FROM signals").fetchone()
        return row[0] if row else 0

    def close(self):
        """SQLite connection'ı kapat."""
        try:
            self._conn.close()
        except Exception:
            pass
