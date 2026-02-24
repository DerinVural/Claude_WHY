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
    (r'\b(trace|izle|zincir|traceability|hangi bileşen|implement|gerçek|karşıl)\b', QueryType.TRACE),
    # Why — rationale / decision
    (r'\b(neden|why|karar|rationale|gerekçe|motivated|sebep|nedeni|nasıl karar)\b', QueryType.WHY),
    # CrossRef — comparison / contradiction
    # Not: \b yerine prefix match — Türkçe ekler için (fark→farkı, benzer→benzerlik)
    (r'(karşılaştır|fark\w*|versus|\bvs\b|analogous|contradicts|çelişki|benzer\w*|farklı\w*|alternatif\w*|arasındaki|iki proje|karşılaştırma)', QueryType.CROSSREF),
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
        n_vector_results: int = 5,
        n_graph_results: int = 10,
        n_source_results: int = 4,        # kaynak chunk sayısı
    ):
        self.graph = graph_store
        self.vector = vector_store
        self.source_store = source_chunk_store   # None → graceful degradation
        self.n_vector = n_vector_results
        self.n_graph = n_graph_results
        self.n_source = n_source_results
        self._stale_ids = graph_store.get_stale_node_ids()

    def classify(self, question: str) -> QueryType:
        return classify_query(question)

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
        else:
            return self._route_what(question)

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

        project_filter = self._resolve_project(question, vector_hits)
        source_chunks = self._search_source_chunks(question, project_filter=project_filter)

        return QueryResult(
            query=question,
            query_type=QueryType.WHAT,
            vector_hits=vector_hits,
            graph_nodes=graph_nodes,
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

        # How sorguları genellikle RTL/implementation detayı arar
        project_filter = self._resolve_project(question, vector_hits)
        source_chunks = self._search_source_chunks(
            question, project_filter=project_filter, file_type_filter=None
        )

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

        project_filter = self._resolve_project(question, vector_hits)
        source_chunks = self._search_source_chunks(question, project_filter=project_filter)

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

        # Req tree for any requirements in scope
        req_tree = self._get_req_trees_for_nodes(list(visited_nodes.values()))

        project_filter = self._resolve_project(question, vector_hits)
        source_chunks = self._search_source_chunks(question, project_filter=project_filter)

        return QueryResult(
            query=question,
            query_type=QueryType.TRACE,
            vector_hits=vector_hits,
            graph_nodes=list(visited_nodes.values()),
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

        # CrossRef: iki proje karşılaştırması → her iki projeden de chunk ara
        source_chunks = self._search_source_chunks(question)

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

    # Question-text keywords that strongly indicate a specific project.
    # PROJECT-A = nexys_a7_dma_audio | PROJECT-B = axi_gpio_example (Nexys Video)
    _TEXT_PROJECT_SIGNALS: List[tuple] = [
        # PROJECT-B (axi_gpio_example / Nexys Video)
        ("nexys video", "PROJECT-B"),
        ("axi_gpio_example", "PROJECT-B"),
        ("axi_gpio_wrapper", "PROJECT-B"),  # unique RTL file for PROJECT-B
        ("lvcmos25", "PROJECT-B"),          # Nexys Video LED IOSTANDARD
        ("lvcmos12", "PROJECT-B"),          # Nexys Video switch IOSTANDARD
        ("microblaze", "PROJECT-B"),        # PROJECT-A has no MicroBlaze
        ("microblaze", "PROJECT-B"),
        ("mdm_1", "PROJECT-B"),
        ("synthesis_results", "PROJECT-B"),
        ("synthesis results", "PROJECT-B"),
        # PROJECT-A (nexys_a7_dma_audio)
        ("nexys a7", "PROJECT-A"),
        ("nexys-a7", "PROJECT-A"),
        ("dma audio", "PROJECT-A"),
        ("dma ses", "PROJECT-A"),
        ("axis2fifo", "PROJECT-A"),
        ("fifo2audpwm", "PROJECT-A"),
        ("tone_generator", "PROJECT-A"),
        ("helloworld", "PROJECT-A"),
        ("pwm audio", "PROJECT-A"),
        ("aud_pwm", "PROJECT-A"),
        ("s2mm", "PROJECT-A"),
        ("mm2s", "PROJECT-A"),
    ]

    def _resolve_project(self, question: str, vector_hits: List[Dict[str, Any]]) -> Optional[str]:
        """
        Resolve project filter with two-tier approach:
          1. High-confidence text keywords in the question (overrides voting)
          2. Fall back to vector-hit node_id voting
        Returns PROJECT-A, PROJECT-B, or None.
        """
        q_lower = question.lower()
        for keyword, project in self._TEXT_PROJECT_SIGNALS:
            if keyword in q_lower:
                return project
        return self._infer_project(vector_hits)

    def _infer_project(self, vector_hits: List[Dict[str, Any]]) -> Optional[str]:
        """
        Infer project (PROJECT-A or PROJECT-B) from vector hit node_ids.
        Node ID convention:
          - -A- in nid → PROJECT-A (nexys_a7_dma_audio)
          - -B- in nid → PROJECT-B (axi_gpio_example)
          - DMA-* or SDOC-A-* → PROJECT-A
          - AXI-DEC-* → ignored (too ambiguous)
          - SDOC-*, EVID-*, PAT-* → excluded (not reliable project signals)
        Returns None if project cannot be determined with high confidence.
        """
        votes = {"PROJECT-A": 0, "PROJECT-B": 0}
        for hit in vector_hits:
            nid = hit.get("node_id", "")
            prefix = nid.split("-")[0] if "-" in nid else nid
            # Skip unreliable prefixes
            if prefix in ("SDOC", "EVID", "PAT", "AXI", "PATTERN"):
                continue
            # DMA-* nodes → nexys_a7_dma_audio = PROJECT-A
            if prefix == "DMA":
                votes["PROJECT-A"] += 1
                continue
            # Standard -A-/-B- pattern
            if "-A-" in nid or nid.startswith("PROJECT-A") or nid.startswith("REQ-A") or nid.startswith("CONST-A"):
                votes["PROJECT-A"] += 1
            elif "-B-" in nid or nid.startswith("PROJECT-B") or nid.startswith("REQ-B") or nid.startswith("CONST-B"):
                votes["PROJECT-B"] += 1
        # Only filter if one project dominates (≥ 70% of counted votes, at least 1 vote)
        total = sum(votes.values())
        if total == 0:
            return None  # no reliable signal → don't filter
        for proj, count in votes.items():
            if count / total >= 0.70:
                return proj
        return None  # cross-project query: don't filter

    # Turkish → English code term bridge for query augmentation
    _TR_EN_TERMS = {
        "çalışma modu": "operating mode DEMO_MODE",
        "buton": "button button_pe case",
        "varsayılan": "default init PAUSED",
        "demo": "demo DEMO_MODE SW_TONE_GEN HW_TONE_GEN",
        "sdk": "SDK XAxiDma XGpio helloworld firmware",
        "yazılım": "software firmware C code function",
        # Address map — very specific TCL terms to retrieve address segment chunks
        "adres haritası": "address map create_bd_addr_seg SEG_GPIO_IN SEG_axi_dma offset 0x40000000 0x41E00000 dlmb ilmb mig_7series memaddr",
        "adres": "address baseaddr BASEADDR offset 0x40 create_bd_addr_seg SEG_axi_gpio assign_bd_address",
        "bellek haritası": "create_bd_addr_seg offset 0x40000000 0x41E00000 SEG_GPIO DDR2 MIG memmap memaddr XPAR",
        "bellek": "memory DDR2 BRAM address XPAR create_bd_addr_seg mig_7series",
        "gpio": "GPIO XGpio gpio_io C_GPIO_WIDTH gpio_io_o gpio_io_i",
        "saat": "clock clk_wiz MMCM PLL CLK100MHZ create_clock clk_out1",
        "reset": "reset rst_clk_wiz proc_sys_reset ext_reset_in dcm_locked",
        "dma": "DMA XAxiDma SimpleTransfer MM2S S2MM",
        # FIFO — specific to fifo2audpwm.v and design_1.tcl FIFO generator
        "fifo": "FIFO fifo_empty fifo_full fifo_rd_en fifo2audpwm aud_en DATA_WIDTH duty count PWM",
        "pwm": "PWM count duty DATA_WIDTH fifo2audpwm aud_pwm aud_en fifo_rd_en",
        "kesme": "interrupt irq INTC xlconcat",
        "axi": "AXI AXI4 S_AXI M_AXI connect_bd_net",
        # Timing — XDC specific
        "timing": "timing create_clock false_path multicycle set_input_delay sys_clk 10.000",
        "zamanlama": "timing constraint create_clock sys_clk 10.000 LVCMOS33",
        "iostandard": "IOSTANDARD LVCMOS33 LVCMOS25 LVCMOS12 LVCMOS15 set_property PACKAGE_PIN",
        # LED/switch — for XDC retrieval
        "led": "LED leds LVCMOS25 PACKAGE_PIN T14 set_property IOSTANDARD",
        "switch": "switches LVCMOS12 PACKAGE_PIN E22 set_property IOSTANDARD",
        "sentez": "synthesis synth_1 synth_design launch_runs BRAM LUTs",
        "frekans": "frequency Hz MHz CLK INCREMENT localparam",
        "interrupt": "interrupt irq INTC XIntc",
        # Standalone/wrapper RTL — for axi_gpio_wrapper.v
        "çalıştırılabilir": "standalone tied off AXI master slave s_axi_awaddr",
        "standalone": "standalone tied off AXI master cannot operate s_axi_awaddr 32'h0 1'b0",
        # XDC constraint file retrieval (LVCMOS33 only — project-neutral)
        "xdc": "XDC set_property PACKAGE_PIN IOSTANDARD create_clock LVCMOS33",
        # Peripheral/XPAR addressing
        "peripheral": "XPAR_GPIO_IN XPAR_GPIO_OUT XPAR_AXI_DMA XPAR_MIG7SERIES DDR_BASE_ADDR create_bd_addr_seg",
        "offset": "offset 0x40000000 0x41E00000 0x80000000 create_bd_addr_seg SEG_GPIO SEG_axi_dma",
    }

    def _augment_query(self, question: str) -> str:
        """
        Türkçe soru → İngilizce kod terimlerine çevirerek augmented query üret.
        Embedding'in Türkçe soru ↔ İngilizce kod arasındaki boşluğu kapatır.
        """
        q_lower = question.lower()
        augments = []
        for tr_term, en_terms in self._TR_EN_TERMS.items():
            if tr_term in q_lower:
                augments.append(en_terms)
        if augments:
            return question + " | " + " ".join(augments)
        return question

    def _search_source_chunks(
        self,
        question: str,
        project_filter: Optional[str] = None,
        file_type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        SourceChunkStore'u sorgula.
        Türkçe sorular için augmented query ile daha iyi retrieval sağlar.
        Store mevcut değilse boş liste döndür (graceful degradation).
        """
        if self.source_store is None:
            return []
        try:
            augmented_q = self._augment_query(question)
            return self.source_store.search(
                augmented_q,
                n_results=self.n_source,
                project_filter=project_filter,
                file_type_filter=file_type_filter,
            )
        except Exception as e:
            print(f"  [QueryRouter] Source chunk search hata: {e}")
            return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
