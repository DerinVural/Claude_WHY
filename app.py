#!/usr/bin/env python3
"""
GCP-RAG-VIVADO Streamlit Chat Interface
"""

import sys
import os
import time
from pathlib import Path

# Project root
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

import streamlit as st

# ============================================================================
# PAGE CONFIG
# ============================================================================
st.set_page_config(
    page_title="GCP-RAG-VIVADO",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# CUSTOM CSS
# ============================================================================
st.markdown("""
<style>
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        color: #1E3A5F;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 1rem;
        color: #666;
        margin-top: 0;
    }
    .stat-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .stat-number {
        font-size: 1.8rem;
        font-weight: 700;
    }
    .stat-label {
        font-size: 0.8rem;
        opacity: 0.9;
    }
    .source-box {
        background: #f8f9fa;
        border-left: 4px solid #667eea;
        padding: 0.8rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
        font-size: 0.85rem;
    }
    .similarity-high { color: #28a745; font-weight: 700; }
    .similarity-mid { color: #ffc107; font-weight: 700; }
    .similarity-low { color: #dc3545; font-weight: 700; }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# INITIALIZE RAG SYSTEM (cached)
# ============================================================================
@st.cache_resource(show_spinner="RAG sistemi yukleniyor...")
def load_rag_system():
    from src.rag.sentence_embeddings import SentenceEmbeddings
    from src.rag.gemini_generator import GeminiGenerator
    from src.vectorstore.chroma_store import ChromaVectorStore

    vs = ChromaVectorStore(
        persist_directory=str(project_root / "chroma_db"),
        collection_name="documents",
    )
    emb = SentenceEmbeddings()
    gen = GeminiGenerator()

    # Warm up embedding model
    emb.embed_text("warmup")

    return vs, emb, gen, vs.get_document_count()


def is_turkish(text: str) -> bool:
    turkish_chars = set("ğüşıöçĞÜŞİÖÇ")
    turkish_words = {"nedir", "nasıl", "için", "ile", "bir", "olan", "hangi",
                     "yapılır", "oluştur", "kullan", "ayarla", "konfigüre", "neden"}
    has_char = any(c in turkish_chars for c in text)
    has_word = any(w in text.lower().split() for w in turkish_words)
    return has_char or has_word


def translate_to_english(generator, text: str) -> str:
    try:
        model = generator._get_model()
        response = model.generate_content(
            f"Translate this FPGA/electronics question to English. "
            f"Keep all technical terms. Only output the translation, nothing else.\n\n{text}",
            generation_config={"temperature": 0.0, "max_output_tokens": 256},
        )
        return response.text.strip()
    except Exception:
        return text


# ============================================================================
# SIDEBAR
# ============================================================================
with st.sidebar:
    st.markdown("### Ayarlar")
    top_k = st.slider("Kaynak sayisi (Top-K)", 1, 15, 5)
    auto_translate = st.checkbox("Turkce sorulari otomatik cevir", value=True)
    show_sources = st.checkbox("Kaynaklari goster", value=True)
    show_content = st.checkbox("Kaynak icerigini goster", value=False)

    st.markdown("---")
    st.markdown("### Ornek Sorular")

    example_questions = [
        "Zynq-7000 Processing System nedir?",
        "Vivado'da timing closure nasil yapilir?",
        "AXI DMA transfer configuration",
        "Versal ACAP NoC architecture",
        "VHDL entity architecture process",
        "Vitis HLS pragma pipeline unroll",
        "7 Series MMCM PLL clock management",
        "PYNQ overlay bitstream Python",
    ]

    for eq in example_questions:
        if st.button(eq, key=f"ex_{eq}", use_container_width=True):
            st.session_state["pending_question"] = eq

    st.markdown("---")
    st.markdown("### Sistem Bilgisi")


# ============================================================================
# MAIN AREA
# ============================================================================
st.markdown('<p class="main-header">GCP-RAG-VIVADO</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">FPGA & Vivado Dokumantasyon Asistani | 3.8M+ chunk | GPU Accelerated</p>', unsafe_allow_html=True)
st.markdown("---")

# Load system
vs, emb, gen, doc_count = load_rag_system()

# Stats row
with st.sidebar:
    st.metric("Dokuman Sayisi", f"{doc_count:,}")
    st.metric("Kategori", "31")
    st.metric("Embedding Model", "all-mpnet-base-v2")
    st.metric("LLM", "Gemini 2.0 Flash")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and "sources" in msg:
            if show_sources:
                with st.expander(f"Kaynaklar ({len(msg['sources'])} sonuc)"):
                    for i, src in enumerate(msg["sources"], 1):
                        sim = src["similarity"]
                        sim_class = "high" if sim >= 0.7 else "mid" if sim >= 0.5 else "low"
                        fname = src["metadata"].get("filename", "?")
                        ftype = src["metadata"].get("type", "?")
                        lang = src["metadata"].get("language", "")
                        lang_str = f" | {lang}" if lang else ""

                        st.markdown(
                            f'<div class="source-box">'
                            f'<b>#{i}</b> {fname} '
                            f'<span class="similarity-{sim_class}">{sim:.1%}</span>'
                            f' | {ftype}{lang_str}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                        if show_content:
                            st.code(src["content"][:500], language=None)

# Handle pending question from sidebar
if "pending_question" in st.session_state:
    pending = st.session_state.pop("pending_question")
    st.session_state["chat_input_value"] = pending
    st.rerun()

# Chat input
prompt = st.chat_input("FPGA, Vivado, Zynq hakkinda bir soru sorun...")

# Check for pre-filled input
if "chat_input_value" in st.session_state:
    prompt = st.session_state.pop("chat_input_value")

if prompt:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process
    with st.chat_message("assistant"):
        with st.status("Dusunuyor...", expanded=True) as status:
            # Step 1: Translation
            search_query = prompt
            if auto_translate and is_turkish(prompt):
                st.write("Turkce algilandi, cevriliyor...")
                search_query = translate_to_english(gen, prompt)
                st.write(f"Arama sorgusu: *{search_query}*")

            # Step 2: Embedding
            st.write("Sorgu vektorlestiriliyor...")
            t0 = time.time()
            query_embedding = emb.embed_text(search_query)
            embed_time = (time.time() - t0) * 1000

            # Step 3: Retrieval
            st.write(f"ChromaDB'de arama yapiliyor (top-{top_k})...")
            t0 = time.time()
            results = vs.query(query_embedding, n_results=top_k)
            search_time = (time.time() - t0) * 1000

            # Format retrieved docs
            retrieved_docs = []
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                retrieved_docs.append({
                    "content": doc,
                    "metadata": meta,
                    "similarity": 1.0 - dist,
                })

            avg_sim = sum(d["similarity"] for d in retrieved_docs) / len(retrieved_docs)
            st.write(f"Bulundu: {len(retrieved_docs)} kaynak (ort. benzerlik: {avg_sim:.1%})")

            # Step 4: Generation
            st.write("Gemini ile yanit olusturuluyor...")
            t0 = time.time()
            try:
                answer = gen.generate(prompt, retrieved_docs)
                gen_time = (time.time() - t0) * 1000
                status.update(
                    label=f"Tamamlandi ({embed_time:.0f}ms embed + {search_time:.0f}ms arama + {gen_time:.0f}ms yanit)",
                    state="complete",
                )
            except Exception as e:
                answer = f"Gemini API hatasi: {e}\n\nKaynaklar bulundu ancak yanit olusturulamadi."
                gen_time = 0
                status.update(label="Yanit olusturulamadi (API hatasi)", state="error")

        # Display answer
        st.markdown(answer)

        # Sources
        if show_sources:
            with st.expander(f"Kaynaklar ({len(retrieved_docs)} sonuc)"):
                for i, src in enumerate(retrieved_docs, 1):
                    sim = src["similarity"]
                    sim_class = "high" if sim >= 0.7 else "mid" if sim >= 0.5 else "low"
                    fname = src["metadata"].get("filename", "?")
                    ftype = src["metadata"].get("type", "?")
                    lang = src["metadata"].get("language", "")
                    lang_str = f" | {lang}" if lang else ""

                    st.markdown(
                        f'<div class="source-box">'
                        f'<b>#{i}</b> {fname} '
                        f'<span class="similarity-{sim_class}">{sim:.1%}</span>'
                        f' | {ftype}{lang_str}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    if show_content:
                        st.code(src["content"][:500], language=None)

    # Save to history
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": retrieved_docs,
    })
