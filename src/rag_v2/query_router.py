"""
Query Router — FPGA RAG v2
Architecture ref: fpga_rag_architecture_v2.md §6

5 Query Types:
  What     → tüm store paralel (genel bilgi)
  How      → COMPONENT + PATTERN nodes
  Why      → DECISION nodes + MOTIVATED_BY edges
  Trace    → IMPLEMENTS / VERIFIED_BY traversal (traceability zinciri)
  CrossRef → ANALOGOUS_TO / CONTRADICTS edges (karşılaştırma)

4-Store parallel query (v2.1):
  Vector Store       → semantic similarity (VectorStoreV2, graph node metadata)
  Graph Store        → structural traversal (GraphStore)
  Source Chunk Store → kaynak dosya içeriği (SourceChunkStore) [YENİ]
  Req Tree           → DECOMPOSES_TO BFS (GraphStore.get_req_tree)
"""

from __future__ import annotations

import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJ_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJ_ROOT / "src"))

from rag_v2.graph_store import GraphStore
from rag_v2.vector_store_v2 import VectorStoreV2

# SourceChunkStore isteğe bağlı — yoksa gracefully degrade
try:
    from rag_v2.source_chunk_store import SourceChunkStore as _SCS
    _HAS_SOURCE_STORE = True
except ImportError:
    _HAS_SOURCE_STORE = False

# DocStore isteğe bağlı — yoksa gracefully degrade
try:
    from rag_v2.doc_store import DocStore as _DS
    _HAS_DOC_STORE = True
except ImportError:
    _HAS_DOC_STORE = False

# ─────────────────────────────────────────────────────────────────────────────
# IP → Xilinx Döküman eşleme tablosu
# HOW sorgularında yapısal retrieval için: semantic benzerlik kör noktasını kapatır.
# Proje COMPONENT node'larındaki IP isimleri bu tablo üzerinden doc_id'ye çevrilir.
# Yeni IP eklendiğinde buraya satır ekle — başka hiçbir şey değişmez.
# ─────────────────────────────────────────────────────────────────────────────
_IP_TO_DOCS: Dict[str, List[str]] = {
    # Saat & Reset
    "clk_wiz":               ["pg065", "ug572"],
    "proc_sys_reset":        ["pg164"],
    # MicroBlaze
    "microblaze":            ["ug984", "ug898"],
    "microblaze_mcs":        ["pg048", "ug984"],
    "mdm":                   ["pg115", "pg062"],
    "lmb_bram_if_cntlr":     ["ug984"],
    "lmb_v10":               ["ug984"],
    # AXI Interconnect
    "axi_interconnect":      ["pg059"],
    "smartconnect":          ["pg247"],
    "axi_register_slice":    ["pg373"],
    # AXI Periferaller
    "axi_gpio":              ["pg144"],
    "axi_uartlite":          ["pg142"],
    "axi_iic":               ["pg090"],
    "axi_spi":               ["pg153"],
    "axi_timer":             ["pg079"],
    "axi_intc":              ["pg099"],
    "axi_bram_ctrl":         ["pg078"],
    # AXI DMA & Streaming
    "axi_dma":               ["pg021"],
    "axi_vdma":              ["pg020"],
    "axis_subset_converter": ["pg085"],
    "axis_data_fifo":        ["pg085"],
    # Bellek
    "mig_7series":           ["ug586"],
    "blk_mem_gen":           ["pg058"],
    "fifo_generator":        ["pg057"],
    # PCIe
    "axi_pcie":              ["pg054"],
    "xdma":                  ["pg195"],
    # GTX / Aurora / Ethernet
    "aurora_8b10b":          ["pg046"],
    "aurora_64b66b":         ["pg074"],
    "gig_ethernet_pcs_pma":  ["pg047"],
    "tri_mode_ethernet_mac": ["pg051"],
    # Video
    "v_tc":                  ["pg016"],
    "v_axi4s_vid_out":       ["pg044"],
    "v_vid_in_axi4s":        ["pg043"],
    "rgb2dvi":               ["pg160"],
    "dvi2rgb":               ["pg163"],
    # Debug
    "xadc_wiz":              ["pg091", "ug480"],
    "ila":                   ["pg172"],
    "vio":                   ["pg159"],
    # Zynq PS
    "processing_system7":    ["ug585", "pg082", "ug898"],
}


# ---------------------------------------------------------------------------
# Query Type
# ---------------------------------------------------------------------------

class QueryType(str, Enum):
    WHAT = "What"
    HOW = "How"
    WHY = "Why"
    TRACE = "Trace"
    CROSSREF = "CrossRef"
    ENUMERATE = "Enumerate"


# ---------------------------------------------------------------------------
# Query Result
# ---------------------------------------------------------------------------

class QueryResult:
    """Container for 5-store federated query results."""

    def __init__(
        self,
        query: str,
        query_type: QueryType,
        vector_hits: List[Dict[str, Any]] = None,
        graph_nodes: List[Dict[str, Any]] = None,
        graph_edges: List[Dict[str, Any]] = None,
        req_tree: List[Dict[str, Any]] = None,
        source_chunks: List[Dict[str, Any]] = None,   # 4. store: proje kaynak kodu
        doc_chunks: List[Dict[str, Any]] = None,       # 5. store: Xilinx UG dökümanları
        stale_ids: set = None,
    ):
        self.query = query
        self.query_type = query_type
        self.vector_hits = vector_hits or []
        self.graph_nodes = graph_nodes or []
        self.graph_edges = graph_edges or []
        self.req_tree = req_tree or []
        self.source_chunks = source_chunks or []
        self.doc_chunks = doc_chunks or []             # 5. store
        self.stale_ids = stale_ids or set()

    def all_nodes(self) -> List[Dict[str, Any]]:
        """Merged, deduplicated nodes from all stores."""
        seen = set()
        result = []
        for node in self.graph_nodes + self.req_tree:
            nid = node.get("node_id", "")
            if nid and nid not in seen:
                seen.add(nid)
                result.append(node)
        # Add vector hits not already in graph results
        for hit in self.vector_hits:
            nid = hit.get("node_id", "")
            if nid and nid not in seen:
                seen.add(nid)
                # Retrieve full node attrs from graph
                result.append(hit)
        return result

    def __repr__(self) -> str:
        return (f"QueryResult(type={self.query_type}, "
                f"vector={len(self.vector_hits)}, "
                f"graph={len(self.graph_nodes)}, "
                f"edges={len(self.graph_edges)}, "
                f"req_tree={len(self.req_tree)}, "
                f"source_chunks={len(self.source_chunks)}, "
                f"doc_chunks={len(self.doc_chunks)})")


# ---------------------------------------------------------------------------
# Keyword classifier
# ---------------------------------------------------------------------------

# Pattern: (regex, QueryType) — first match wins
_CLASSIFY_PATTERNS = [
    # HOW-Workflow (prosedür adımları) — TRACE'den ÖNCE değerlendirilmeli
    # "hangi adımları izlemeliyim", "hangi sırayı takip et", "adım adım" → daima HOW
    # Kural: adım/sıra/workflow/aşama vocabulary'si = prosedürel sorgu = HOW
    # Sinyal izleme (zincir, bileşen) ile karışmaması için önce yakalanır.
    (r'\b(adım\s+adım|adımlar\w*|hangi\s+adım\w*|hangi\s+sıra\w*|sırasıyla'
     r'|workflow\w*|prosedür\w*|aşamalar\w*|aşamaları\w*'
     r'|oluşturma\s+süreç\w*|kurulum\s+süreç\w*'
     r'|step.by.step|which\s+steps?|what\s+steps?)\b', QueryType.HOW),
    # Trace — traceability / izleme
    # Turkish morphology: izle→izleyin, zincir→zincirini, karşıl→karşıladığını
    # Use \w+ suffix to handle Turkish agglutinative suffixes
    (r'(?:\btrace(?:ability)?\b|\bizle\w+|\bzincir\w+|\bimplement\w+|\bhangi\s+bileşen\w*|\bgerçek\b|\bkarşıl(?:ay|ad|am)\w*)', QueryType.TRACE),
    # Why — rationale / decision
    (r'\b(neden|why|karar|rationale|gerekçe|motivated|sebep|nedeni|nasıl karar)\b', QueryType.WHY),
    # CrossRef — comparison / contradiction / both-projects queries
    # Not: \b yerine prefix match — Türkçe ekler için (fark→farkı, benzer→benzerlik)
    # "arasındaki" tek başına CROSSREF tetiklememeli — yalnızca karşılaştırma bağlamında
    # "DDR_BASE_ADDR ile arasındaki offset" gibi ifadeler CROSSREF değil HOW/WHAT
    # "her iki proje" / "project a ve b" / "iki proje için" → CROSSREF (no project filter)
    (r'(karşılaştır|versus|\bvs\b|analogous|contradicts|çelişki|iki proje|karşılaştırma'
     r'|her iki proje|her iki\s+(?:proje|sistem|tasarım)'
     r'|project.a.ve.project.b|project\s+a\s+ve\s+b|proje.a.ve.b|a\s+ve\s+b\s+(?:projesi|için|proje)'
     r'|mevcut projeler\w*|sistemdeki projeler\w*'
     r'|projelerimiz\w*|projeleriniz\w*|tüm projeler\w*|bu projeler\w*'
     r'|(?:iki\s+\w+\s+arasındaki)'
     r'|\barasındaki(?:\s+\w+){0,3}\s+(?:fark|benzerlik|farklılık|ilişki|uyum|çelişki|karşılaştırma)'
     r'|(?:fark\w*|benzer\w*|farklı\w*|alternatif\w*)\s+\w{0,10}\s+arasında)', QueryType.CROSSREF),
    # Enumerate — "list all" / "tüm X" sorgular: top-K değil tam liste gerekir
    # IP blokları, bileşenler, peripheral listesi, "hangi X'ler var" sorguları
    (r'\b(tüm\s+ip\w*|ip\s+list\w*|listele\w*\s+ip\w*|ip\w*\s+listele\w*'
     r'|hangi\s+ip\w*|kaç\s+ip\w*|all\s+ip\w*|list\s+all\s+ip'
     r'|tüm\s+bileşen\w*|bileşen\s+list\w*|component\s+list|list\s+all\s+component'
     r'|ip\s+blok\w*|ip\s+block\w*|kullanılan\s+ip\w*|ip\w*\s+kullanıl\w*'
     r'|hangi\s+modul\w*|tüm\s+modul\w*|modul\s+list\w*'
     r'|hangi\s+peripheral\w*|tüm\s+peripheral\w*|peripheral\s+list\w*)\b',
     QueryType.ENUMERATE),
    # How — implementation details
    (r'\b(nasıl|how|çalış|implement|konfigür|ayarla|kullan|bağlan|port|sinyal|clock)\b', QueryType.HOW),
    # What — fallback
    (r'.*', QueryType.WHAT),
]


def classify_query(question: str) -> QueryType:
    """
    Rule-based query type classifier.
    Keyword match → returns QueryType.
    """
    q_lower = question.lower()
    for pattern, qtype in _CLASSIFY_PATTERNS:
        if re.search(pattern, q_lower, re.IGNORECASE):
            return qtype
    return QueryType.WHAT




# ---------------------------------------------------------------------------
# Query Router
# ---------------------------------------------------------------------------

class QueryRouter:
    """
    Routes queries to the appropriate stores based on query type.
    Architecture §6: 4-store parallel query (v2.1).

    4 stores:
      1. VectorStoreV2      — graph node metadata semantic search
      2. GraphStore         — structural traversal
      3. SourceChunkStore   — kaynak dosya içeriği semantic search [YENİ]
      4. Req Tree           — DECOMPOSES_TO BFS
    """

    def __init__(
        self,
        graph_store: GraphStore,
        vector_store: VectorStoreV2,
        source_chunk_store=None,          # SourceChunkStore | None
        doc_store=None,                   # DocStore | None — Xilinx UG dökümanları
        n_vector_results: int = 0,        # 0 → auto-scale ile belirlenir
        n_graph_results: int = 10,
        n_source_results: int = 0,        # 0 → auto-scale ile belirlenir
        n_doc_results: int = 4,           # UG döküman sonuçları (sabit — çok fazla gürültü ekler)
    ):
        self.graph = graph_store
        self.vector = vector_store
        self.source_store = source_chunk_store   # None → graceful degradation
        self.doc_store = doc_store               # None → graceful degradation
        self.n_doc = n_doc_results
        self.n_graph = n_graph_results
        self._stale_ids = graph_store.get_stale_node_ids()

        # ── Adaptif K değerleri: proje sayısına göre otomatik ölçekle ──────────
        # 100+ proje eklendiğinde, daha geniş candidate pool gerekir.
        # Nihai LLM context max_nodes=10 + max_chars=8000 ile sınırlıdır,
        # bu yüzden büyük K sadece retrieval kalitesini artırır, token maliyeti sabit.
        all_nodes = graph_store.get_all_nodes()
        project_count = max(1, sum(
            1 for n in all_nodes
            if n.get("node_type") == "PROJECT"
        ))
        self.n_vector = n_vector_results if n_vector_results > 0 else max(5, min(project_count + 4, 20))
        self.n_source = n_source_results if n_source_results > 0 else max(6, min(project_count + 2, 24))

        # ── Exact-match proje ID listesi ─────────────────────────────────────
        # Runtime'da graph PROJECT node'larından türetilir.
        # _exact_project_match() ve classify() için init'te bir kez hesaplanır.
        self._project_ids: List[str] = [
            n["node_id"] for n in all_nodes
            if n.get("node_type") == "PROJECT" and n.get("node_id")
        ]

        # ── Paylaşılan board adları — routing sinyali olamaz ──────────────────
        # Yapısal kural: aynı board'u kullanan 2+ proje varsa, board adı discriminator değil.
        # "Nexys Video" → 8+ proje: routing için kullanılamaz.
        # "Zybo Z7-20 Pcam" → 1 proje: kullanılabilir.
        # Bu set init'te bir kez hesaplanır; yeni proje eklenince otomatik güncellenir.
        self._shared_board_names: frozenset = self._build_shared_board_names()

        # ── Dinamik proje sinyal tablosu ──────────────────────────────────────
        # Sınıf değişkeni _TEXT_PROJECT_SIGNALS statik (hardcoded) girişler içerir.
        # Grafta yeni PROJECT node'ları eklendiğinde otomatik olarak kapsanır.
        # Yeni projeler için gereken tek şey GraphStore'a node eklemektir —
        # index_source_files.py'ye veya query_router.py'ye dokunmak gerekmez.
        self._TEXT_PROJECT_SIGNALS = self._build_dynamic_signals()

    # CrossRef dominance threshold: tek proje bu oranın üstündeyse CrossRef tetiklenmez.
    # Kısa/genel keyword'ler (gpio, dma, uart) az ağırlık alır → spesifik proje ID'si baskın çıkar.
    # Sistem bazlı: retrieval sinyal gücüne dayalı, soru parsing'ine değil.
    _CROSSREF_DOMINANCE = 0.70

    def classify(self, question: str) -> QueryType:
        qt = classify_query(question)
        q_lower = question.lower()

        # ── Exact project ID match: soruda kaç farklı project_id geçiyor? ──────
        # count == 1 → tek proje sorusu: CrossRef yanlış tetiklendiyse baskıla.
        # count >= 2 → gerçek karşılaştırma: CrossRef doğru kalır.
        # Sistem bazlı: project_ids graph'tan türetilir, hardcoded keyword yok.
        # Not: _exact_project_match() longest-match döndürür (tek proje).
        # classify() için TÜM eşleşmeleri saymamız gerekiyor — ayrı döngü.
        exact_matches: set = set()
        for pid in self._project_ids:
            pid_lower = pid.lower()
            if (pid_lower in q_lower
                    or pid_lower.replace("_", " ") in q_lower
                    or pid_lower.replace("_", "-") in q_lower):
                exact_matches.add(pid)

        if len(exact_matches) == 1 and qt == QueryType.CROSSREF:
            # Tek proje → CrossRef false positive → WHAT'a düşür
            qt = QueryType.WHAT

        # ── Metin sinyal bazlı CrossRef (exact match yoksa) ──────────────────
        # İki proje keyword'ü aynı soruda ama biri baskın değilse CrossRef zorla.
        # exact_matches varsa bu blok atlanır — exact match daha güvenilir sinyal.
        if qt != QueryType.CROSSREF and not exact_matches:
            project_weight: Dict[str, int] = {}
            for keyword, project in self._TEXT_PROJECT_SIGNALS:
                if keyword in q_lower:
                    project_weight[project] = project_weight.get(project, 0) + len(keyword)
            if len(project_weight) >= 2:
                total = sum(project_weight.values())
                top   = max(project_weight.values())
                if top / total < self._CROSSREF_DOMINANCE:
                    qt = QueryType.CROSSREF

        return qt

    # Doc sorgu keyword'leri — proje sinyali olmasa bile doc_store'a bak
    _DOC_QUERY_RE = re.compile(
        r'\b(vivado|vitis|synthesis|sentez(?:leme)?|implementation|implem'
        r'|timing\s*constraint|timing\s*closure|set_false_path|set_multicycle'
        r'|set_input_delay|set_output_delay|create_clock|get_clocks|get_ports'
        r'|set_dont_touch|keep_hierarchy|xdc\s+syntax|xdc\s+komutu'
        r'|tcl\s+komutu|tcl\s+script|ug\d{3,4}|user\s+guide'
        r'|microblaze\s+parameter|pcw_\w+|fsbl|xsdb|bsp\s+setting'
        r'|synthesize|elaborate|opt_design|place_design|route_design'
        r'|direkt\w*|pragma|attribute\s+\w+|ip\s+catalog|ip\s+packager'
        r'|clock\s+domain\s+crossing|cdc\s+violation|timing\s+violation'
        r'|setup\s+time|hold\s+time|slack|wns|tns)\b',
        re.IGNORECASE,
    )

    def _exact_project_match(self, question: str) -> Optional[str]:
        """
        Soruda herhangi bir project_id'nin tam veya boşluklu formu geçiyorsa döndür.
        En uzun eşleşme kazanır — benzer isimli projelerde doğru proje seçilir.
        (Örnek: "arty_s7_25_base_rt" hem "arty s7" hem "arty_s7_25_base_rt" formuna uyar
         → uzun olanı kazanır, kısa "arty s7" başka projeye çekmez.)

        Sistem bazlı: project_ids graph'tan __init__'te derlenir, hardcoded kelime yok.
        Yeni proje eklendikçe otomatik kapsar.
        """
        q = question.lower()
        best: Optional[str] = None
        best_len: int = 0
        for pid in self._project_ids:
            pid_lower = pid.lower()
            # Üç form: altçizgili (fpga_vbs), boşluklu (fpga vbs), tireli (fpga-vbs)
            for form in (pid_lower,
                         pid_lower.replace("_", " "),
                         pid_lower.replace("_", "-")):
                # min 4 karakter — kısa kısaltmalar (e.g. "i2c") genel kelime olabilir
                if len(form) >= 4 and form in q and len(form) > best_len:
                    best = pid
                    best_len = len(form)
        return best

    def _search_doc_store(self, question: str, n_results: int = 0) -> List[Dict]:
        """
        DocStore araması — genel Vivado/Vitis soruları için.
        HOW/WHAT/ENUMERATE tiplerinde ve doc keyword'leri varsa çalışır.
        Proje-spesifik context'i bozmamak için az sayıda (n_doc) sonuç döner.
        n_results > 0 ise self.n_doc'u override eder (kavramsal sorgular için boost).
        """
        if not self.doc_store:
            return []
        n = n_results if n_results > 0 else self.n_doc
        try:
            return self.doc_store.search(question, n_results=n)
        except Exception:
            return []

    def _get_ip_doc_chunks(
        self, project: Optional[str], question: str
    ) -> List[Dict]:
        """
        HOW + proje sinyali durumunda yapısal IP→Doc retrieval.
        Graph COMPONENT node'ları yerine source chunk store'daki TCL içeriğinden
        query-time parse ile IP isimlerini çıkarır → _IP_TO_DOCS → DocStore.

        Soru-bağımsız: her proje için TCL chunk'ları zaten indeksli.
        IP-bağımsız: _IP_TO_DOCS'a yeni satır eklemek yeterli.
        """
        if not self.doc_store or not project or not self.source_store:
            return []

        # 1. Projenin TCL chunk'larını çek → create_bd_cell -vlnv regex ile IP isimlerini çıkar
        ip_names: set = set()
        try:
            col = self.source_store._get_collection()
            data = col.get(
                where={"$and": [{"project": {"$eq": project}}, {"file_type": {"$eq": "tcl"}}]},
                include=["documents"],
            )
            _VLNV_RE = re.compile(
                r'create_bd_cell\s+-type\s+ip\s+.*?-vlnv\s+\S+:(\w+):\S+',
                re.IGNORECASE,
            )
            for doc in data.get("documents", []):
                for m in _VLNV_RE.finditer(doc or ""):
                    ip_names.add(m.group(1).lower())
        except Exception:
            return []

        if not ip_names:
            return []

        # 2. _IP_TO_DOCS üzerinden benzersiz doc_id listesi oluştur
        doc_ids: List[str] = []
        seen_doc_ids: set = set()
        for ip in sorted(ip_names):
            for doc_id in _IP_TO_DOCS.get(ip, []):
                if doc_id not in seen_doc_ids:
                    doc_ids.append(doc_id)
                    seen_doc_ids.add(doc_id)

        if not doc_ids:
            return []

        # 3. DocStore'da filtrelenmiş semantic arama
        try:
            return self.doc_store.search_in_docs(question, doc_ids, n_per_doc=2)
        except Exception:
            return []

    def route(self, question: str, query_type: Optional[QueryType] = None) -> QueryResult:
        """
        Main entry point. Returns QueryResult with results from all relevant stores.
        """
        if query_type is None:
            query_type = self.classify(question)

        # ── Genel Sorgu Yolu ────────────────────────────────────────────────────
        # Tetikleyici: proje sinyali yokluğu (yapısal) + proje bağlamı gerektiren route.
        #
        # TRACE ve CROSSREF proje bağlamı varsayar: graph traversal, cross-project edge.
        # Proje sinyali olmadan bu route'lara girmek graph gürültüsüne yol açar —
        # LLM ilgisiz REQUIREMENT/COMPONENT node'larını bağlam olarak kullanır.
        #
        # Çözüm: proje sinyali yok + TRACE/CROSSREF → WHAT'a override.
        # WHAT route tüm store'ları paralel sorgular, DocStore öne çıkar.
        # Sonsuz soru uzayı prensibi: keyword değil, yapısal özellik (sinyal yokluğu).
        _has_project_signal = (
            self._exact_project_match(question) is not None
            or any(kw in question.lower() for kw, _ in self._TEXT_PROJECT_SIGNALS)
        )
        _is_general_query = (
            not _has_project_signal
            and query_type in (QueryType.TRACE, QueryType.CROSSREF)
            and not self._ALL_PROJECTS_RE.search(question.lower())
        )
        if _is_general_query:
            query_type = QueryType.WHAT

        if query_type == QueryType.WHAT:
            result = self._route_what(question)
        elif query_type == QueryType.HOW:
            result = self._route_how(question)
        elif query_type == QueryType.WHY:
            result = self._route_why(question)
        elif query_type == QueryType.TRACE:
            result = self._route_trace(question)
        elif query_type == QueryType.CROSSREF:
            result = self._route_crossref(question)
        elif query_type == QueryType.ENUMERATE:
            result = self._route_enumerate(question)
        else:
            result = self._route_what(question)

        # ── DocStore boost ──────────────────────────────────────────────────────
        # Katmanlar (proje sinyali varlığına göre, yapısal karar):
        #
        # 1. _is_general_query (TRACE/CROSSREF, proje sinyali yok):
        #    DocStore birincil → 3x boost, source_chunks[:2] (graph gürültüsü kesilir).
        #
        # 2. HOW, proje sinyali yok:
        #    DocStore 3x boost, source_chunks KORUNUR (TCL örnekleri değerli).
        #    Route tipi değişmez — HOW meta chunk'ları hâlâ aranır.
        #
        # 3. WHAT/WHY, proje sinyali yok (kavramsal):
        #    DocStore 2x boost.
        #
        # 4. Proje sinyali var (proje-spesifik): n_doc sabit (gürültü önlenir).
        #
        # Sistem bazlı: proje sinyali varlığı sorgudan değil, sinyal tablosundan kontrol edilir.
        # Yeni proje/doküman eklendiğinde otomatik çalışır — keyword gerekmez.
        _is_general_how = (
            not _has_project_signal
            and result.query_type == QueryType.HOW
        )
        if _is_general_query:
            n_doc_eff = max(self.n_doc * 3, 12)
            result.doc_chunks = self._search_doc_store(question, n_results=n_doc_eff)
            result.source_chunks = result.source_chunks[:2]
        elif _is_general_how:
            n_doc_eff = max(self.n_doc * 3, 12)
            result.doc_chunks = self._search_doc_store(question, n_results=n_doc_eff)
            # source_chunks korunur — gerçek proje TCL/HDL örnekleri referans değeri taşır
        else:
            is_conceptual = (
                result.query_type in (QueryType.WHAT, QueryType.WHY)
                and not _has_project_signal
            )
            n_doc_eff = max(self.n_doc * 2, 8) if is_conceptual else self.n_doc
            result.doc_chunks = self._search_doc_store(question, n_results=n_doc_eff)

            # ── HOW + proje sinyali: yapısal IP→Doc retrieval ────────────────────
            # Semantik arama "nasıl sentezlerim" → "apply_bd_automation" bağlantısını
            # kuramaz. Graph'taki COMPONENT node'larından IP listesi çıkarılıp
            # _IP_TO_DOCS üzerinden ilgili PG/UG chunk'ları doğrudan çekilir.
            # Soru-bağımsız, IP-bağımsız — yeni proje/IP eklenince otomatik çalışır.
            if result.query_type == QueryType.HOW and _has_project_signal:
                project_for_ip = self._resolve_project(question, result.vector_hits)
                ip_chunks = self._get_ip_doc_chunks(project_for_ip, question)
                existing_doc_ids = {c.get("chunk_id") for c in result.doc_chunks}
                for c in ip_chunks:
                    if c.get("chunk_id") not in existing_doc_ids:
                        result.doc_chunks.append(c)

        return result

    # ------------------------------------------------------------------
    # Enumerate — "list all IPs/components" queries
    # top-K similarity yerine proje manifest + semantic detay
    # ------------------------------------------------------------------

    # chunk_label'lar bu listedeyse IP değil — manifest'ten çıkar
    _ENUMERATE_SKIP_LABELS = {
        "preamble", "address_map", "net_connections", "get_script_folder",
        "write_mig_file_system_mig_7series_0_0", "ip_manifest",
    }
    _ENUMERATE_SKIP_PREFIXES = (
        "lines ", "write_mig_file", "get_script", " (part ", "create_hier_cell_",
        "create_root_design", "preamble",
    )
    _ENUMERATE_SKIP_SUFFIXES = (" (header)", " (part 1)", " (part 2)", " (part 3)")

    def _route_enumerate(self, question: str) -> QueryResult:
        """
        ENUMERATE — "tüm IP'leri listele" tarzı sorgular.
        1. Proje manifest: tüm TCL chunk label'larından IP listesi üret (içerik yok, sadece isimler).
        2. Semantic detay: normal top-K search ile konfigürasyon chunk'ları.
        LLM hem tam listeyi hem de detayları görür.
        """
        vector_hits = self.vector.query(question, n_results=self.n_vector)
        vector_hits = [h for h in vector_hits if h["node_id"] not in self._stale_ids]
        graph_nodes = self._enrich_from_graph(vector_hits)

        project = self._resolve_project(question, vector_hits)
        graph_nodes = self._filter_cross_project_nodes(graph_nodes, project)

        # ── 1. Manifest ────────────────────────────────────────────────
        manifest_chunk: Optional[Dict] = None
        if project and self.source_store:
            metas = self.source_store.enumerate_project_chunks(project, file_types=["tcl"])
            ip_labels = sorted({
                m.get("chunk_label", "")
                for m in metas
                if m.get("chunk_label", "") not in self._ENUMERATE_SKIP_LABELS
                and not any(m.get("chunk_label", "").startswith(p)
                            for p in self._ENUMERATE_SKIP_PREFIXES)
                and not any(m.get("chunk_label", "").endswith(s)
                            for s in self._ENUMERATE_SKIP_SUFFIXES)
                and m.get("chunk_label", "")
            })
            if ip_labels:
                manifest_content = (
                    f"[IP Manifest — {project}]\n"
                    f"Bu projede {len(ip_labels)} IP/bileşen tespit edildi:\n"
                    + ", ".join(ip_labels) + "\n"
                    f"\n(Detay için aşağıdaki IP konfigürasyon chunk'larına bakın.)"
                )
                manifest_chunk = {
                    "chunk_id":        f"{project}_ip_manifest",
                    "content":         manifest_content,
                    "file_path":       "",
                    "file_type":       "tcl",
                    "project":         project,
                    "start_line":      0,
                    "end_line":        0,
                    "chunk_label":     "ip_manifest",
                    "similarity":      1.0,
                    "rrf_score":       1.0,
                    "related_node_ids": [],
                }

        # ── 2. Semantic detay ───────────────────────────────────────────
        source_chunks = self._search_source_chunks(question, project_filter=project)
        if manifest_chunk:
            # Manifest her zaman ilk sıraya
            source_chunks = [manifest_chunk] + [
                c for c in source_chunks if c["chunk_id"] != manifest_chunk["chunk_id"]
            ]

        return QueryResult(
            query=question,
            query_type=QueryType.ENUMERATE,
            vector_hits=vector_hits,
            graph_nodes=graph_nodes,
            graph_edges=[],
            req_tree=[],
            source_chunks=source_chunks,
            stale_ids=self._stale_ids,
        )

    # ------------------------------------------------------------------
    # What — all stores parallel
    # ------------------------------------------------------------------

    _PROJECT_QUERY_RE = re.compile(
        r'(proje\w*\s*(nelerdir|listele|kaç|hangi|var|mevcut|bulunan|göster)'
        r'|hangi\s+proje\w*'
        r'|kaç\s+proje'
        r'|sistemdeki\s+proje\w*'
        r'|what\s+project'
        r'|list.*project)',
        re.IGNORECASE,
    )

    def _route_what(self, question: str) -> QueryResult:
        """General: search all stores in parallel.

        Special case: PROJECT listing queries → inject all PROJECT nodes at top,
        suppress req_tree expansion (avoids flooding context with REQUIREMENT nodes).
        Architecture §3: PROJECT nodes are root context.
        """
        is_project_listing = bool(self._PROJECT_QUERY_RE.search(question))

        vector_hits = self.vector.query(question, n_results=self.n_vector)
        vector_hits = [h for h in vector_hits if h["node_id"] not in self._stale_ids]

        graph_nodes = self._enrich_from_graph(vector_hits)

        # For project listing queries: always include all PROJECT nodes at the front
        if is_project_listing:
            existing_ids = {n.get("node_id", "") for n in graph_nodes}
            for node in self.graph.get_all_nodes():
                if node.get("node_type") == "PROJECT":
                    nid = node.get("node_id", "")
                    if nid and nid not in existing_ids and nid not in self._stale_ids:
                        graph_nodes.insert(0, {"node_id": nid, **node})
                        existing_ids.add(nid)

        # ── Edge traversal for WHAT queries ──────────────────────────────
        # Enrich context with structural edges so LLM can reason multi-hop.
        what_edges = []
        seen_edge_pairs: set = set()
        _WHAT_EDGE_TYPES = (
            "IMPLEMENTS", "CONNECTS_TO", "PROVIDES_DATA_TO",
            "DEPENDS_ON", "CONSTRAINED_BY", "VERIFIED_BY",
            "MOTIVATED_BY", "ANALOGOUS_TO", "REUSES_PATTERN",
            "CONTRADICTS",
        )
        for node in list(graph_nodes):  # iterate copy — may grow
            nid = node.get("node_id", "")
            if not nid:
                continue
            for etype in _WHAT_EDGE_TYPES:
                for nbr_id, eattrs in self.graph.get_neighbors(
                    nid, edge_type=etype, direction="both"
                ):
                    pair = (min(nid, nbr_id), max(nid, nbr_id), etype)
                    if pair in seen_edge_pairs:
                        continue
                    seen_edge_pairs.add(pair)
                    what_edges.append({
                        "from": nid, "to": nbr_id,
                        "edge_type": etype, **eattrs,
                    })
                    # Pull neighbor node into context if missing
                    if not any(n.get("node_id") == nbr_id for n in graph_nodes):
                        nbr_node = self.graph.get_node(nbr_id)
                        if nbr_node and nbr_id not in self._stale_ids:
                            graph_nodes.append({"node_id": nbr_id, **nbr_node})

        project = self._resolve_project(question, vector_hits)
        graph_nodes = self._filter_cross_project_nodes(graph_nodes, project)

        # req_tree: filter'dan SONRA hesaplanmalı — aksi hâlde filtrelenmemiş
        # REQUIREMENT node'ları req_tree'ye sızar (özellikle proje tespitsiz genel sorgularda).
        if is_project_listing:
            # Skip req_tree expansion — project listing should not flood REQUIREMENT nodes
            req_tree = []
        else:
            req_tree = self._get_req_trees_for_nodes(graph_nodes)

        # Kavramsal sorular: sinyal tablosu kontrolü _search_source_chunks'tan ÖNCE.
        # Tier 2b semantik arama genel sorular için yanlış proje döndürebilir (0.45 eşik).
        # has_project_signal=False ise Tier 2b'nin proje filtresini yok say → global top-4.
        has_project_signal = (
            self._exact_project_match(question) is not None
            or any(kw in question.lower() for kw, _ in self._TEXT_PROJECT_SIGNALS)
        )
        effective_project = project if (has_project_signal or is_project_listing) else None
        source_chunks = self._search_source_chunks(question, project_filter=effective_project)
        if not has_project_signal and not is_project_listing:
            source_chunks = source_chunks[:4]

        return QueryResult(
            query=question,
            query_type=QueryType.WHAT,
            vector_hits=vector_hits,
            graph_nodes=graph_nodes,
            graph_edges=what_edges,
            req_tree=req_tree,
            source_chunks=source_chunks,
            stale_ids=self._stale_ids,
        )

    # ------------------------------------------------------------------
    # How — COMPONENT + PATTERN
    # ------------------------------------------------------------------

    def _route_how(self, question: str) -> QueryResult:
        """Implementation details: focus on COMPONENT and PATTERN nodes."""
        # Vector search filtered to component/pattern types
        comp_hits = self.vector.query(question, n_results=self.n_vector,
                                       node_type_filter="COMPONENT")
        pat_hits = self.vector.query(question, n_results=3,
                                      node_type_filter="PATTERN")
        vector_hits = comp_hits + pat_hits
        vector_hits = [h for h in vector_hits if h["node_id"] not in self._stale_ids]

        # Also get COMPONENT nodes that IMPLEMENT requirements matched by vector
        graph_nodes = self._enrich_from_graph(vector_hits)

        # Find patterns reused by these components
        pattern_edges = []
        for node in graph_nodes:
            nid = node.get("node_id", "")
            for nbr_id, eattrs in self.graph.get_neighbors(nid, edge_type="REUSES_PATTERN"):
                pattern_edges.append({"from": nid, "to": nbr_id, **eattrs})
            for nbr_id, eattrs in self.graph.get_neighbors(nid, edge_type="DEPENDS_ON"):
                pattern_edges.append({"from": nid, "to": nbr_id, **eattrs})

        project = self._resolve_project(question, vector_hits)
        graph_nodes = self._filter_cross_project_nodes(graph_nodes, project)

        # Meta chunks: HOW route → her zaman prepend, soru regex'ine bağımlılık yok.
        # Routing zaten HOW olarak sınıflandırdı — classifier ne kadar iyileşirse
        # meta boost da otomatik iyileşir. Yeni proje eklendiğinde de çalışır.
        seen_ids: set = set()
        source_chunks: List[Dict[str, Any]] = []
        if self.source_store and project:
            for mc in self.source_store.get_meta_chunks(project):
                seen_ids.add(mc["chunk_id"])
                source_chunks.append(mc)
        for c in self._search_source_chunks(question, project_filter=project):
            if c["chunk_id"] not in seen_ids:
                source_chunks.append(c)

        return QueryResult(
            query=question,
            query_type=QueryType.HOW,
            vector_hits=vector_hits,
            graph_nodes=graph_nodes,
            graph_edges=pattern_edges,
            source_chunks=source_chunks,
            stale_ids=self._stale_ids,
        )

    # ------------------------------------------------------------------
    # Why — DECISION + MOTIVATED_BY
    # ------------------------------------------------------------------

    def _route_why(self, question: str) -> QueryResult:
        """Rationale: focus on DECISION nodes and MOTIVATED_BY edges."""
        # Vector search for DECISION nodes
        dec_hits = self.vector.query(question, n_results=self.n_vector,
                                      node_type_filter="DECISION")
        # Also general search for context
        gen_hits = self.vector.query(question, n_results=3)
        vector_hits = dec_hits + [h for h in gen_hits
                                   if h["node_id"] not in {x["node_id"] for x in dec_hits}]
        vector_hits = [h for h in vector_hits if h["node_id"] not in self._stale_ids]

        graph_nodes = self._enrich_from_graph(vector_hits)

        # Traverse MOTIVATED_BY edges from DECISION nodes
        motivated_edges = []
        for node in graph_nodes:
            nid = node.get("node_id", "")
            if node.get("node_type") == "DECISION":
                for nbr_id, eattrs in self.graph.get_neighbors(nid, edge_type="MOTIVATED_BY"):
                    motivated_edges.append({"from": nid, "to": nbr_id, **eattrs})
                for nbr_id, eattrs in self.graph.get_neighbors(nid, edge_type="ALTERNATIVE_TO"):
                    motivated_edges.append({"from": nid, "to": nbr_id, **eattrs})

        # Get EVIDENCE nodes linked to decisions
        evidence_nodes = []
        for edge in motivated_edges:
            ev_node = self.graph.get_node(edge.get("to", ""))
            if ev_node and ev_node.get("node_type") in ("EVIDENCE", "REQUIREMENT"):
                evidence_nodes.append({"node_id": edge["to"], **ev_node})

        project = self._resolve_project(question, vector_hits)
        graph_nodes = self._filter_cross_project_nodes(graph_nodes, project)

        # Kavramsal WHY: sinyal tablosu kontrolü _search_source_chunks'tan ÖNCE.
        # Tier 2b false positive'in proje filtresini kavramsal sorularda yok say.
        has_project_signal = (
            self._exact_project_match(question) is not None
            or any(kw in question.lower() for kw, _ in self._TEXT_PROJECT_SIGNALS)
        )
        effective_project = project if has_project_signal else None
        source_chunks = self._search_source_chunks(question, project_filter=effective_project)
        if not has_project_signal:
            source_chunks = source_chunks[:4]

        return QueryResult(
            query=question,
            query_type=QueryType.WHY,
            vector_hits=vector_hits,
            graph_nodes=graph_nodes + evidence_nodes,
            graph_edges=motivated_edges,
            source_chunks=source_chunks,
            stale_ids=self._stale_ids,
        )

    # ------------------------------------------------------------------
    # Trace — IMPLEMENTS / VERIFIED_BY chain
    # ------------------------------------------------------------------

    def _route_trace(self, question: str) -> QueryResult:
        """Traceability: follow IMPLEMENTS and VERIFIED_BY chains."""
        # For trace: prioritize COMPONENT and REQUIREMENT hits
        comp_hits = self.vector.query(question, n_results=self.n_vector,
                                       node_type_filter="COMPONENT")
        req_hits = self.vector.query(question, n_results=3,
                                      node_type_filter="REQUIREMENT")
        gen_hits = self.vector.query(question, n_results=3)

        seen = set()
        vector_hits = []
        for h in comp_hits + req_hits + gen_hits:
            nid = h["node_id"]
            if nid not in seen and nid not in self._stale_ids:
                seen.add(nid)
                vector_hits.append(h)

        graph_nodes = self._enrich_from_graph(vector_hits)

        # Follow IMPLEMENTS and VERIFIED_BY in both directions
        trace_edges = []
        visited_nodes: Dict[str, Dict] = {n["node_id"]: n for n in graph_nodes
                                           if n.get("node_id")}

        for node in list(graph_nodes):
            nid = node.get("node_id", "")
            # IMPLEMENTS: component → requirement
            for nbr_id, eattrs in self.graph.get_neighbors(nid, edge_type="IMPLEMENTS",
                                                            direction="both"):
                trace_edges.append({"from": nid, "to": nbr_id, **eattrs})
                if nbr_id not in visited_nodes:
                    n = self.graph.get_node(nbr_id)
                    if n:
                        visited_nodes[nbr_id] = {"node_id": nbr_id, **n}

            # VERIFIED_BY: requirement → evidence
            for nbr_id, eattrs in self.graph.get_neighbors(nid, edge_type="VERIFIED_BY",
                                                            direction="both"):
                trace_edges.append({"from": nid, "to": nbr_id, **eattrs})
                if nbr_id not in visited_nodes:
                    n = self.graph.get_node(nbr_id)
                    if n:
                        visited_nodes[nbr_id] = {"node_id": nbr_id, **n}

            # CONSTRAINED_BY
            for nbr_id, eattrs in self.graph.get_neighbors(nid, edge_type="CONSTRAINED_BY"):
                trace_edges.append({"from": nid, "to": nbr_id, **eattrs})

            # DEPENDS_ON: data path chain traversal (e.g. axi_dma_0 → mig_7series_0)
            for nbr_id, eattrs in self.graph.get_neighbors(nid, edge_type="DEPENDS_ON",
                                                            direction="both"):
                trace_edges.append({"from": nid, "to": nbr_id,
                                    "edge_type": "DEPENDS_ON", **eattrs})
                if nbr_id not in visited_nodes:
                    n = self.graph.get_node(nbr_id)
                    if n:
                        visited_nodes[nbr_id] = {"node_id": nbr_id, **n}

        project = self._resolve_project(question, vector_hits)
        trace_nodes = self._filter_cross_project_nodes(list(visited_nodes.values()), project)
        # req_tree: filter'dan SONRA — filtrelenmiş node'lar üzerinden genişlet
        req_tree = self._get_req_trees_for_nodes(trace_nodes)
        source_chunks = self._search_source_chunks(question, project_filter=project)

        return QueryResult(
            query=question,
            query_type=QueryType.TRACE,
            vector_hits=vector_hits,
            graph_nodes=trace_nodes,
            graph_edges=trace_edges,
            req_tree=req_tree,
            source_chunks=source_chunks,
            stale_ids=self._stale_ids,
        )

    # ------------------------------------------------------------------
    # CrossRef — ANALOGOUS_TO / CONTRADICTS
    # ------------------------------------------------------------------

    def _route_crossref(self, question: str) -> QueryResult:
        """Cross-reference: comparison and contradiction edges."""
        # Daha geniş vector arama: CrossRef için n_results 2x
        vector_hits = self.vector.query(question, n_results=self.n_vector * 2)
        vector_hits = [h for h in vector_hits if h["node_id"] not in self._stale_ids]

        # İsim bazlı fallback: sorguda geçen bileşen isimleri graph'tan direkt al
        import re as _re
        q_lower = question.lower()
        for node in self.graph.get_all_nodes():
            nid = node.get("node_id", "")
            nname = node.get("name", "").lower()
            # node_id'nin kısa identifier kısmı (COMP-A-clk_wiz_0 → clk_wiz_0)
            short_id = nid.split("-", 2)[-1].lower() if "-" in nid else nid.lower()
            # _0, _1 gibi sayı suffix'lerini strip et (clk_wiz_0 → clk_wiz)
            short_id_base = _re.sub(r'_\d+$', '', short_id)
            if (short_id and short_id in q_lower) or \
               (short_id_base and len(short_id_base) > 3 and short_id_base in q_lower) or \
               (nname and any(w in q_lower for w in nname.split()[:2] if len(w) > 3)):
                if not any(h["node_id"] == nid for h in vector_hits):
                    vector_hits.append({
                        "node_id": nid,
                        "similarity": 0.5,  # fallback sabit skor
                        "metadata": {},
                        "text": "",
                    })

        graph_nodes = self._enrich_from_graph(vector_hits)

        cross_edges = []
        visited_nodes: Dict[str, Dict] = {n["node_id"]: n for n in graph_nodes
                                           if n.get("node_id")}

        for node in list(graph_nodes):
            nid = node.get("node_id", "")
            for edge_type in ("ANALOGOUS_TO", "CONTRADICTS", "ALTERNATIVE_TO"):
                for nbr_id, eattrs in self.graph.get_neighbors(nid, edge_type=edge_type,
                                                                direction="both"):
                    cross_edges.append({"from": nid, "to": nbr_id,
                                        "edge_type": edge_type, **eattrs})
                    if nbr_id not in visited_nodes:
                        n = self.graph.get_node(nbr_id)
                        if n:
                            visited_nodes[nbr_id] = {"node_id": nbr_id, **n}

        # Global fallback: "tüm cross-project ilişkileri" meta-sorgusu için
        # Eğer hiç edge bulunamadıysa ve soru ANALOGOUS_TO/CONTRADICTS hakkındaysa,
        # graph'taki tüm cross-project edge'leri dahil et.
        if not cross_edges:
            q_lower = question.lower()
            meta_signals = (
                "analogous_to", "contradicts", "benzer yapı", "çelişki",
                "ilişki", "benzer", "analogous", "similar", "relationship",
                "hangi ilişki", "ne tür ilişki",
            )
            if any(sig in q_lower for sig in meta_signals):
                for u, v, eattrs in self.graph._graph.edges(data=True):
                    etype = eattrs.get("edge_type", "")
                    if etype in ("ANALOGOUS_TO", "CONTRADICTS", "ALTERNATIVE_TO"):
                        cross_edges.append({"from": u, "to": v, "edge_type": etype,
                                            **{k: v2 for k, v2 in eattrs.items()
                                               if k != "edge_type"}})
                        for nid in (u, v):
                            if nid not in visited_nodes:
                                node_data = self.graph.get_node(nid)
                                if node_data:
                                    visited_nodes[nid] = {"node_id": nid, **node_data}

        # CrossRef: her zaman global arama — karşılaştırma sorguları çok proje gerektirir
        source_chunks = self._search_source_chunks(question, project_filter=None)

        return QueryResult(
            query=question,
            query_type=QueryType.CROSSREF,
            vector_hits=vector_hits,
            graph_nodes=list(visited_nodes.values()),
            graph_edges=cross_edges,
            source_chunks=source_chunks,
            stale_ids=self._stale_ids,
        )

    # ------------------------------------------------------------------
    # Source chunk helper — 4th store
    # ------------------------------------------------------------------

    # Statik proje sinyalleri — YALNIZCA FTS5 auto-signals'da bulunmayan
    # doğal dil / Türkçe / teknoloji terimler.
    #
    # FTS5 index zamanında otomatik çıkarılanlar (chunk_label, dosya adı, TCL IP):
    #   axis2fifo, fifo2audpwm, tone_generator, create_gtx_ddr_mb, create_i2c_with_xdc,
    #   aurora_8b10b gibi spesifik terimler _build_dynamic_signals()'de FTS5'ten okunur.
    #
    # Bu listede sadece kaynak kodda GEÇMEYEN ama sohbette kullanılan terimler kalır.
    _TEXT_PROJECT_SIGNALS: List[tuple] = [
        # Doğal dil / Türkçe (kaynak kodda yok)
        ("dma ses", "nexys_a7_dma_audio"),
        ("dma audio", "nexys_a7_dma_audio"),
        ("pwm audio", "nexys_a7_dma_audio"),
        ("s2mm", "nexys_a7_dma_audio"),           # DMA yönü, kod içinde yok label'da
        ("mm2s", "nexys_a7_dma_audio"),
        ("ddr2", "nexys_a7_dma_audio"),            # DDR çip modeli referansı
        ("mt47h", "nexys_a7_dma_audio"),           # DDR çip model numarası başlangıcı
        # Nexys Video board → FTS5 board adından gelmiyor (alt-proje belirsizliği)
        ("nexys video gtx", "gtx_ddr_example"),    # Spesifik alt-proje tanımlayıcı
        ("nexys video hdmi", "hdmi_video_example"),
        ("nexys video", "axi_gpio_example"),        # Default Nexys Video → GPIO örneği
        ("lvcmos25", "axi_gpio_example"),           # XDC IOSTANDARD
        ("lvcmos12", "axi_gpio_example"),
        # GTX Transceiver doğal dil
        ("gtx transceiver", "gtx_ddr_example"),
        ("aurora 8b10b", "gtx_ddr_example"),        # Boşluklu form
        ("8b10b", "gtx_ddr_example"),               # Kısaltma
        # HDMI doğal dil
        ("hdmi video", "hdmi_video_example"),
        ("axi vdma", "hdmi_video_example"),         # Boşluklu form (axi_vdma shared!)
        ("1080p", "hdmi_video_example"),
        ("hdmi giriş", "hdmi_video_example"),
        ("hdmi çıkış", "hdmi_video_example"),
        # PCIe doğal dil
        ("pcie dma ddr", "pcie_dma_ddr_example"),
        ("xdma mb", "pcie_xdma_mb_example"),
        # RGMII doğal dil
        ("rgmii", "rgmii_example"),
        # Arty S7 doğal dil / kısaltmalar
        ("arty s7", "arty_s7_25_base_rt"),
        ("arty-s7", "arty_s7_25_base_rt"),
        ("arty s7-25", "arty_s7_25_base_rt"),
        ("arty s7 25", "arty_s7_25_base_rt"),
        ("base-rt", "arty_s7_25_base_rt"),
        ("freertos hello", "arty_s7_25_base_rt"),
        ("spartan-7", "arty_s7_25_base_rt"),
        ("spartan 7", "arty_s7_25_base_rt"),
        # Zybo doğal dil / kısaltmalar
        ("zybo z7", "zybo_z7_20_pcam_5c"),
        ("zybo-z7", "zybo_z7_20_pcam_5c"),
        ("pcam 5c", "zybo_z7_20_pcam_5c"),
        ("pcam5c", "zybo_z7_20_pcam_5c"),
        ("mipi csi", "zybo_z7_20_pcam_5c"),
        ("mipi csi-2", "zybo_z7_20_pcam_5c"),
        ("dphy", "zybo_z7_20_pcam_5c"),
        ("d-phy", "zybo_z7_20_pcam_5c"),
        ("zynq-7000", "zybo_z7_20_pcam_5c"),
        ("zynq 7000", "zybo_z7_20_pcam_5c"),
        ("dviclock", "zybo_z7_20_pcam_5c"),
    ]

    def _build_shared_board_names(self) -> frozenset:
        """
        Birden fazla projede kullanılan board adlarını hesapla.

        Yapısal kural: Eğer bir board adı N≥2 projeye aitse, o board adı
        proje discriminatoru değildir ve routing sinyali olarak kullanılamaz.
        Ör: "Nexys Video" → 8 proje → sinyal olamaz.
        Ör: Zybo Z7-20 Pcam board → 1 proje → sinyal olabilir.

        Init'te bir kez hesaplanır. Yeni proje eklendikçe otomatik güncellenir.
        """
        from collections import Counter
        board_counts: Counter = Counter()
        for node in self.graph.get_all_nodes():
            if node.get("node_type") != "PROJECT":
                continue
            board = (node.get("board", "") or "").strip().lower()
            if board:
                board_counts[board] += 1
                # Normalize varyantlar: "digilent nexys video" → "nexys video"
                # (ön ek üretici adı çıkarılır)
                for prefix in ("digilent ", "xilinx ", "avnet ", "trenz "):
                    if board.startswith(prefix):
                        short = board[len(prefix):]
                        if short:
                            board_counts[short] += 1
        return frozenset(b for b, c in board_counts.items() if c > 1)

    def _build_dynamic_signals(self) -> List[tuple]:
        """
        (keyword, project_id) sinyal tablosunu üç kaynaktan birleştir:

        1. GraphStore PROJECT node'ları: project_id + board adı + fpga_part kısaltması
        2. FTS5 signals tablosu: index zamanında otomatik çıkarılan UNIQUE keyword'ler
           (chunk_label, dosya adı, TCL create_bd_cell IP adları)
        3. _TEXT_PROJECT_SIGNALS statik liste: FTS5'te bulunmayan doğal dil/Türkçe girişler

        100+ proje için: yeni proje eklendiğinde yalnızca GraphStore'a node eklenir,
        re-index sonrası FTS5 otomatik kapsanır — bu dosyaya dokunmak gerekmez.
        """
        dynamic: List[tuple] = []
        seen_keywords: set = set()

        # ── 1. GraphStore PROJECT node'larından ──────────────────────────────
        for node in self.graph.get_all_nodes():
            if node.get("node_type") != "PROJECT":
                continue
            pid = node.get("node_id", "")
            if not pid:
                continue

            # project_id: altçizgili + boşluklu + tireli form
            for kw in (pid, pid.replace("_", " "), pid.replace("_", "-")):
                kw = kw.strip().lower()
                if kw and kw not in seen_keywords:
                    seen_keywords.add(kw)
                    dynamic.append((kw, pid))

            # board adı — yalnızca o board tek bir projeye özgüyse sinyal olur.
            # Yapısal kural: shared board names discriminator olamaz.
            board = (node.get("board", "") or "").strip().lower()
            if board and board not in seen_keywords and board not in self._shared_board_names:
                seen_keywords.add(board)
                dynamic.append((board, pid))

            # fpga_part kısaltması (xc7a100tcsg324-1 → xc7a100tcsg324)
            fpga_part = (node.get("fpga_part", "") or "").strip().lower()
            if fpga_part:
                short = fpga_part.split("-")[0]
                if len(short) >= 6 and short not in seen_keywords:
                    seen_keywords.add(short)
                    dynamic.append((short, pid))

        # ── 2. FTS5 auto-signals: index zamanında çıkarılan UNIQUE keyword'ler ─
        if self.source_store is not None:
            try:
                for kw, proj in self.source_store._fts.get_unique_signals():
                    if kw not in seen_keywords:
                        seen_keywords.add(kw)
                        dynamic.append((kw, proj))
                        # Underscore ↔ space her iki form
                        # Yapısal kural: Birden fazla projenin paylaştığı board adı
                        # varyantları routing sinyali olamaz (shared board ≠ project discriminator).
                        kw_alt = kw.replace("_", " ") if "_" in kw else kw.replace(" ", "_")
                        if (kw_alt != kw
                                and kw_alt not in seen_keywords
                                and kw_alt not in self._shared_board_names):
                            seen_keywords.add(kw_alt)
                            dynamic.append((kw_alt, proj))
            except Exception:
                pass  # Source store erişilemez → sessizce devam

        # ── 3. Statik liste: FTS5'te bulunmayan doğal dil / Türkçe girişler ─
        for kw, proj in self.__class__._TEXT_PROJECT_SIGNALS:
            if kw not in seen_keywords:
                seen_keywords.add(kw)
                dynamic.append((kw, proj))

        return dynamic

    def _build_project_tag_map(self) -> Dict[str, str]:
        """
        Graph node_id prefix/tag → project_id eşlemesi.
        _infer_project() için kullanılır.
        Yeni projeler için COMP-{yeni_proje_tag}-* gibi node'lar varsa otomatik kapsanır.
        """
        tag_map: Dict[str, str] = {}
        for node in self.graph.get_all_nodes():
            if node.get("node_type") != "PROJECT":
                continue
            pid = node.get("node_id", "")
            # Eski convention: PROJECT-A → tag "A", COMP-A-* → A
            # Yeni convention: PROJECT node_id = proje adı, COMP node_id = COMP-{pid}-*
            # Her ikisini de map'e ekle
            tag_map[pid] = pid
            # Kısa tag (geriye dönük uyum: A → nexys_a7_dma_audio)
        # Hard-coded geriye dönük uyum
        tag_map.setdefault("A", "nexys_a7_dma_audio")
        tag_map.setdefault("B", "axi_gpio_example")
        return tag_map

    # Tüm projeler birlikte sorulduğunda → None (global arama, filtre yok)
    _ALL_PROJECTS_RE = re.compile(
        r'(her iki proje|iki proje\b|tüm projeler\w*|tüm proje\w*'
        r'|mevcut projeler\w*|sistemdeki projeler\w*'
        r'|projelerimiz\w*|projeleriniz\w*'
        r'|bütün projeler\w*|hangi projeler\w*'
        r'|projeler(?:in|de|den|le|i|imiz|iniz|imizin|inizin)?\b'
        r'|referans projeler\w*)',
        re.IGNORECASE,
    )

    def _resolve_project(
        self,
        question: str,
        vector_hits: List[Dict[str, Any]],
    ) -> Optional[str]:
        """
        Soru için proje filtresi belirle.
        Çok projeli / danışman sorularda None döner (global arama).

        Sıra:
          0. Exact project_id match → en güçlü sinyal (benzer isimli projeler karışmaz)
          1. Tüm-projeler pattern → None
          2. Metin keyword eşleşmesi → gerçek proje adı
          2b. Semantic PROJECT node araması → keyword gerektirmez, tüm projeler için çalışır
          3. Vector node_id voting fallback
        """
        q_lower = question.lower()

        # Tier 0: Exact project ID match — en kesin sinyal
        # Soruda "nexys_4_abacus" veya "nexys 4 abacus" geçiyorsa direkt döndür.
        # Benzer isimli projeler (arty_s7_25 vs arty_s7_50) için longest-match kazanır.
        exact = self._exact_project_match(question)
        if exact:
            return exact

        # Tier 1: Tüm projeler isteniyor → filtre yok
        if self._ALL_PROJECTS_RE.search(q_lower):
            return None

        # Tier 2: Spesifik proje keyword eşleşmesi — longest-match-wins
        # Sinyaller _build_dynamic_signals()'da len(keyword) DESC sıralanır.
        # Uzun keyword = daha özgün sinyal → daha önce değerlendirilir.
        # "nexys a7" (8 kar.) her zaman "uart" (4 kar.) önünde bulunur.
        for keyword, project in self._TEXT_PROJECT_SIGNALS:
            if keyword in q_lower:
                return project

        # Tier 2b: Semantic PROJECT node araması (keyword bağımsız)
        # VectorStore'daki PROJECT node'larını semantik olarak sorgular.
        # Yeni proje eklendiğinde keyword listesine dokunmadan otomatik çalışır.
        # Graph PROJECT node'u olmayan projeler için Tier 3'e düşer.
        try:
            proj_hits = self.vector.query(question, n_results=3,
                                          node_type_filter="PROJECT")
            if proj_hits:
                top = proj_hits[0]
                pid = top["node_id"]
                # Yalnızca güçlü semantic eşleşme — düşük skor proje tespiti için yeterli değil
                if top["similarity"] >= 0.45 and pid not in self._stale_ids:
                    return pid
        except Exception:
            pass  # Vector store erişilemez → sessizce Tier 3'e geç

        # Tier 3: Vector node_id voting fallback
        return self._infer_project(vector_hits)

    def _infer_project(self, vector_hits: List[Dict[str, Any]]) -> Optional[str]:
        """
        Vector hit node_id'lerinden proje adını tahmin et.
        Node ID convention:
          - COMP-{proj_tag}-* → proje (dinamik tag map ile)
          - PROJECT-{proj_id} → doğrudan proje adı
          - DMA-* → nexys_a7_dma_audio (legacy)
          - SDOC/EVID/PAT → güvenilmez, atla
        70%+ oy → o proje; aksi halde None (global arama).

        100+ proje için: _build_project_tag_map() ile dinamik; hardcoded map yok.
        """
        # Dinamik tag map: graph PROJECT node'larından build edilir
        tag_map = self._build_project_tag_map()

        # Tüm mevcut proje ID'leri (PROJECT node isimlerinden)
        all_project_ids: set = set(tag_map.values())

        votes: Dict[str, int] = {}
        for hit in vector_hits:
            nid = hit.get("node_id", "")
            prefix = nid.split("-")[0] if "-" in nid else nid
            if prefix in ("SDOC", "EVID", "PAT", "AXI", "PATTERN"):
                continue
            if prefix == "DMA":
                votes["nexys_a7_dma_audio"] = votes.get("nexys_a7_dma_audio", 0) + 1
                continue
            # PROJECT node'unun kendisi → node_id = proje adı (yeni convention)
            if nid in all_project_ids:
                votes[nid] = votes.get(nid, 0) + 2  # Direkt eşleşme → 2 oy
                continue
            # COMP-{tag}-* → tag'den proje
            if nid.startswith("COMP-") and nid.count("-") >= 2:
                tag = nid.split("-")[1]
                proj = tag_map.get(tag)
                if proj:
                    votes[proj] = votes.get(proj, 0) + 1
            # Legacy: REQ-A, CONST-B vb.
            elif "-A-" in nid or nid.startswith("REQ-A") or nid.startswith("CONST-A"):
                votes["nexys_a7_dma_audio"] = votes.get("nexys_a7_dma_audio", 0) + 1
            elif "-B-" in nid or nid.startswith("REQ-B") or nid.startswith("CONST-B"):
                votes["axi_gpio_example"] = votes.get("axi_gpio_example", 0) + 1

        total = sum(votes.values())
        if total == 0:
            return None
        best_proj, best_count = max(votes.items(), key=lambda x: x[1])
        if best_count / total >= 0.70:
            return best_proj
        return None  # belirsiz → filtre yok

    # Yalnızca Türkçe kavramlar → İngilizce karşılıkları.
    # BM25 artık kod tanımlayıcılarını (PACKAGE_PIN, spi_mosi, AB22, CONFIG...) direkt buluyor.
    # Bu dict sadece BM25'in bilemeyeceği Türkçe→İngilizce kavram eşlemelerini içerir.
    _TR_EN_TERMS = {
        # Türkçe donanım/yazılım kavramları
        "saat":             "clock CLK clk_wiz MMCM PLL",
        "bellek":           "memory DDR BRAM RAM",
        "bellek haritası":  "address map create_bd_addr_seg offset",
        "adres haritası":   "address map create_bd_addr_seg SEG offset",
        "adres":            "address baseaddr offset",
        "kesme":            "interrupt irq INTC",
        "zamanlama":        "timing constraint create_clock",
        "sentez":           "synthesis synth_1 synth_design",
        "frekans":          "frequency Hz MHz localparam",
        "yazılım":          "software firmware C code",
        "çalışma modu":     "operating mode DEMO_MODE",
        "buton":            "button",
        "varsayılan":       "default init",
        "çalıştırılabilir": "standalone AXI master",
        # Türkçe donanım bileşen adları → İngilizce
        "ivmeölçer":        "accelerometer ADXL362",
        "ivme":             "accelerometer axis",
        "sıcaklık sensörü": "temperature sensor ADT7420 I2C",
        "sıcaklık":         "temperature sensor",
        "mikrofon":         "microphone PDM",
        "ses çıkışı":       "audio output PWM amplifier",
        "ses":              "audio tone PWM",
        "ekran":            "display seven-segment digit",
        "yedi segment":     "seven-segment display digit anode cathode",
        "7 segment":        "seven-segment display digit anode cathode",
        "seri port":        "serial UART baud rate",
        # Versiyon çapraz eşleme — BM25 biremez (DDR3 soran için DDR2 içeriği)
        "ddr3":             "DDR2 mig_7series MIG SDRAM",
    }

    def _augment_query(self, question: str) -> str:
        """
        Türkçe soru → İngilizce kod terimlerine çevirerek augmented query üret.
        Embedding'in Türkçe soru ↔ İngilizce kod arasındaki boşluğu kapatır.
        """
        # Türkçe büyük İ → küçük i normalizasyonu
        # Python .lower() converts İ (U+0130) to i + combining dot (U+0069 U+0307)
        # which breaks substring matching against plain 'i'. Strip combining chars.
        import unicodedata
        q_lower = unicodedata.normalize("NFC", question.lower()).replace("\u0307", "")
        augments = []
        for tr_term, en_terms in self._TR_EN_TERMS.items():
            if tr_term in q_lower:
                augments.append(en_terms)
        if augments:
            return question + " | " + " ".join(augments)
        return question

    # Sorguda geçebilecek kaynak dosya uzantıları
    _SOURCE_FILE_RE = re.compile(
        r'\b([\w][\w\-]*)\.(?:tcl|v|sv|c|cpp|h|hpp|xdc|json|pdf)\b', re.IGNORECASE
    )

    def _search_source_chunks(
        self,
        question: str,
        project_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        SourceChunkStore'u sorgula.
        - project_filter verilirse önce o projeye ait chunk'larda ara (kirlilik önleme).
          Yeterli sonuç gelmezse global aramayla tamamla.
        - Türkçe sorular için augmented query ile daha iyi retrieval sağlar.
        - Sorguda dosya adı geçiyorsa o dosyanın chunk'larını garantili olarak ekler.
        - Store mevcut değilse boş liste döndür (graceful degradation).
        """
        if self.source_store is None:
            return []
        try:
            augmented_q = self._augment_query(question)

            # File-name boost: sorguda belirtilen dosyaların en ilgili chunk'larını getir.
            file_chunks: List[Dict[str, Any]] = []
            seen_ids: set = set()
            mentioned_stems = self._SOURCE_FILE_RE.findall(question)
            for stem in mentioned_stems:
                for h in self.source_store.search_within_file(augmented_q, stem, n_results=8):
                    if h["chunk_id"] not in seen_ids:
                        seen_ids.add(h["chunk_id"])
                        file_chunks.append(h)

            # Proje filtreli arama (proje tespit edildiyse)
            if project_filter:
                filtered_hits = self.source_store.search(
                    augmented_q,
                    n_results=self.n_source,
                    project_filter=project_filter,
                )
                for h in filtered_hits:
                    if h["chunk_id"] not in seen_ids:
                        seen_ids.add(h["chunk_id"])
                        file_chunks.append(h)

                # Yeterli sonuç geldiyse bitir; az geldiyse global aramayla tamamla
                min_needed = max(3, self.n_source // 3)
                if len(file_chunks) >= min_needed:
                    return file_chunks
                # Fallback: eksik kalan kadar global aramadan al
                remaining = self.n_source - len(file_chunks)
                global_hits = self.source_store.search(augmented_q, n_results=remaining + 4)
                for h in global_hits:
                    if h["chunk_id"] not in seen_ids:
                        seen_ids.add(h["chunk_id"])
                        file_chunks.append(h)
                        if len(file_chunks) >= self.n_source:
                            break
            else:
                # Proje belirsiz → global arama
                general_hits = self.source_store.search(augmented_q, n_results=self.n_source)
                for h in general_hits:
                    if h["chunk_id"] not in seen_ids:
                        seen_ids.add(h["chunk_id"])
                        file_chunks.append(h)

            return file_chunks
        except Exception as e:
            print(f"  [QueryRouter] Source chunk search hata: {e}")
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _filter_cross_project_nodes(
        self,
        graph_nodes: List[Dict],
        project: Optional[str],
    ) -> List[Dict]:
        """
        Proje-spesifik node'ları filtrele:
        - project tespit edildi → PROJECT/DECISION/EVIDENCE/REQUIREMENT/ISSUE
          sadece o projeye ait olanlar geçer.
        - project tespit edilmedi → DECISION/EVIDENCE/REQUIREMENT/ISSUE hiçbiri
          geçmez (genel sorgulara proje-spesifik analiz node'ları karışmasın).
        CROSSREF sorgularında ÇAĞRILMAMALI.
        """
        _PROJECT_SPECIFIC = {"DECISION", "EVIDENCE", "REQUIREMENT", "ISSUE", "COMPONENT"}
        result = []
        for n in graph_nodes:
            ntype = n.get("node_type", "")
            nid   = n.get("node_id", "")
            nproj = n.get("project", "")

            if ntype == "PROJECT":
                if project and nid != project:
                    continue  # başka proje PROJECT node'u
            elif ntype in _PROJECT_SPECIFIC:
                if not project:
                    continue  # proje tespitsiz genel sorgu — çıkar
                if nproj and nproj != project:
                    continue  # başka projenin analiz node'u — çıkar
            result.append(n)
        return result

    def _enrich_from_graph(self, vector_hits: List[Dict]) -> List[Dict]:
        """Fetch full node attrs from GraphStore for each vector hit."""
        nodes = []
        seen = set()
        for hit in vector_hits:
            nid = hit.get("node_id", "")
            if nid in seen:
                continue
            seen.add(nid)
            node = self.graph.get_node(nid)
            if node:
                nodes.append({"node_id": nid, **node})
        return nodes

    def _get_req_trees_for_nodes(self, nodes: List[Dict]) -> List[Dict]:
        """Expand REQUIREMENT nodes via DECOMPOSES_TO BFS."""
        req_nodes = []
        seen = set()
        for node in nodes:
            nid = node.get("node_id", "")
            nt = node.get("node_type", "")
            if nt == "REQUIREMENT" and nid not in seen:
                seen.add(nid)
                tree = self.graph.get_req_tree(nid)
                for n in tree:
                    tid = n.get("node_id", "")
                    if tid not in seen:
                        seen.add(tid)
                        req_nodes.append(n)
        return req_nodes
