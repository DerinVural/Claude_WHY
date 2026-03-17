#!/usr/bin/env python3
"""
FPGA RAG v2 — Streamlit Chat Interface
=======================================
Mimari: fpga_rag_architecture_v2.md
3-Store federated query: Vector + Graph + Req Tree
Anti-hallüsinasyon: 6 aktif katman
LLM: Claude Code CLI (claude-sonnet-4-6, API key gerektirmez)
"""

import os
import sys
import time
from pathlib import Path

# Proje kökü
_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

import streamlit as st

# ── Sayfa ayarları ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FPGA RAG v2",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Genel */
.block-container { padding-top: 1.5rem; }

/* Başlık */
.v2-header { font-size: 1.8rem; font-weight: 700; color: #1a3c6e; margin-bottom: 0; }
.v2-sub    { font-size: 0.9rem;  color: #666; margin-top: 0; }

/* Badge */
.badge {
    display: inline-block; padding: 2px 8px;
    border-radius: 12px; font-size: 0.72rem; font-weight: 600;
    margin-right: 4px; vertical-align: middle;
}
.badge-what    { background:#dbeafe; color:#1e40af; }
.badge-how     { background:#dcfce7; color:#166534; }
.badge-why     { background:#fef3c7; color:#92400e; }
.badge-trace   { background:#ede9fe; color:#5b21b6; }
.badge-crossref{ background:#fce7f3; color:#9d174d; }
.badge-auto    { background:#f1f5f9; color:#475569; }

/* Güven */
.conf-HIGH    { color:#16a34a; font-weight:700; }
.conf-MEDIUM  { color:#d97706; font-weight:700; }
.conf-PARSE   { color:#dc2626; font-weight:700; }

/* Node kartları */
.node-card {
    border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 10px 14px; margin: 6px 0;
    background: #fafafa; font-size: 0.83rem;
}
.node-card .ntype { font-size:0.7rem; font-weight:700; letter-spacing:.5px; }
.nc-COMPONENT  { border-left: 4px solid #3b82f6; }
.nc-REQUIREMENT{ border-left: 4px solid #10b981; }
.nc-DECISION   { border-left: 4px solid #f59e0b; }
.nc-EVIDENCE   { border-left: 4px solid #8b5cf6; }
.nc-PATTERN    { border-left: 4px solid #ec4899; }
.nc-ISSUE      { border-left: 4px solid #ef4444; }
.nc-CONSTRAINT { border-left: 4px solid #6b7280; }
.nc-PROJECT    { border-left: 4px solid #1e40af; }
.nc-SOURCE_DOC { border-left: 4px solid #0ea5e9; }

/* Uyarı kutusu */
.warn-box {
    background:#fef9c3; border-left:4px solid #eab308;
    padding:8px 12px; border-radius:0 6px 6px 0;
    font-size:0.8rem; margin:4px 0;
}
.edge-chip {
    display:inline-block; font-size:0.72rem;
    background:#f0f4ff; border:1px solid #c7d2fe;
    border-radius:4px; padding:1px 6px; margin:2px;
}
</style>
""", unsafe_allow_html=True)


# ── RAG v2 sistemi yükle (cached) ─────────────────────────────────────────────
@st.cache_resource(show_spinner="⚡ FPGA RAG v2 yükleniyor...")
def load_rag_v2():
    from rag_v2.graph_store import GraphStore
    from rag_v2.vector_store_v2 import VectorStoreV2
    from rag_v2.query_router import QueryRouter
    from rag_v2.hallucination_gate import HallucinationGate

    graph_path  = str(_ROOT / "db" / "graph" / "fpga_rag_v2_graph.json")
    chroma_path = str(_ROOT / "db" / "chroma_v2")

    if not Path(graph_path).exists():
        st.error("Graph DB bulunamadı. Önce: `python scripts/build_graph_db.py`")
        st.stop()

    gs = GraphStore(persist_path=graph_path)
    vs = VectorStoreV2(persist_directory=chroma_path, threshold=0.35)

    # ── 4. Store: Source Chunk Store (kaynak dosya içerikleri) ────────────────
    source_chunk_path = str(_ROOT / "db" / "chroma_source_chunks")
    sc = None
    if Path(source_chunk_path).exists():
        try:
            from rag_v2.source_chunk_store import SourceChunkStore
            sc = SourceChunkStore(persist_directory=source_chunk_path, threshold=0.25)
            chunk_count = sc.count()
            if chunk_count == 0:
                sc = None  # Boş store — bağlama
        except Exception as e:
            sc = None  # Graceful degradation

    # ── 5. Store: DocStore (Xilinx UG/XAPP dökümanları) ──────────────────────
    doc_store_path = str(_ROOT / "db" / "chroma_docs")
    ds = None
    if Path(doc_store_path).exists():
        try:
            from rag_v2.doc_store import DocStore
            ds = DocStore(persist_dir="db/chroma_docs")
            if ds.count() == 0:
                ds = None  # Boş store — bağlama
        except Exception:
            ds = None  # Graceful degradation

    router = QueryRouter(gs, vs, source_chunk_store=sc, doc_store=ds,
                         n_vector_results=6, n_source_results=16)
    gate = HallucinationGate(gs)

    stats = gs.stats()
    stats["source_chunks"] = sc.count() if sc else 0
    stats["doc_chunks"] = ds.count() if ds else 0

    # Embedding model pre-warm: ilk sorgu bekleme süresini azalt.
    # FTS5 disk-persistent olduğundan cold-start yok (sadece embedding modeli yüklenir).
    import threading
    def _warmup():
        try:
            if sc:
                sc.search("vivado clock constraint", n_results=1)
            if ds:
                ds.search("vivado timing constraint", n_results=1)
        except Exception:
            pass
    threading.Thread(target=_warmup, daemon=True).start()

    return gs, vs, router, gate, stats, sc


def get_llm(model_name: str):
    from rag.llm_factory import get_llm as _get_llm
    return _get_llm(model_name)


# ── Yardımcı render fonksiyonları ─────────────────────────────────────────────

_TYPE_BADGE = {
    "What": "badge-what", "How": "badge-how", "Why": "badge-why",
    "Trace": "badge-trace", "CrossRef": "badge-crossref", "AUTO": "badge-auto",
}
_TYPE_EMOJI = {
    "What": "🔍", "How": "⚙️", "Why": "💡", "Trace": "🔗",
    "CrossRef": "↔️", "AUTO": "🤖",
}
_CONF_CLASS = {
    "HIGH": "conf-HIGH", "MEDIUM": "conf-MEDIUM",
}


def render_node_card(node: dict):
    nid   = node.get("node_id", "?")
    ntype = node.get("node_type", "?")
    name  = node.get("name", node.get("title", nid))
    desc  = node.get("description", "")
    conf  = node.get("confidence", "")
    kl    = node.get("key_logic", "")
    rat   = node.get("rationale", "")

    # Güven rengi
    conf_cls = _CONF_CLASS.get(conf.split("_")[0] if conf else "", "conf-PARSE")
    short_desc = (desc[:130] + "…") if len(desc) > 130 else desc
    kl_str = ""
    if kl:
        import json as _j
        try:
            items = _j.loads(kl) if kl.startswith("[") else [kl]
            kl_str = "".join(f"<br>• {i}" for i in items[:3])
        except Exception:
            kl_str = f"<br>• {kl[:100]}"

    st.markdown(f"""
    <div class="node-card nc-{ntype}">
        <span class="ntype">{ntype}</span>
        <span style="margin-left:8px;font-weight:600">{name}</span>
        <span style="float:right;font-size:0.72rem" class="{conf_cls}">{conf}</span>
        <div style="color:#475569;margin-top:4px">{short_desc}</div>
        {f'<div style="color:#64748b;font-size:0.78rem">{kl_str}</div>' if kl_str else ''}
        {f'<div style="color:#7c3aed;font-size:0.78rem;margin-top:2px">Rationale: {rat[:100]}</div>' if rat else ''}
        <div style="font-size:0.68rem;color:#94a3b8;margin-top:4px">{nid}</div>
    </div>
    """, unsafe_allow_html=True)


def render_edge_row(edge: dict):
    etype  = edge.get("edge_type", "?")
    from_n = edge.get("from", "?")
    to_n   = edge.get("to", "?")
    conf   = edge.get("confidence", "")
    st.markdown(
        f'`{from_n}` '
        f'<span class="edge-chip">{etype}</span>'
        f' → `{to_n}` '
        f'<small style="color:#94a3b8">{conf}</small>',
        unsafe_allow_html=True,
    )


def render_warning(w: str):
    # Layer etiketi kısalt
    short = w.replace("[Layer1-EvidenceGate]", "⚠ Kanıt")\
              .replace("[Layer3-CoverageGap]", "⬜ Coverage Gap")\
              .replace("[Layer4-ParseUncertain]", "❓ PARSE_UNCERTAIN")\
              .replace("[Layer5-Stale]", "🗑 Stale")\
              .replace("[Layer6-Contradiction]", "⚡ Çelişki")
    st.markdown(f'<div class="warn-box">{short}</div>', unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Ayarlar")

    llm_model = st.selectbox(
        "LLM Modeli",
        [
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            "claude-opus-4-6",
        ],
        index=0,
    )
    query_type_override = st.selectbox(
        "Sorgu Tipi",
        ["Otomatik", "What", "How", "Why", "Trace", "CrossRef"],
        index=0,
    )
    n_results = st.slider("Sonuç sayısı", 3, 10, 5)
    show_nodes    = st.checkbox("Graph node'larını göster", value=True)
    show_edges    = st.checkbox("Edge'leri göster", value=True)
    show_warnings = st.checkbox("Anti-hallüsinasyon uyarıları", value=True)
    show_req_tree = st.checkbox("Requirement tree", value=False)

    st.markdown("---")
    st.markdown("### 💬 Örnek Sorular")

    examples = [
        ("🔍 What",    "Nexys A7 DMA Audio projesi nedir?"),
        ("⚙️ How",     "AXI DMA bileşeni nasıl çalışır?"),
        ("💡 Why",     "Neden interrupt yerine polling kullanıldı?"),
        ("🔗 Trace",   "DMA-REQ-L1-001 hangi bileşen tarafından karşılanıyor?"),
        ("↔️ Cross",   "İki projedeki clk_wiz bileşenlerinin farkı nedir?"),
        ("🔗 Trace",   "axis2fifo hangi gereksinimi implement ediyor?"),
        ("💡 Why",     "MIG 7-series DDR2 kontrolcüsü neden seçildi?"),
        ("⚙️ How",     "AXI GPIO wrapper nasıl bağlanıyor?"),
        ("🔍 What",    "axi_gpio_example projesindeki AXI bus mimarisi nedir?"),
        ("⬜ Gap",     "DMA-REQ-L0-001 hangi bileşen karşılıyor?"),
    ]

    for badge, q in examples:
        if st.button(f"{badge} — {q[:40]}", key=f"ex_{q}", use_container_width=True):
            st.session_state["pending_q"] = q

    st.markdown("---")
    st.markdown("### 📊 DB İstatistikleri")


# ── Ana alan ─────────────────────────────────────────────────────────────────
st.markdown('<p class="v2-header">⚡ FPGA RAG v2</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="v2-sub">Graph + Vector + Req Tree federated sorgu · '
    '6 katman anti-hallüsinasyon · OpenAI GPT</p>',
    unsafe_allow_html=True,
)
st.markdown("---")

# Sistemi yükle
gs, vs, router, gate, db_stats, sc = load_rag_v2()

# Sidebar stats
with st.sidebar:
    st.metric("Graph Nodes", db_stats["total_nodes"])
    st.metric("Graph Edges", db_stats["total_edges"])
    st.metric("Vector Docs", vs.count())
    st.metric("Source Chunks", db_stats.get("source_chunks", 0))
    st.metric("Doc Chunks (UG)", db_stats.get("doc_chunks", 0))
    st.metric("Eşik", "0.35 / 0.25")

    gaps = gs.get_coverage_gaps()
    orphans = gs.get_orphan_components()
    if gaps:
        st.warning(f"{len(gaps)} Coverage Gap")
    if orphans:
        st.info(f"{len(orphans)} Orphan Component")

# Sohbet geçmişi
if "messages_v2" not in st.session_state:
    st.session_state.messages_v2 = []

# Geçmişi göster
for msg in st.session_state.messages_v2:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

        if msg["role"] == "assistant" and "meta" in msg:
            meta = msg["meta"]
            qtype = meta.get("query_type", "?")
            badge_cls = _TYPE_BADGE.get(qtype, "badge-auto")
            emoji = _TYPE_EMOJI.get(qtype, "🔍")
            conf = meta.get("confidence", "?")
            conf_cls = _CONF_CLASS.get(conf.split("_")[0] if conf else "", "conf-PARSE")

            st.markdown(
                f'<span class="badge {badge_cls}">{emoji} {qtype}</span>'
                f'<span class="badge" style="background:#f1f5f9;color:#334155">Güven: '
                f'<span class="{conf_cls}">{conf}</span></span>'
                f'<span class="badge" style="background:#f1f5f9;color:#334155">'
                f'⏱ {meta.get("elapsed","?")}s</span>',
                unsafe_allow_html=True,
            )

            # Graph nodes
            if show_nodes and meta.get("nodes"):
                with st.expander(f"📦 Graph Nodes ({len(meta['nodes'])})"):
                    for n in meta["nodes"][:8]:
                        render_node_card(n)

            # Edges
            if show_edges and meta.get("edges"):
                with st.expander(f"🔗 Edges ({len(meta['edges'])})"):
                    for e in meta["edges"][:10]:
                        render_edge_row(e)

            # Req Tree
            if show_req_tree and meta.get("req_tree"):
                with st.expander(f"🌲 Requirement Tree ({len(meta['req_tree'])})"):
                    for r in meta["req_tree"][:10]:
                        rid = r.get("node_id", "?")
                        rdesc = r.get("description", "")
                        st.markdown(f"- `{rid}` — {rdesc[:80]}")

            # Source Chunks
            if meta.get("source_chunks"):
                with st.expander(f"📄 Kaynak Dosya Chunk'ları ({len(meta['source_chunks'])})"):
                    for ch in meta["source_chunks"][:5]:
                        fp = ch.get("file_path", "")
                        label = ch.get("chunk_label", "")
                        sim = ch.get("similarity", 0)
                        content = ch.get("content", "")
                        st.markdown(f"`{fp}` — **{label}** (sim={sim:.2f})")
                        st.code(content[:500], language="verilog")

            # Uyarılar
            if show_warnings and meta.get("warnings"):
                with st.expander(f"⚠️ Uyarılar ({len(meta['warnings'])})"):
                    for w in meta["warnings"][:10]:
                        render_warning(w)

# ── Örnek soru pending ────────────────────────────────────────────────────────
if "pending_q" in st.session_state:
    pending = st.session_state.pop("pending_q")
    # Direkt işleme gönder
    st.session_state["auto_prompt"] = pending
    st.rerun()

# ── Chat input ────────────────────────────────────────────────────────────────
prompt = st.chat_input("FPGA, Vivado, AXI, DMA hakkında bir soru sorun…")

# Otomatik prompt (örnek butondan)
if "auto_prompt" in st.session_state:
    prompt = st.session_state.pop("auto_prompt")

if prompt:
    # Kullanıcı mesajı
    st.session_state.messages_v2.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        # Sorgu tipi
        from rag_v2.query_router import QueryType
        qt_map = {"What": QueryType.WHAT, "How": QueryType.HOW,
                  "Why": QueryType.WHY, "Trace": QueryType.TRACE,
                  "CrossRef": QueryType.CROSSREF}
        qt = qt_map.get(query_type_override) if query_type_override != "Otomatik" else None

        # Router
        router._vector = vs  # n_results güncelle
        router.n_vector = n_results

        with st.status("Sorgu yönlendiriliyor…", expanded=True) as status:
            t0 = time.time()

            # Sınıfla
            detected_qt = qt or router.classify(prompt)
            emoji = _TYPE_EMOJI.get(detected_qt.value, "🔍")
            st.write(f"{emoji} Sorgu tipi: **{detected_qt.value}**")

            # Route
            n_stores = "5" if router.doc_store else ("4" if router.source_store else "3")
            st.write(f"📡 {n_stores} store paralel sorgulanıyor…")
            qr = router.route(prompt, detected_qt)
            doc_count = len(getattr(qr, "doc_chunks", []))
            st.write(
                f"Bulundu → vector: {len(qr.vector_hits)} · "
                f"graph: {len(qr.graph_nodes)} · "
                f"edges: {len(qr.graph_edges)} · "
                f"req_tree: {len(qr.req_tree)} · "
                f"source_chunks: {len(qr.source_chunks)} · "
                f"doc_chunks: {doc_count}"
            )

            # Gate
            st.write("🛡 Anti-hallüsinasyon gate kontrol ediliyor…")
            all_nodes = qr.all_nodes()
            gr = gate.check(all_nodes, qr.graph_edges)
            conf_cls = _CONF_CLASS.get(
                gr.overall_confidence.split("_")[0] if gr.overall_confidence else "",
                "conf-PARSE"
            )
            st.write(
                f"Güven: <span class='{conf_cls}'>{gr.overall_confidence}</span> · "
                f"Uyarı: {len(gr.warnings)} · "
                f"Stale: {len(gr.filtered_node_ids)}",
                unsafe_allow_html=True,
            )

            # LLM
            st.write("🤖 LLM yanıt üretiyor…")
            from rag_v2.response_builder import build_llm_context, build_system_prefix
            ctx = build_llm_context(qr, gr, max_nodes=15, max_chars=22000)

            # Dinamik sistem prefix: graph PROJECT node'ları + source chunk projeleri birleştirilir.
            # Yeni proje eklenince otomatik güncellenir — kod değişikliği gerekmez.
            system = build_system_prefix(gs, source_chunk_store=sc)

            llm = get_llm(llm_model)
            llm_answer = None
            if llm:
                try:
                    llm_answer = llm.generate(
                        query=prompt,
                        context_documents=[ctx],
                        system_prompt=system,
                        temperature=0.3,
                    )
                except Exception as e:
                    llm_answer = f"⚠️ LLM hatası: {e}"
            else:
                llm_answer = (
                    "⚠️ **LLM başlatılamadı.**\n\n"
                    "Claude Code CLI kurulu ve giriş yapılmış olmalı.\n\n"
                    "`claude --version` komutuyla kontrol edin."
                )

            # Grounding check — LLM cevabındaki değerleri context'e karşı doğrula
            if llm_answer and not llm_answer.startswith("⚠️"):
                from rag_v2.grounding_checker import GroundingChecker
                sc_chunks = getattr(qr, "source_chunks", [])
                grounding_warns = GroundingChecker().check(llm_answer, sc_chunks, qr.graph_nodes)
                if grounding_warns:
                    gr.warnings.extend(grounding_warns)

            elapsed = round(time.time() - t0, 1)
            status.update(label=f"✅ Tamamlandı ({elapsed}s)", state="complete")

        # Yanıtı göster
        st.markdown(llm_answer)

        # Metadata badge satırı
        qtype_val = detected_qt.value
        badge_cls = _TYPE_BADGE.get(qtype_val, "badge-auto")
        st.markdown(
            f'<span class="badge {badge_cls}">{emoji} {qtype_val}</span>'
            f'<span class="badge" style="background:#f1f5f9;color:#334155">Güven: '
            f'<span class="{conf_cls}">{gr.overall_confidence}</span></span>'
            f'<span class="badge" style="background:#f1f5f9;color:#334155">⏱ {elapsed}s</span>',
            unsafe_allow_html=True,
        )

        # Graph nodes
        if show_nodes and all_nodes:
            active = [n for n in all_nodes
                      if n.get("node_id", "") not in gr.filtered_node_ids]
            with st.expander(f"📦 Graph Nodes ({len(active)})", expanded=False):
                for n in active[:8]:
                    render_node_card(n)

        # Edges
        if show_edges and qr.graph_edges:
            with st.expander(f"🔗 Edges ({len(qr.graph_edges)})", expanded=False):
                for e in qr.graph_edges[:10]:
                    render_edge_row(e)

        # Req Tree
        if show_req_tree and qr.req_tree:
            with st.expander(f"🌲 Requirement Tree ({len(qr.req_tree)})", expanded=False):
                for r in qr.req_tree[:10]:
                    rid = r.get("node_id", "?")
                    rdesc = r.get("description", "")
                    st.markdown(f"- `{rid}` — {rdesc[:80]}")

        # Source Chunks (4. store)
        if qr.source_chunks:
            with st.expander(f"📄 Kaynak Dosya Chunk'ları ({len(qr.source_chunks)})",
                             expanded=False):
                for ch in qr.source_chunks[:8]:
                    fp = ch.get("file_path", "")
                    label = ch.get("chunk_label", "")
                    sim = ch.get("similarity", 0)
                    rrf = ch.get("rrf_score", 0)
                    content = ch.get("content", "")
                    ftype = ch.get("file_type", "text")
                    score_str = f"rrf={rrf:.4f}" if rrf else f"sim={sim:.2f}"
                    fname = fp.split('/')[-1]
                    icon = "📄" if ftype == "pdf" else "📝"
                    st.markdown(f"{icon} `{fname}` — **{label}** ({score_str})")
                    lang_map = {"verilog": "verilog", "c": "c", "xdc": "tcl",
                                "tcl": "tcl", "header": "c", "pdf": "text"}
                    st.code(content[:600], language=lang_map.get(ftype, "text"))

        # Doc Chunks (5. store — Xilinx UG)
        doc_chunks = getattr(qr, "doc_chunks", [])
        if doc_chunks:
            with st.expander(f"📚 UG Döküman Chunk'ları ({len(doc_chunks)})",
                             expanded=False):
                for dc in doc_chunks[:4]:
                    doc_title = dc.get("doc_title", dc.get("doc_id", ""))
                    section = dc.get("section", "")
                    sim = dc.get("similarity", 0)
                    page_num = dc.get("page_num", 0)
                    content = dc.get("content", "")
                    page_str = f" s.{page_num}" if page_num else ""
                    st.markdown(f"📚 **{dc.get('doc_id','?')}** — {section}{page_str} (sim={sim:.2f})")
                    st.caption(doc_title)
                    st.code(content[:500], language="text")

        # Uyarılar
        if show_warnings and gr.warnings:
            with st.expander(f"⚠️ Anti-Hallüsinasyon Uyarıları ({len(gr.warnings)})",
                             expanded=len(gr.warnings) <= 3):
                for w in gr.warnings[:10]:
                    render_warning(w)

        # Geçmişe kaydet
        st.session_state.messages_v2.append({
            "role": "assistant",
            "content": llm_answer,
            "meta": {
                "query_type": qtype_val,
                "confidence": gr.overall_confidence,
                "elapsed": elapsed,
                "nodes": all_nodes,
                "edges": qr.graph_edges,
                "req_tree": qr.req_tree,
                "source_chunks": qr.source_chunks,
                "warnings": gr.warnings,
            },
        })

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<small style='color:#94a3b8'>FPGA RAG v2.1 · "
    "GraphStore (NetworkX) + VectorStore + SourceChunkStore (ChromaDB) + OpenAI GPT · "
    "4-Store Federated Query · Anti-hallüsinasyon: Layer 1–6 aktif</small>",
    unsafe_allow_html=True,
)
