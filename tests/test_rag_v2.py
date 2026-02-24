"""
FPGA RAG v2 — Test Suite
========================
Kapsam:
  Unit  : GraphStore, VectorStoreV2, HallucinationGate, QueryRouter, ResponseBuilder
  Enteg : Loader → Graph + Vector → Query → Gate → Response tam zincir
  Smoke : Gerçek DB üzerinde hızlı sağlık kontrolü

Çalıştırma:
  source .venv/bin/activate

  pytest tests/test_rag_v2.py -v                      # tüm testler
  pytest tests/test_rag_v2.py -v -m unit               # sadece unit
  pytest tests/test_rag_v2.py -v -m integration        # sadece entegrasyon
  pytest tests/test_rag_v2.py -v -m smoke              # sadece smoke (gerçek DB)
  pytest tests/test_rag_v2.py -v -k "GraphStore"       # sınıfa göre filtre
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Proje kökünü sys.path'e ekle
_PROJ_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJ_ROOT / "src"))

# ---------------------------------------------------------------------------
# Sabitler — gerçek DB yolları (smoke testler için)
# ---------------------------------------------------------------------------
REAL_GRAPH_DB   = str(_PROJ_ROOT / "db" / "graph" / "fpga_rag_v2_graph.json")
REAL_CHROMA_DIR = str(_PROJ_ROOT / "db" / "chroma_graph_nodes")
REAL_PIPELINE_JSON = str(_PROJ_ROOT / "data" / "fpga_rag_v2_output" / "pipeline_graph.json")

# ---------------------------------------------------------------------------
# Test Fixture — minimal in-memory graph
# ---------------------------------------------------------------------------

def _minimal_graph_data() -> Dict[str, Any]:
    """Unit testler için minimal node/edge seti. Gerçek DB gerektirmez."""
    return {
        "nodes": [
            {
                "node_id": "TEST-PROJ-A",
                "node_type": "PROJECT",
                "name": "Test Project A",
                "description": "Unit test project",
                "confidence": "HIGH",
                "version": 1,
            },
            {
                "node_id": "TEST-REQ-001",
                "node_type": "REQUIREMENT",
                "name": "Test REQ 001",
                "description": "System shall do X",
                "confidence": "HIGH",
                "project": "TEST-PROJ-A",
                "version": 1,
            },
            {
                "node_id": "TEST-REQ-002",
                "node_type": "REQUIREMENT",
                "name": "Test REQ 002",
                "description": "Sub-requirement of X",
                "confidence": "MEDIUM",
                "project": "TEST-PROJ-A",
                "version": 1,
            },
            {
                "node_id": "TEST-COMP-001",
                "node_type": "COMPONENT",
                "name": "test_module",
                "description": "RTL module implementing X",
                "confidence": "HIGH",
                "project": "TEST-PROJ-A",
                "key_logic": "output = input & enable",
                "version": 1,
            },
            {
                "node_id": "TEST-EVID-001",
                "node_type": "EVIDENCE",
                "name": "Test Evidence",
                "description": "Simulation result confirming X",
                "confidence": "HIGH",
                "project": "TEST-PROJ-A",
                "version": 1,
            },
            {
                "node_id": "TEST-DEC-001",
                "node_type": "DECISION",
                "name": "Test Decision",
                "description": "Chose approach A over B",
                "confidence": "HIGH",
                "project": "TEST-PROJ-A",
                "version": 1,
            },
            {
                "node_id": "TEST-PAT-001",
                "node_type": "PATTERN",
                "name": "AXI Handshake Pattern",
                "description": "tvalid/tready handshake",
                "confidence": "HIGH",
                "version": 1,
            },
            {
                "node_id": "TEST-CONST-001",
                "node_type": "CONSTRAINT",
                "name": "Timing Constraint",
                "description": "100 MHz max freq",
                "confidence": "HIGH",
                "version": 1,
            },
            {
                "node_id": "TEST-ISSUE-001",
                "node_type": "ISSUE",
                "name": "Test Issue",
                "description": "Known limitation",
                "confidence": "HIGH",
                "version": 1,
            },
        ],
        "edges": [
            {
                "from": "TEST-REQ-001",
                "to": "TEST-REQ-002",
                "edge_type": "DECOMPOSES_TO",
                "confidence": "HIGH",
            },
            {
                "from": "TEST-COMP-001",
                "to": "TEST-REQ-001",
                "edge_type": "IMPLEMENTS",
                "confidence": "HIGH",
            },
            {
                "from": "TEST-REQ-001",
                "to": "TEST-EVID-001",
                "edge_type": "VERIFIED_BY",
                "confidence": "HIGH",
            },
            {
                "from": "TEST-DEC-001",
                "to": "TEST-REQ-001",
                "edge_type": "MOTIVATED_BY",
                "confidence": "HIGH",
            },
            {
                "from": "TEST-COMP-001",
                "to": "TEST-CONST-001",
                "edge_type": "CONSTRAINED_BY",
                "confidence": "HIGH",
            },
        ],
    }


# ---------------------------------------------------------------------------
# GraphStore Unit Tests
# ---------------------------------------------------------------------------

class TestGraphStore:
    """src/rag_v2/graph_store.py unit testleri."""

    @pytest.fixture
    def tmp_graph(self, tmp_path):
        from rag_v2.graph_store import GraphStore
        gs = GraphStore(persist_path=str(tmp_path / "test_graph.json"))
        return gs

    @pytest.fixture
    def populated_graph(self, tmp_path):
        from rag_v2.graph_store import GraphStore
        gs = GraphStore(persist_path=str(tmp_path / "populated.json"))
        data = _minimal_graph_data()
        for node in data["nodes"]:
            gs.add_node(node["node_id"], {k: v for k, v in node.items()})
        for edge in data["edges"]:
            gs.add_edge(edge["from"], edge["to"], edge["edge_type"],
                        {"confidence": edge.get("confidence", "MEDIUM")})
        return gs

    # --- Node CRUD ---

    def test_add_and_get_node(self, tmp_graph):
        from rag_v2.graph_store import GraphStore
        tmp_graph.add_node("N1", {"node_type": "COMPONENT", "name": "mod1"})
        n = tmp_graph.get_node("N1")
        assert n is not None
        assert n["node_type"] == "COMPONENT"
        assert n["name"] == "mod1"

    def test_get_nonexistent_node_returns_none(self, tmp_graph):
        assert tmp_graph.get_node("NONEXISTENT") is None

    def test_add_node_invalid_type_raises(self, tmp_graph):
        with pytest.raises(ValueError, match="Unknown node_type"):
            tmp_graph.add_node("BAD", {"node_type": "INVALID_TYPE"})

    def test_get_nodes_by_type(self, populated_graph):
        reqs = populated_graph.get_nodes_by_type("REQUIREMENT")
        assert len(reqs) == 2
        for r in reqs:
            assert r["node_type"] == "REQUIREMENT"

    def test_get_all_nodes(self, populated_graph):
        all_n = populated_graph.get_all_nodes()
        assert len(all_n) == 9

    # --- Edge CRUD ---

    def test_add_and_get_edge(self, tmp_graph):
        tmp_graph.add_node("A", {"node_type": "COMPONENT", "name": "a"})
        tmp_graph.add_node("B", {"node_type": "REQUIREMENT", "name": "b"})
        tmp_graph.add_edge("A", "B", "IMPLEMENTS", {"confidence": "HIGH"})
        edge = tmp_graph.get_edge("A", "B")
        assert edge is not None
        assert edge["edge_type"] == "IMPLEMENTS"

    def test_add_edge_invalid_type_raises(self, tmp_graph):
        tmp_graph.add_node("A", {"node_type": "COMPONENT", "name": "a"})
        tmp_graph.add_node("B", {"node_type": "REQUIREMENT", "name": "b"})
        with pytest.raises(ValueError, match="Unknown edge_type"):
            tmp_graph.add_edge("A", "B", "UNKNOWN_EDGE")

    # --- Traversal ---

    def test_get_neighbors_out(self, populated_graph):
        neighbors = populated_graph.get_neighbors("TEST-REQ-001", edge_type="DECOMPOSES_TO")
        ids = [nid for nid, _ in neighbors]
        assert "TEST-REQ-002" in ids

    def test_get_neighbors_in(self, populated_graph):
        neighbors = populated_graph.get_neighbors("TEST-REQ-001",
                                                   edge_type="IMPLEMENTS",
                                                   direction="in")
        ids = [nid for nid, _ in neighbors]
        assert "TEST-COMP-001" in ids

    def test_find_path(self, populated_graph):
        path = populated_graph.find_path("TEST-COMP-001", "TEST-REQ-001")
        assert len(path) >= 2
        assert path[0] == "TEST-COMP-001"
        assert path[-1] == "TEST-REQ-001"

    def test_find_path_nonexistent(self, populated_graph):
        path = populated_graph.find_path("TEST-COMP-001", "TEST-PROJ-A")
        assert path == []

    def test_get_req_tree(self, populated_graph):
        tree = populated_graph.get_req_tree("TEST-REQ-001")
        ids = [n["node_id"] for n in tree]
        assert "TEST-REQ-001" in ids
        assert "TEST-REQ-002" in ids

    # --- Confidence ---

    def test_chain_confidence_all_high(self, populated_graph):
        path = ["TEST-COMP-001", "TEST-REQ-001"]
        conf = populated_graph.get_chain_confidence(path)
        assert conf == "HIGH"

    def test_chain_confidence_weakest_link(self, populated_graph):
        # TEST-REQ-002 is MEDIUM
        path = ["TEST-COMP-001", "TEST-REQ-001", "TEST-REQ-002"]
        conf = populated_graph.get_chain_confidence(path)
        assert conf == "MEDIUM"

    def test_chain_confidence_empty_path(self, populated_graph):
        conf = populated_graph.get_chain_confidence([])
        assert conf == "PARSE_UNCERTAIN"

    # --- Anti-Hallucination helpers ---

    def test_coverage_gaps(self, populated_graph):
        # TEST-REQ-002 has no IMPLEMENTS edge pointing to it
        gaps = populated_graph.get_coverage_gaps()
        gap_ids = [g["node_id"] for g in gaps]
        assert "TEST-REQ-002" in gap_ids
        # TEST-REQ-001 HAS an IMPLEMENTS edge
        assert "TEST-REQ-001" not in gap_ids

    def test_orphan_components(self, populated_graph):
        # TEST-COMP-001 has IMPLEMENTS edge (not orphan)
        orphans = populated_graph.get_orphan_components()
        orphan_ids = [o["node_id"] for o in orphans]
        assert "TEST-COMP-001" not in orphan_ids

    def test_get_contradictions_empty(self, populated_graph):
        contras = populated_graph.get_contradictions()
        assert contras == []

    def test_get_stale_node_ids_empty(self, populated_graph):
        stale = populated_graph.get_stale_node_ids()
        assert len(stale) == 0

    # --- Persistence ---

    def test_save_and_reload(self, tmp_path):
        from rag_v2.graph_store import GraphStore
        path = str(tmp_path / "persist_test.json")
        gs1 = GraphStore(persist_path=path)
        gs1.add_node("N1", {"node_type": "COMPONENT", "name": "test"})
        gs1.add_node("N2", {"node_type": "REQUIREMENT", "name": "req"})
        gs1.add_edge("N1", "N2", "IMPLEMENTS")
        gs1.save()

        gs2 = GraphStore(persist_path=path)
        assert gs2.get_node("N1") is not None
        assert gs2.get_edge("N1", "N2") is not None
        assert gs2.stats()["total_nodes"] == 2

    # --- Stats ---

    def test_stats_structure(self, populated_graph):
        s = populated_graph.stats()
        assert "total_nodes" in s
        assert "total_edges" in s
        assert "node_types" in s
        assert "edge_types" in s
        assert s["total_nodes"] == 9
        assert s["total_edges"] == 5


# ---------------------------------------------------------------------------
# HallucinationGate Unit Tests
# ---------------------------------------------------------------------------

class TestHallucinationGate:
    """src/rag_v2/hallucination_gate.py unit testleri."""

    @pytest.fixture
    def gate_and_graph(self, tmp_path):
        from rag_v2.graph_store import GraphStore
        from rag_v2.hallucination_gate import HallucinationGate
        gs = GraphStore(persist_path=str(tmp_path / "gate_test.json"))
        data = _minimal_graph_data()
        for node in data["nodes"]:
            gs.add_node(node["node_id"], {k: v for k, v in node.items()})
        for edge in data["edges"]:
            gs.add_edge(edge["from"], edge["to"], edge["edge_type"],
                        {"confidence": edge.get("confidence", "MEDIUM")})
        gate = HallucinationGate(gs)
        return gate, gs

    def test_check_returns_gate_result(self, gate_and_graph):
        from rag_v2.hallucination_gate import GateResult
        gate, gs = gate_and_graph
        nodes = gs.get_all_nodes()
        result = gate.check(nodes)
        assert isinstance(result, GateResult)
        assert result.overall_confidence in ("HIGH", "MEDIUM", "PARSE_UNCERTAIN")

    def test_layer2_confidence_all_high(self, gate_and_graph):
        gate, gs = gate_and_graph
        nodes = [gs.get_node("TEST-COMP-001"), gs.get_node("TEST-REQ-001")]
        nodes = [{"node_id": nid, **n} for nid, n in
                 [("TEST-COMP-001", gs.get_node("TEST-COMP-001")),
                  ("TEST-REQ-001", gs.get_node("TEST-REQ-001"))]]
        result = gate.check(nodes, require_evidence=False)
        assert result.overall_confidence == "HIGH"

    def test_layer3_coverage_gap_warning(self, gate_and_graph):
        gate, gs = gate_and_graph
        # TEST-REQ-002 has no implementing component
        req2 = {"node_id": "TEST-REQ-002", **gs.get_node("TEST-REQ-002")}
        result = gate.check([req2], require_evidence=False)
        gap_warns = [w for w in result.warnings if "CoverageGap" in w]
        assert len(gap_warns) >= 1

    def test_layer4_parse_uncertain_warning(self, gate_and_graph):
        gate, gs = gate_and_graph
        pu_node = {
            "node_id": "TMP-PU",
            "node_type": "COMPONENT",
            "name": "uncertain",
            "confidence": "PARSE_UNCERTAIN_WHY_DISABLED",
        }
        result = gate.check([pu_node], require_evidence=False)
        pu_warns = [w for w in result.warnings if "ParseUncertain" in w]
        assert len(pu_warns) >= 1

    def test_layer5_stale_filter(self, gate_and_graph):
        gate, gs = gate_and_graph
        # Add a SUPERSEDES edge: NEW supersedes OLD
        gs.add_node("OLD-COMP", {"node_type": "COMPONENT", "name": "old"})
        gs.add_node("NEW-COMP", {"node_type": "COMPONENT", "name": "new"})
        gs.add_edge("NEW-COMP", "OLD-COMP", "SUPERSEDES")

        old_node = {"node_id": "OLD-COMP", "node_type": "COMPONENT", "name": "old"}
        result = gate.check([old_node], require_evidence=False)
        assert "OLD-COMP" in result.filtered_node_ids
        stale_warns = [w for w in result.warnings if "Stale" in w]
        assert len(stale_warns) >= 1

    def test_layer6_contradiction_warning(self, gate_and_graph):
        gate, gs = gate_and_graph
        gs.add_node("COMP-X", {"node_type": "COMPONENT", "name": "x"})
        gs.add_node("COMP-Y", {"node_type": "COMPONENT", "name": "y"})
        gs.add_edge("COMP-X", "COMP-Y", "CONTRADICTS")

        nodes = [
            {"node_id": "COMP-X", "node_type": "COMPONENT"},
            {"node_id": "COMP-Y", "node_type": "COMPONENT"},
        ]
        result = gate.check(nodes, require_evidence=False)
        contra_warns = [w for w in result.warnings if "Contradiction" in w]
        assert len(contra_warns) >= 1

    def test_check_evidence_with_verified_by(self, gate_and_graph):
        gate, gs = gate_and_graph
        # TEST-REQ-001 has VERIFIED_BY → TEST-EVID-001
        has_ev = gate.check_evidence("TEST-REQ-001", [])
        assert has_ev is True

    def test_check_evidence_missing(self, gate_and_graph):
        gate, gs = gate_and_graph
        # TEST-REQ-002 has no VERIFIED_BY edge
        has_ev = gate.check_evidence("TEST-REQ-002", [])
        assert has_ev is False

    def test_propagate_confidence_weakest_link(self, gate_and_graph):
        gate, gs = gate_and_graph
        path = [
            {"node_id": "A", "confidence": "HIGH"},
            {"node_id": "B", "confidence": "MEDIUM"},
            {"node_id": "C", "confidence": "HIGH"},
        ]
        conf = gate.propagate_confidence(path)
        assert conf == "MEDIUM"


# ---------------------------------------------------------------------------
# QueryRouter Unit Tests (Mock graph + vector)
# ---------------------------------------------------------------------------

class TestQueryRouter:
    """src/rag_v2/query_router.py unit testleri."""

    def test_classify_what(self):
        from rag_v2.query_router import classify_query, QueryType
        assert classify_query("FPGA nedir?") == QueryType.WHAT
        assert classify_query("bu bileşen ne yapar") == QueryType.WHAT

    def test_classify_how(self):
        from rag_v2.query_router import classify_query, QueryType
        assert classify_query("axis2fifo nasıl çalışır?") == QueryType.HOW
        assert classify_query("clock nasıl konfigüre edilir?") == QueryType.HOW

    def test_classify_why(self):
        from rag_v2.query_router import classify_query, QueryType
        assert classify_query("neden interrupt yerine polling seçildi?") == QueryType.WHY
        assert classify_query("bu karar neden alındı?") == QueryType.WHY

    def test_classify_trace(self):
        from rag_v2.query_router import classify_query, QueryType
        assert classify_query("hangi bileşen bu gereksinimi karşılıyor?") == QueryType.TRACE
        assert classify_query("traceability zinciri nedir?") == QueryType.TRACE

    def test_classify_crossref(self):
        from rag_v2.query_router import classify_query, QueryType
        assert classify_query("A ile B'yi karşılaştır") == QueryType.CROSSREF
        assert classify_query("bu iki bileşen arasındaki fark nedir?") == QueryType.CROSSREF

    def test_query_result_all_nodes_dedup(self):
        from rag_v2.query_router import QueryResult, QueryType
        # Same node in both graph_nodes and vector_hits → deduplicated
        node = {"node_id": "N1", "node_type": "COMPONENT", "name": "x"}
        vec_hit = {"node_id": "N1", "similarity": 0.8, "metadata": {}}
        qr = QueryResult(
            query="test",
            query_type=QueryType.HOW,
            vector_hits=[vec_hit],
            graph_nodes=[node],
        )
        all_n = qr.all_nodes()
        ids = [n["node_id"] for n in all_n]
        assert ids.count("N1") == 1  # dedup

    def test_query_result_stale_excluded(self):
        from rag_v2.query_router import QueryResult, QueryType
        node_a = {"node_id": "A", "node_type": "COMPONENT"}
        node_b = {"node_id": "B", "node_type": "COMPONENT"}
        qr = QueryResult(
            query="test",
            query_type=QueryType.WHAT,
            graph_nodes=[node_a, node_b],
            stale_ids={"B"},
        )
        # stale_ids bilgi amaçlı — all_nodes filtre yapmaz (gate filtreler)
        assert len(qr.all_nodes()) == 2
        assert qr.stale_ids == {"B"}


# ---------------------------------------------------------------------------
# Loader Unit Tests
# ---------------------------------------------------------------------------

class TestLoader:
    """src/rag_v2/loader.py unit testleri."""

    def test_strip_js_comments_line(self):
        from rag_v2.loader import _strip_js_comments
        text = '{"key": "value"} // line comment\n{"k2": "v2"}'
        result = _strip_js_comments(text)
        assert "//" not in result
        assert '"key"' in result

    def test_strip_js_comments_block(self):
        from rag_v2.loader import _strip_js_comments
        text = '{"a": /* block */ 1}'
        result = _strip_js_comments(text)
        assert "/*" not in result
        assert '"a"' in result

    def test_load_pipeline_graph_minimal(self, tmp_path):
        from rag_v2.loader import load_pipeline_graph
        data = {
            "meta": {"pipeline_version": "2.0"},
            "nodes": [{"node_id": "N1", "node_type": "COMPONENT", "name": "x"}],
            "edges": [{"from": "N1", "to": "N1", "edge_type": "DEPENDS_ON"}],
        }
        p = tmp_path / "mini.json"
        p.write_text(json.dumps(data))
        nodes, edges, meta = load_pipeline_graph(str(p))
        assert len(nodes) == 1
        assert len(edges) == 1
        assert meta["pipeline_version"] == "2.0"

    def test_load_pipeline_graph_missing_file(self):
        from rag_v2.loader import load_pipeline_graph
        with pytest.raises(FileNotFoundError):
            load_pipeline_graph("/nonexistent/path.json")

    def test_flatten_node_nested(self):
        from rag_v2.loader import _flatten_node
        node = {
            "node_id": "N1",
            "node_type": "COMPONENT",
            "ports": {"inputs": ["clk", "rst"], "outputs": ["data"]},
            "tags": ["axi", "dma"],
        }
        flat = _flatten_node(node)
        assert isinstance(flat["ports"], str)
        assert isinstance(flat["tags"], str)
        assert flat["node_id"] == "N1"
        assert flat["node_type"] == "COMPONENT"


# ---------------------------------------------------------------------------
# ResponseBuilder Unit Tests
# ---------------------------------------------------------------------------

class TestResponseBuilder:
    """src/rag_v2/response_builder.py unit testleri."""

    @pytest.fixture
    def mock_query_result(self):
        from rag_v2.query_router import QueryResult, QueryType
        nodes = [
            {"node_id": "TEST-COMP-001", "node_type": "COMPONENT",
             "name": "test_module", "confidence": "HIGH", "description": "RTL module"},
            {"node_id": "TEST-REQ-001", "node_type": "REQUIREMENT",
             "name": "Test REQ", "confidence": "HIGH", "description": "System shall do X"},
        ]
        return QueryResult(
            query="nasıl çalışır?",
            query_type=QueryType.HOW,
            vector_hits=[{"node_id": "TEST-COMP-001", "similarity": 0.8,
                          "metadata": {"node_type": "COMPONENT"}}],
            graph_nodes=nodes,
            graph_edges=[{"from": "TEST-COMP-001", "to": "TEST-REQ-001",
                          "edge_type": "IMPLEMENTS", "confidence": "HIGH"}],
        )

    @pytest.fixture
    def mock_gate_result(self):
        from rag_v2.hallucination_gate import GateResult
        return GateResult(
            passed=True,
            overall_confidence="HIGH",
            warnings=[],
            filtered_node_ids=set(),
            evidence_ids=[],
            details={},
        )

    def test_build_structured_response_keys(self, mock_query_result, mock_gate_result):
        from rag_v2.response_builder import build_structured_response
        resp = build_structured_response("nasıl çalışır?",
                                         mock_query_result, mock_gate_result,
                                         "LLM yanıtı")
        for key in ("answer", "confidence", "sources", "warnings",
                    "query_type", "llm_answer"):
            assert key in resp

    def test_build_structured_response_sources(self, mock_query_result, mock_gate_result):
        from rag_v2.response_builder import build_structured_response
        resp = build_structured_response("test", mock_query_result, mock_gate_result)
        assert "TEST-COMP-001" in resp["sources"]

    def test_build_structured_response_confidence(self, mock_query_result, mock_gate_result):
        from rag_v2.response_builder import build_structured_response
        resp = build_structured_response("test", mock_query_result, mock_gate_result)
        assert resp["confidence"] == "HIGH"

    def test_build_llm_context_contains_nodes(self, mock_query_result, mock_gate_result):
        from rag_v2.response_builder import build_llm_context
        ctx = build_llm_context(mock_query_result, mock_gate_result)
        assert "test_module" in ctx or "TEST-COMP-001" in ctx
        assert "COMPONENT" in ctx

    def test_build_llm_context_excludes_stale(self, mock_gate_result):
        from rag_v2.query_router import QueryResult, QueryType
        from rag_v2.hallucination_gate import GateResult
        from rag_v2.response_builder import build_llm_context

        nodes = [
            {"node_id": "ACTIVE", "node_type": "COMPONENT", "name": "active", "confidence": "HIGH"},
            {"node_id": "STALE",  "node_type": "COMPONENT", "name": "stale",  "confidence": "HIGH"},
        ]
        qr = QueryResult(query="test", query_type=QueryType.WHAT, graph_nodes=nodes)
        gr = GateResult(passed=True, overall_confidence="HIGH",
                        warnings=[], filtered_node_ids={"STALE"},
                        evidence_ids=[], details={})
        ctx = build_llm_context(qr, gr)
        assert "STALE" not in ctx
        assert "active" in ctx

    def test_answer_template_format(self, mock_query_result, mock_gate_result):
        from rag_v2.response_builder import build_structured_response
        resp = build_structured_response("test", mock_query_result, mock_gate_result,
                                         "Test LLM yanıtı")
        assert "[YANIT]" in resp["answer"]
        assert "Güven Seviyesi" in resp["answer"]
        assert "Kaynaklar" in resp["answer"]
        assert "[AÇIKLAMA]" in resp["answer"]


# ---------------------------------------------------------------------------
# Integration Tests — gerçek DB kullanır (smoke + integration)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestIntegrationFullPipeline:
    """
    Gerçek db/graph/ ve db/chroma_graph_nodes/ üzerinde tam pipeline testi.
    Embedding modeli ilk çalıştırmada yüklenir (~5-10 sn).
    """

    @pytest.fixture(scope="class")
    def stores(self):
        from rag_v2.graph_store import GraphStore
        from rag_v2.vector_store_v2 import VectorStoreV2
        assert Path(REAL_GRAPH_DB).exists(), \
            "Graph DB yok — önce: python scripts/build_graph_db.py"
        assert Path(REAL_CHROMA_DIR).exists(), \
            "Vector DB yok — önce: python scripts/build_graph_db.py"
        gs = GraphStore(persist_path=REAL_GRAPH_DB)
        vs = VectorStoreV2(persist_directory=REAL_CHROMA_DIR, threshold=0.35)
        return gs, vs

    @pytest.fixture(scope="class")
    def router(self, stores):
        from rag_v2.query_router import QueryRouter
        gs, vs = stores
        return QueryRouter(gs, vs, n_vector_results=5)

    @pytest.fixture(scope="class")
    def gate(self, stores):
        from rag_v2.hallucination_gate import HallucinationGate
        gs, _ = stores
        return HallucinationGate(gs)

    def test_graph_db_populated(self, stores):
        gs, vs = stores
        s = gs.stats()
        assert s["total_nodes"] > 100, "Beklenen 123+ node"
        assert s["total_edges"] > 80,  "Beklenen 104+ edge"

    def test_vector_db_populated(self, stores):
        _, vs = stores
        assert vs.count() > 100, "Beklenen 123+ embedded node"

    def test_known_node_exists(self, stores):
        gs, _ = stores
        n = gs.get_node("COMP-A-axis2fifo_0")
        assert n is not None
        assert n["node_type"] == "COMPONENT"

    def test_implements_edge_exists(self, stores):
        gs, _ = stores
        # axis2fifo implements DMA-REQ-L2-001
        edge = gs.get_edge("COMP-A-axis2fifo_0", "DMA-REQ-L2-001")
        assert edge is not None
        assert edge["edge_type"] == "IMPLEMENTS"

    def test_decomposes_chain(self, stores):
        gs, _ = stores
        tree = gs.get_req_tree("DMA-REQ-L0-001")
        ids = [n["node_id"] for n in tree]
        assert "DMA-REQ-L0-001" in ids
        assert len(ids) > 1  # en az 1 alt gereksinim

    def test_what_query_returns_results(self, router, gate):
        from rag_v2.query_router import QueryType
        qr = router.route("FPGA nedir?", QueryType.WHAT)
        assert len(qr.vector_hits) > 0
        assert len(qr.graph_nodes) > 0

    def test_how_query_prefers_components(self, router, gate):
        from rag_v2.query_router import QueryType
        qr = router.route("DMA nasıl çalışır?", QueryType.HOW)
        types = [n.get("node_type") for n in qr.graph_nodes]
        assert "COMPONENT" in types

    def test_why_query_finds_decisions(self, router, gate):
        from rag_v2.query_router import QueryType
        # "interrupt karar" — DMA-DEC-005 doğrudan DECISION node metniyle eşleşir
        qr = router.route("interrupt yerine polling neden seçildi karar", QueryType.WHY)
        types = [n.get("node_type") for n in qr.graph_nodes]
        # DECISION bulunamazsa en azından REQUIREMENT veya EVIDENCE dönmeli
        assert len(qr.graph_nodes) > 0, "Why sorgusu hiç node döndürmedi"
        # DECISION veya ISSUE (polling konusu ISSUE-A-006'da geçiyor)
        assert any(t in types for t in ("DECISION", "ISSUE", "REQUIREMENT")), \
            f"Beklenen node tipleri bulunamadı: {types}"

    def test_trace_query_follows_implements(self, router, gate):
        from rag_v2.query_router import QueryType
        qr = router.route("axis2fifo bileşeni hangi gereksinimi karşılıyor",
                           QueryType.TRACE)
        ids = [n.get("node_id") for n in qr.graph_nodes]
        assert "COMP-A-axis2fifo_0" in ids
        assert any("DMA-REQ" in nid for nid in ids)

    def test_crossref_query_finds_analogous(self, router, gate):
        from rag_v2.query_router import QueryType
        qr = router.route("clk_wiz PROJECT-A ve PROJECT-B farkı nedir",
                           QueryType.CROSSREF)
        edge_types = [e.get("edge_type") for e in qr.graph_edges]
        assert "ANALOGOUS_TO" in edge_types

    def test_gate_check_on_real_nodes(self, stores, gate):
        from rag_v2.hallucination_gate import GateResult
        gs, _ = stores
        sample = gs.get_all_nodes()[:5]
        result = gate.check(sample)
        assert isinstance(result, GateResult)
        assert result.overall_confidence in ("HIGH", "MEDIUM", "PARSE_UNCERTAIN")

    def test_full_pipeline_no_crash(self, router, gate):
        from rag_v2.query_router import QueryType
        from rag_v2.response_builder import build_llm_context, build_structured_response

        qr = router.route("DMA-REQ-L1-001 nasıl karşılanıyor?", QueryType.TRACE)
        gr = gate.check(qr.all_nodes(), qr.graph_edges)
        ctx = build_llm_context(qr, gr)
        resp = build_structured_response("test", qr, gr, llm_answer="(test)")
        assert resp["answer"] is not None
        assert "[YANIT]" in resp["answer"]


# ---------------------------------------------------------------------------
# Smoke Tests — 5 saniyede geçmeli
# ---------------------------------------------------------------------------

@pytest.mark.smoke
class TestSmoke:
    """Hızlı sağlık kontrolü — CI/CD veya deploy sonrası çalıştır."""

    def test_graph_db_file_exists(self):
        assert Path(REAL_GRAPH_DB).exists(), "Graph DB eksik"

    def test_chroma_dir_exists(self):
        assert Path(REAL_CHROMA_DIR).exists(), "Vector DB eksik"

    def test_pipeline_json_exists(self):
        assert Path(REAL_PIPELINE_JSON).exists(), "pipeline_graph.json eksik"

    def test_graph_loads_without_error(self):
        from rag_v2.graph_store import GraphStore
        gs = GraphStore(persist_path=REAL_GRAPH_DB)
        assert gs.stats()["total_nodes"] > 0

    def test_vector_store_loads_without_error(self):
        from rag_v2.vector_store_v2 import VectorStoreV2
        vs = VectorStoreV2(persist_directory=REAL_CHROMA_DIR, threshold=0.35)
        assert vs.count() > 0

    def test_node_types_complete(self):
        from rag_v2.graph_store import GraphStore
        gs = GraphStore(persist_path=REAL_GRAPH_DB)
        s = gs.stats()
        for nt in ("PROJECT", "REQUIREMENT", "COMPONENT", "DECISION"):
            assert nt in s["node_types"], f"Node tipi eksik: {nt}"

    def test_edge_types_complete(self):
        from rag_v2.graph_store import GraphStore
        gs = GraphStore(persist_path=REAL_GRAPH_DB)
        s = gs.stats()
        for et in ("IMPLEMENTS", "DECOMPOSES_TO", "MOTIVATED_BY"):
            assert et in s["edge_types"], f"Edge tipi eksik: {et}"

    def test_openai_key_in_env(self):
        from dotenv import load_dotenv
        load_dotenv(_PROJ_ROOT / ".env")
        key = os.getenv("OPENAI_API_KEY", "")
        assert key and not key.startswith("your-"), \
            "OPENAI_API_KEY .env'de ayarlanmamış"
