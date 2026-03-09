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
    """Container for 4-store federated query results."""

    def __init__(
        self,
        query: str,
        query_type: QueryType,
        vector_hits: List[Dict[str, Any]] = None,
        graph_nodes: List[Dict[str, Any]] = None,
        graph_edges: List[Dict[str, Any]] = None,
        req_tree: List[Dict[str, Any]] = None,
        source_chunks: List[Dict[str, Any]] = None,   # YENİ: 4. store
        stale_ids: set = None,
    ):
        self.query = query
        self.query_type = query_type
        self.vector_hits = vector_hits or []
        self.graph_nodes = graph_nodes or []
        self.graph_edges = graph_edges or []
        self.req_tree = req_tree or []
        self.source_chunks = source_chunks or []       # YENİ
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
                f"source_chunks={len(self.source_chunks)})")


# ---------------------------------------------------------------------------
# Keyword classifier
# ---------------------------------------------------------------------------

# Pattern: (regex, QueryType) — first match wins
_CLASSIFY_PATTERNS = [
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
        n_vector_results: int = 0,        # 0 → auto-scale ile belirlenir
        n_graph_results: int = 10,
        n_source_results: int = 0,        # 0 → auto-scale ile belirlenir
    ):
        self.graph = graph_store
        self.vector = vector_store
        self.source_store = source_chunk_store   # None → graceful degradation
        self.n_graph = n_graph_results
        self._stale_ids = graph_store.get_stale_node_ids()

        # ── Adaptif K değerleri: proje sayısına göre otomatik ölçekle ──────────
        # 100+ proje eklendiğinde, daha geniş candidate pool gerekir.
        # Nihai LLM context max_nodes=10 + max_chars=8000 ile sınırlıdır,
        # bu yüzden büyük K sadece retrieval kalitesini artırır, token maliyeti sabit.
        project_count = max(1, sum(
            1 for n in graph_store.get_all_nodes()
            if n.get("node_type") == "PROJECT"
        ))
        self.n_vector = n_vector_results if n_vector_results > 0 else max(5, min(project_count + 4, 20))
        self.n_source = n_source_results if n_source_results > 0 else max(6, min(project_count + 2, 24))

        # ── Dinamik proje sinyal tablosu ──────────────────────────────────────
        # Sınıf değişkeni _TEXT_PROJECT_SIGNALS statik (hardcoded) girişler içerir.
        # Grafta yeni PROJECT node'ları eklendiğinde otomatik olarak kapsanır.
        # Yeni projeler için gereken tek şey GraphStore'a node eklemektir —
        # index_source_files.py'ye veya query_router.py'ye dokunmak gerekmez.
        self._TEXT_PROJECT_SIGNALS = self._build_dynamic_signals()

    def classify(self, question: str) -> QueryType:
        qt = classify_query(question)
        # If two DIFFERENT projects are mentioned by text signals, force CROSSREF
        # regardless of other pattern matches (e.g., D-CROSS-1 style questions)
        if qt != QueryType.CROSSREF:
            q_lower = question.lower()
            projects_seen: set = set()
            for keyword, project in self._TEXT_PROJECT_SIGNALS:
                if keyword in q_lower:
                    projects_seen.add(project)
            if len(projects_seen) >= 2:
                qt = QueryType.CROSSREF
        return qt

    def route(self, question: str, query_type: Optional[QueryType] = None) -> QueryResult:
        """
        Main entry point. Returns QueryResult with results from all relevant stores.
        """
        if query_type is None:
            query_type = self.classify(question)

        if query_type == QueryType.WHAT:
            return self._route_what(question)
        elif query_type == QueryType.HOW:
            return self._route_how(question)
        elif query_type == QueryType.WHY:
            return self._route_why(question)
        elif query_type == QueryType.TRACE:
            return self._route_trace(question)
        elif query_type == QueryType.CROSSREF:
            return self._route_crossref(question)
        elif query_type == QueryType.ENUMERATE:
            return self._route_enumerate(question)
        else:
            return self._route_what(question)

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
            # Skip req_tree expansion — project listing should not flood REQUIREMENT nodes
            req_tree = []
        else:
            req_tree = self._get_req_trees_for_nodes(graph_nodes)

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
        source_chunks = self._search_source_chunks(question, project_filter=project)

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
        source_chunks = self._search_source_chunks(question, project_filter=project)

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
        source_chunks = self._search_source_chunks(question, project_filter=project)

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

        # Req tree for any requirements in scope
        req_tree = self._get_req_trees_for_nodes(list(visited_nodes.values()))

        project = self._resolve_project(question, vector_hits)
        trace_nodes = self._filter_cross_project_nodes(list(visited_nodes.values()), project)
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

    # Question-text keywords → specific project name (real dir name)
    # None döndüren sorular global arama yapar (filtre yok)
    _TEXT_PROJECT_SIGNALS: List[tuple] = [
        # nexys_a7_dma_audio
        ("nexys a7", "nexys_a7_dma_audio"),
        ("nexys-a7", "nexys_a7_dma_audio"),
        ("nexys_a7", "nexys_a7_dma_audio"),
        ("nexys_a7_dma_audio", "nexys_a7_dma_audio"),
        ("dma audio", "nexys_a7_dma_audio"),
        ("dma ses", "nexys_a7_dma_audio"),
        ("axis2fifo", "nexys_a7_dma_audio"),
        ("fifo2audpwm", "nexys_a7_dma_audio"),
        ("tone_generator", "nexys_a7_dma_audio"),
        ("helloworld", "nexys_a7_dma_audio"),
        ("pwm audio", "nexys_a7_dma_audio"),
        ("aud_pwm", "nexys_a7_dma_audio"),
        ("s2mm", "nexys_a7_dma_audio"),
        ("mm2s", "nexys_a7_dma_audio"),
        ("ddr2", "nexys_a7_dma_audio"),
        ("mig_7series", "nexys_a7_dma_audio"),
        ("mt47h", "nexys_a7_dma_audio"),
        # axi_gpio_example — NOT: "nexys video gtx/hdmi" daha spesifik, önce gelir
        ("nexys video gtx", "gtx_ddr_example"),
        ("nexys video hdmi", "hdmi_video_example"),
        ("nexys video", "axi_gpio_example"),
        ("axi_gpio_example", "axi_gpio_example"),
        ("gpio_example", "axi_gpio_example"),
        ("axi_gpio_wrapper", "axi_gpio_example"),
        ("lvcmos25", "axi_gpio_example"),
        ("lvcmos12", "axi_gpio_example"),
        # gtx_ddr_example
        ("gtx_ddr_example", "gtx_ddr_example"),
        ("gtx_ddr", "gtx_ddr_example"),
        ("aurora_8b10b", "gtx_ddr_example"),
        ("aurora 8b10b", "gtx_ddr_example"),
        ("gtx transceiver", "gtx_ddr_example"),
        ("create_gtx_ddr", "gtx_ddr_example"),
        ("create_mb_dma_ddr3", "gtx_ddr_example"),
        ("8b10b", "gtx_ddr_example"),
        # hdmi_video_example
        ("hdmi_video_example", "hdmi_video_example"),
        ("hdmi video", "hdmi_video_example"),
        ("hdmi_video", "hdmi_video_example"),
        ("build_hdmi_video", "hdmi_video_example"),
        ("axi_vdma", "hdmi_video_example"),
        ("axi vdma", "hdmi_video_example"),
        ("dvi2rgb", "hdmi_video_example"),
        ("rgb2dvi", "hdmi_video_example"),
        ("axi_dynclk", "hdmi_video_example"),
        ("v_tc", "hdmi_video_example"),
        ("v_vid_in_axi4s", "hdmi_video_example"),
        ("v_axi4s_vid_out", "hdmi_video_example"),
        ("1080p", "hdmi_video_example"),
        ("hdmi giriş", "hdmi_video_example"),
        ("hdmi çıkış", "hdmi_video_example"),
        ("nexys video hdmi", "hdmi_video_example"),
        # i2c_example
        ("i2c_example", "i2c_example"),
        ("create_i2c", "i2c_example"),
        # pcie_dma_ddr_example
        ("pcie_dma_ddr", "pcie_dma_ddr_example"),
        ("pcie dma ddr", "pcie_dma_ddr_example"),
        ("pcie_dma_ddr_example", "pcie_dma_ddr_example"),
        # pcie_xdma_mb_example
        ("xdma mb", "pcie_xdma_mb_example"),
        ("pcie_xdma_mb", "pcie_xdma_mb_example"),
        ("pcie_xdma_mb_example", "pcie_xdma_mb_example"),
        # rgmii_example
        ("rgmii", "rgmii_example"),
        ("rgmii_example", "rgmii_example"),
        # spi_example
        ("spi_example", "spi_example"),
        ("create_spi", "spi_example"),
        # uart_example
        ("uart_example", "uart_example"),
        ("create_uart", "uart_example"),
        # v2_mig
        ("v2_mig", "v2_mig"),
        ("mb_dma_ddr3", "v2_mig"),
        # v3_gtx
        ("v3_gtx", "v3_gtx"),
        ("mb_dma_mig_gtx", "v3_gtx"),
        # arty_s7_25_base_rt
        ("arty_s7_25_base_rt", "arty_s7_25_base_rt"),
        ("arty s7", "arty_s7_25_base_rt"),
        ("arty-s7", "arty_s7_25_base_rt"),
        ("arty s7-25", "arty_s7_25_base_rt"),
        ("arty s7 25", "arty_s7_25_base_rt"),
        ("base-rt", "arty_s7_25_base_rt"),
        ("base_rt", "arty_s7_25_base_rt"),
        ("freertos hello", "arty_s7_25_base_rt"),
        ("freertos_hello", "arty_s7_25_base_rt"),
        ("xc7s25", "arty_s7_25_base_rt"),
        ("spartan-7", "arty_s7_25_base_rt"),
        ("spartan 7", "arty_s7_25_base_rt"),
        # zybo_z7_20_pcam_5c
        ("zybo_z7_20_pcam_5c", "zybo_z7_20_pcam_5c"),
        ("zybo z7", "zybo_z7_20_pcam_5c"),
        ("zybo-z7", "zybo_z7_20_pcam_5c"),
        ("pcam 5c", "zybo_z7_20_pcam_5c"),
        ("pcam_5c", "zybo_z7_20_pcam_5c"),
        ("pcam5c", "zybo_z7_20_pcam_5c"),
        ("ov5640", "zybo_z7_20_pcam_5c"),
        ("mipi csi", "zybo_z7_20_pcam_5c"),
        ("mipi_csi", "zybo_z7_20_pcam_5c"),
        ("mipi csi-2", "zybo_z7_20_pcam_5c"),
        ("mipi_d_phy", "zybo_z7_20_pcam_5c"),
        ("dphy", "zybo_z7_20_pcam_5c"),
        ("d-phy", "zybo_z7_20_pcam_5c"),
        ("xc7z020", "zybo_z7_20_pcam_5c"),
        ("zynq-7000", "zybo_z7_20_pcam_5c"),
        ("zynq 7000", "zybo_z7_20_pcam_5c"),
        ("processing_system7", "zybo_z7_20_pcam_5c"),
        ("AXI_BayerToRGB", "zybo_z7_20_pcam_5c"),
        ("bayertorgb", "zybo_z7_20_pcam_5c"),
        ("gammacorrection", "zybo_z7_20_pcam_5c"),
        ("dviclocking", "zybo_z7_20_pcam_5c"),
        ("dviclock", "zybo_z7_20_pcam_5c"),
        ("pcam_vdma_hdmi", "zybo_z7_20_pcam_5c"),
    ]

    def _build_dynamic_signals(self) -> List[tuple]:
        """
        Graf'taki PROJECT node'larından dinamik (keyword, project_id) çiftleri üret.
        Statik _TEXT_PROJECT_SIGNALS ile birleştirir:
          - Graf node'larından: project_id itself + board name + fpga_part kısaltması
          - Statik listeden: spesifik IP/bileşen isimleri (aurora_8b10b, dvi2rgb, vb.)

        100+ proje için: yeni proje GraphStore'a eklenince otomatik kapsanır,
        bu dosyada güncelleme gerekmez.
        """
        dynamic: List[tuple] = []
        seen_keywords: set = set()

        for node in self.graph.get_all_nodes():
            if node.get("node_type") != "PROJECT":
                continue
            pid = node.get("node_id", "")
            if not pid:
                continue

            # project_id: hem altçizgili hem boşluklu form
            for kw in (pid, pid.replace("_", " "), pid.replace("_", "-")):
                kw = kw.strip().lower()
                if kw and kw not in seen_keywords:
                    seen_keywords.add(kw)
                    dynamic.append((kw, pid))

            # board adı
            board = (node.get("board", "") or "").strip().lower()
            if board and board not in seen_keywords:
                seen_keywords.add(board)
                dynamic.append((board, pid))

            # fpga_part ilk kısmı (xc7s25csga324-1 → xc7s25)
            fpga_part = (node.get("fpga_part", "") or "").strip().lower()
            if fpga_part:
                short = fpga_part.split("-")[0]  # xc7s25csga324 → xc7s25csga324 (no split) or xc7a100t
                # Sadece 6+ karakter olan unique kısmı ekle
                if len(short) >= 6 and short not in seen_keywords:
                    seen_keywords.add(short)
                    dynamic.append((short, pid))

        # Statik girişler: spesifik IP isimlerini (aurora_8b10b vb.) kapsıyor.
        # Çakışmayan statik girişleri sonuna ekle (daha düşük öncelik olsun).
        static_existing = {kw for kw, _ in dynamic}
        for kw, proj in self.__class__._TEXT_PROJECT_SIGNALS:
            if kw not in static_existing:
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
          1. Tüm-projeler pattern → None
          2. Metin keyword eşleşmesi → gerçek proje adı
          3. Vector node_id voting fallback
        """
        q_lower = question.lower()

        # Tier 1: Tüm projeler isteniyor → filtre yok
        if self._ALL_PROJECTS_RE.search(q_lower):
            return None

        # Tier 2: Spesifik proje keyword eşleşmesi
        for keyword, project in self._TEXT_PROJECT_SIGNALS:
            if keyword in q_lower:
                return project

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
        Belirlenen proje dışındaki PROJECT node'larını kaldır.
        COMPONENT/REQUIREMENT gibi non-PROJECT node'lar dokunulmaz
        (bu node'larda project field'ı genellikle yok).
        CROSSREF sorgularında ÇAĞRILMAMALI — cross-project bilgi kasıtlı isteniyor.
        """
        if not project:
            return graph_nodes
        result = []
        for n in graph_nodes:
            ntype = n.get("node_type", "")
            nid = n.get("node_id", "")
            if ntype == "PROJECT" and nid != project:
                continue  # başka proje node'u — çıkar
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
