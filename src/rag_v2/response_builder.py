"""
Response Builder — FPGA RAG v2
Architecture ref: fpga_rag_architecture_v2.md §7 Layer 5 (Structured Response)

Mandatory response template:
  [YANIT]
    Güven Seviyesi: HIGH | MEDIUM | PARSE_UNCERTAIN_WHY_...
    Kaynaklar: [node_id, edge_id, ...]
    Uyarılar: [Coverage Gap, PARSE_UNCERTAIN, CONTRADICTS, ...]
    [LLM Açıklama]

Also provides context packaging for Gemini LLM calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJ_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJ_ROOT / "src"))

from rag_v2.query_router import QueryResult, QueryType
from rag_v2.hallucination_gate import GateResult


# ---------------------------------------------------------------------------
# Context builder (for LLM prompt)
# ---------------------------------------------------------------------------

def build_llm_context(
    query_result: QueryResult,
    gate_result: GateResult,
    max_nodes: int = 10,
    max_chars: int = 8000,
) -> str:
    """
    Build a structured context string for the LLM from query + gate results.
    Excludes stale nodes. Prioritizes by query type.
    """
    lines: List[str] = []
    lines.append(f"=== FPGA RAG v2 Context ===")
    lines.append(f"Query Type : {query_result.query_type.value}")
    lines.append(f"Confidence : {gate_result.overall_confidence}")
    lines.append("")

    # ── 1. ÖNCE: Source Code Snippets (Ground Truth) ─────────────────────────
    # Kaynak dosya chunk'ları ÖNCE gelir — implementasyon ground truth'u burada.
    # LLM parametre değerleri için her zaman bu bölümü referans alır.
    if hasattr(query_result, "source_chunks") and query_result.source_chunks:
        lines.append("=" * 60)
        lines.append("=== KAYNAK DOSYA İÇERİKLERİ (GROUND TRUTH) ===")
        lines.append("(Gerçek proje dosyalarından alınmıştır. Parametre değerleri için bu bölüm önceliklidir.)")
        lines.append("")

        # Benzerlik skoruna göre sırala
        chunks = sorted(
            query_result.source_chunks,
            key=lambda c: c.get("similarity", 0),
            reverse=True,
        )

        # Bütçe: max_chars'ın ~%60'ı kaynak kodlara ayrılır
        remaining = max(2000, int(max_chars * 0.60))
        for chunk in chunks[:20]:  # en fazla 20 chunk
            file_path = chunk.get("file_path", "")
            chunk_label = chunk.get("chunk_label", "")
            start_line = chunk.get("start_line", 0)
            end_line = chunk.get("end_line", 0)
            similarity = chunk.get("similarity", 0)
            content = chunk.get("content", "")

            # Dosya adını kısalt (tam yol yerine proje-göreli)
            try:
                from pathlib import Path as _P
                fp = _P(file_path)
                for marker in ("data/code/", "validation_test/", "src/"):
                    s = str(fp)
                    idx = s.find(marker)
                    if idx >= 0:
                        file_path = s[idx:]
                        break
                else:
                    file_path = fp.name
            except Exception:
                pass

            header = (f"--- [{chunk.get('file_type','').upper()}] "
                      f"{file_path}:{start_line}-{end_line} "
                      f"({chunk_label}) sim={similarity:.2f} ---")
            lines.append(header)

            content_trimmed = content[:min(len(content), remaining - len(header) - 4)]
            lines.append(content_trimmed)
            lines.append("")

            remaining -= len(content_trimmed) + len(header) + 4
            if remaining <= 200:
                lines.append("[... daha fazla kaynak chunk mevcut ama bütçe aşıldı ...]")
                break

        lines.append("=" * 60)
        lines.append("")

    # ── 1b. Xilinx UG Döküman Chunk'ları (5. store) ──────────────────────────
    # Proje kaynak kodundan sonra gelir — referans bilgi, ground truth değil.
    # LLM için: "Proje kaynak kodu ile çelişirse kaynak kodu tercih et."
    if hasattr(query_result, "doc_chunks") and query_result.doc_chunks:
        lines.append("=" * 60)
        lines.append("=== XİLİNX REFERANS DÖKÜMANLAR (UG/XAPP) ===")
        lines.append("(Genel Vivado/Vitis referansı. Proje kaynak koduyla çelişirse kaynak kodu tercih et.)")
        lines.append("")

        # G3: Ayrı garantili bütçe — source chunk yarışmasından bağımsız
        doc_budget = max(2000, int(max_chars * 0.25))
        for dc in query_result.doc_chunks[:6]:
            doc_title = dc.get("doc_title", dc.get("doc_id", ""))
            section = dc.get("section", "")
            page_num = dc.get("page_num", 0)
            sim = dc.get("similarity", 0)
            content = dc.get("content", "")

            page_str = f"s.{page_num}" if page_num else ""
            header = f"--- [{doc_title}] {section} {page_str} sim={sim:.2f} ---"
            lines.append(header)
            content_trimmed = content[:min(len(content), doc_budget - len(header) - 4)]
            lines.append(content_trimmed)
            lines.append("")

            doc_budget -= len(content_trimmed) + len(header) + 4
            if doc_budget <= 200:
                break

        lines.append("=" * 60)
        lines.append("")

    # ── 2. SONRA: Graph Nodes (Mimari Bağlam / Topoloji) ─────────────────────
    # Graph node'ları mimari bağlamı ve bileşen ilişkilerini verir.
    # Parametre değerleri için KAYNAK DOSYA bölümünü kullan, graph'ı değil.

    # Collect all relevant nodes, filtered by stale
    all_nodes = query_result.all_nodes()
    active_nodes = [n for n in all_nodes
                    if n.get("node_id", "") not in gate_result.filtered_node_ids]

    # Sort: PROJECT nodes first, then by type priority
    type_priority = {
        "PROJECT": 0, "DECISION": 1, "REQUIREMENT": 2, "COMPONENT": 3,
        "EVIDENCE": 4, "CONSTRAINT": 5, "PATTERN": 6,
        "ISSUE": 7, "SOURCE_DOC": 8,
    }
    active_nodes.sort(key=lambda n: type_priority.get(n.get("node_type", ""), 9))
    active_nodes = active_nodes[:max_nodes]

    if active_nodes:
        lines.append("=== MİMARİ BAĞLAM (Graph Metadata — Topoloji & İlişkiler) ===")
        lines.append("")

    for node in active_nodes:
        nid = node.get("node_id", "?")
        ntype = node.get("node_type", "?")
        name = node.get("name", nid)
        conf = node.get("confidence", "?")
        desc = node.get("description", "")
        key_logic = node.get("key_logic", "")
        rationale = node.get("rationale", "")
        acceptance = node.get("acceptance_criteria", "")
        summary = node.get("summary", "")

        lines.append(f"--- [{ntype}] {nid} ---")
        lines.append(f"Name      : {name}")
        lines.append(f"Confidence: {conf}")
        if desc:
            lines.append(f"Desc      : {desc}")
        if key_logic:
            try:
                kl = json.loads(key_logic) if isinstance(key_logic, str) and key_logic.startswith("[") else key_logic
                if isinstance(kl, list):
                    lines.append(f"Key Logic :")
                    for item in kl:
                        lines.append(f"  - {item}")
                else:
                    lines.append(f"Key Logic : {kl}")
            except Exception:
                lines.append(f"Key Logic : {key_logic}")
        if rationale:
            lines.append(f"Rationale : {rationale}")
        if acceptance:
            lines.append(f"Acceptance: {acceptance}")
        if summary:
            lines.append(f"Summary   : {summary}")
        lines.append("")

    # Format relevant edges
    if query_result.graph_edges:
        lines.append("--- Edges ---")
        for edge in query_result.graph_edges[:15]:
            etype = edge.get("edge_type", "?")
            from_id = edge.get("from", "?")
            to_id = edge.get("to", "?")
            econf = edge.get("confidence", "")
            lines.append(f"  {from_id} --[{etype}]--> {to_id}"
                         + (f" ({econf})" if econf else ""))
        lines.append("")

    # Req tree context
    if query_result.req_tree:
        lines.append("--- Requirement Tree ---")
        for rn in query_result.req_tree[:8]:
            rid = rn.get("node_id", "?")
            rdesc = rn.get("description", "")
            lines.append(f"  {rid}: {rdesc[:100]}")
        lines.append("")

    # Warnings (from gate)
    if gate_result.warnings:
        lines.append("--- Uyarılar ---")
        for w in gate_result.warnings:
            lines.append(f"  {w}")
        lines.append("")

    context = "\n".join(lines)

    # Trim to max_chars
    if len(context) > max_chars:
        context = context[:max_chars] + "\n[... context truncated ...]"

    return context


# ---------------------------------------------------------------------------
# Structured Response
# ---------------------------------------------------------------------------

def build_structured_response(
    query: str,
    query_result: QueryResult,
    gate_result: GateResult,
    llm_answer: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Architecture §7 Layer 5 — mandatory structured response.

    Returns dict with:
      answer         : str (full formatted response)
      confidence     : str
      sources        : List[str] (node_ids)
      warnings       : List[str]
      query_type     : str
      llm_answer     : str (raw LLM output)
    """
    # Source node IDs (active only)
    source_ids = [
        n.get("node_id", "")
        for n in query_result.all_nodes()
        if n.get("node_id", "") not in gate_result.filtered_node_ids
    ]

    # Build formatted answer block
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("[YANIT]")
    lines.append(f"  Sorgu Tipi   : {query_result.query_type.value}")
    lines.append(f"  Güven Seviyesi: {gate_result.overall_confidence}")
    lines.append(f"  Kaynaklar    : {source_ids[:10]}")

    if gate_result.warnings:
        lines.append("  Uyarılar:")
        for w in gate_result.warnings:
            lines.append(f"    - {w}")
    else:
        lines.append("  Uyarılar     : Yok")

    lines.append("")

    if llm_answer:
        lines.append("[AÇIKLAMA]")
        lines.append(llm_answer)
    else:
        lines.append("[AÇIKLAMA]")
        lines.append("(LLM yanıtı üretilmedi — build_llm_context() ile context oluşturun)")

    lines.append("=" * 60)

    formatted = "\n".join(lines)

    return {
        "answer": formatted,
        "confidence": gate_result.overall_confidence,
        "sources": source_ids,
        "warnings": gate_result.warnings,
        "query_type": query_result.query_type.value,
        "llm_answer": llm_answer or "",
        "vector_hits": len(query_result.vector_hits),
        "graph_nodes": len(query_result.graph_nodes),
        "graph_edges": len(query_result.graph_edges),
        "stale_filtered": len(gate_result.filtered_node_ids),
    }


# ---------------------------------------------------------------------------
# System prompt for Gemini
# ---------------------------------------------------------------------------

_FPGA_RAG_SYSTEM_PROMPT_TEMPLATE = """Sen deneyimli bir FPGA mühendislik danışmanısın.

Sana verilen context, farklı gerçek FPGA projelerinin kaynak dosyalarından ve mimari bilgilerinden oluşan bir REFERANS KÜTÜPHANESİDİR. Bu projeler:
{project_list}

GÖREVIN:
Kullanıcı bir FPGA implementasyon sorusu sorduğunda:
  1. Context'teki referans projeler arasında konuyla ilgili implementasyonları bul
  2. Projeler farklı yaklaşım kullanıyorsa karşılaştır ve neden farklı olduğunu açıkla
  3. Kullanıcının durumuna en uygun yaklaşımı gerekçesiyle öner

ÇIKTI FORMATI (karşılaştırmalı sorgular için):
  [proje_adı] → parametre/yaklaşım/değer
  [proje_adı] → farklı parametre/yaklaşım/değer
  [Öneri] Durumuna göre X öneriyorum çünkü...

KURALLAR — DEĞİŞMEYEN:
1. Yalnızca context'teki somut değerleri kullan — asla tahmin üretme veya değer uydurma.
2. KAYNAK DOSYA İÇERİKLERİ bölümü ground truth'tur — parametre değerleri için önceliklidir.
3. ÖNCELİK: Kaynak dosyadaki değer > Graph metadata değeri. Çakışma varsa kaynak dosyayı kullan.
4. Her iddia için kaynak belirt: proje adı + dosya adı (ör. nexys_a7_dma_audio/design_1.tcl).
5. Bir parametre context'te yoksa "bu değer referans projelerde bulunmadı" de — uydurma.
6. Coverage Gap uyarısı graph düzeyinde eksiklik işaretidir. Kaynak dosya chunk'ında değer açıkça yazıyorsa Coverage Gap uyarısına rağmen değeri ver — kaynak dosya her zaman önceliklidir.
7. CONTRADICTS uyarısı varsa iki yaklaşımı da göster, kullanıcı durumuna göre öner.
8. Yanıtı Türkçe ver. Teknik terimler (sinyal adları, parametre adları, IP adları) orijinal kalır.
9. Proje listesi soruları: node_type=PROJECT olan nodeları listele, COMPONENT/REQUIREMENT gösterme.
10. localparam/parameter/define değerlerini kaynak dosyadan doğrudan aktar. Değer chunk'ta açıkça yazıyorsa ver.
11. Bilinmeyen arayüz/protokol: Context'te yoksa "bu arayüz referans projelerde kullanılmıyor" de.
12. IP bloğunun parametre değeri (örn. NUM_PORTS=5, C_NUM_CHANNELS=8, CONFIG.xx=yy) chunk'ta doğrudan yazıyorsa kesinlikle ver — "belirleyemiyorum" deme.

CONTEXT:
{context}

SORU: {question}

YANIT:"""

# Statik fallback — graph yüklenemezse kullanılır
_STATIC_PROJECT_LIST = (
    "  - nexys_a7_dma_audio   : MicroBlaze + AXI DMA + DDR2 + PWM Ses sistemi (Nexys A7-100T)\n"
    "  - axi_gpio_example     : MicroBlaze + AXI GPIO temel sistemi (Nexys Video)\n"
    "  - gtx_ddr_example      : GTX Transceiver + DDR3 + MicroBlaze (Nexys Video)\n"
    "  - hdmi_video_example   : AXI VDMA + DDR3 + Video Timing + MicroBlaze (Nexys Video)\n"
    "  - i2c_example          : I2C (IIC) peripheral sistemi (Nexys Video)\n"
    "  - pcie_dma_ddr_example : PCIe XDMA + DDR3 yüksek bant genişliği sistemi (Nexys Video)\n"
    "  - pcie_xdma_mb_example : PCIe XDMA + MicroBlaze hibrit mimarisi (Nexys Video)\n"
    "  - rgmii_example        : RGMII Ethernet MAC sistemi (Nexys Video)\n"
    "  - spi_example          : SPI peripheral sistemi (Nexys Video)\n"
    "  - uart_example         : UART + interrupt zinciri (Nexys Video)\n"
    "  - v2_mig               : MicroBlaze + DMA + DDR3 MIG (Nexys Video)\n"
    "  - v3_gtx               : MicroBlaze + DMA + MIG + GTX kombine sistem (Nexys Video)\n"
    "  - arty_s7_25_base_rt   : FreeRTOS gerçek zamanlı temel sistem, MicroBlaze + DDR3 MIG + XADC + SPI (Arty S7-25)"
)


def build_project_list_str(graph_store=None, source_chunk_store=None) -> str:
    """
    Tüm kaynaklardan dinamik proje listesi üret:
      1. GraphStore PROJECT node'ları: tam meta (board, description) ile
      2. SourceChunkStore projesi (grafta yoksa): chunk'lardan proje ID'si ile
      3. Statik fallback: graph_store=None veya boş grafta

    100+ proje için otomatik ölçeklenir — hardcoded liste güncellemeye gerek yok.
    """
    # ── Graftan PROJECT node'ları ────────────────────────────────────────────
    graph_projects: Dict[str, str] = {}   # node_id → formatted line
    if graph_store is not None:
        try:
            nodes = [n for n in graph_store.get_all_nodes() if n.get("node_type") == "PROJECT"]
            for n in sorted(nodes, key=lambda x: x.get("node_id", "")):
                nid   = n.get("node_id", "?")
                name  = n.get("name", "")
                board = n.get("board", "")
                desc  = n.get("description", "")
                summary = name if name else (desc[:60] if desc else nid)
                detail  = f" ({board})" if board else ""
                graph_projects[nid] = f"  - {nid:<25}: {summary}{detail}"
        except Exception:
            pass

    # ── SourceChunkStore projelerini ekle (grafta yoksa) ─────────────────────
    chunk_only_projects: list = []
    if source_chunk_store is not None:
        try:
            col = source_chunk_store._get_collection()
            data = col.get(include=["metadatas"])
            for m in (data.get("metadatas") or []):
                pid = m.get("project", "")
                if pid and pid not in graph_projects:
                    chunk_only_projects.append(pid)
        except Exception:
            pass

    if not graph_projects and not chunk_only_projects:
        return _STATIC_PROJECT_LIST

    lines = list(graph_projects.values())
    for pid in sorted(set(chunk_only_projects)):
        lines.append(f"  - {pid:<25}: (kaynak dosyalar indeksli)")
    return "\n".join(lines)


def build_system_prompt(context: str, question: str, graph_store=None) -> str:
    """
    Sistem promptunu dinamik proje listesiyle oluştur.
    graph_store verilirse PROJECT node'larından proje listesi çekilir.
    100+ proje eklendikçe prompt otomatik güncellenir.
    """
    project_list = build_project_list_str(graph_store)
    return _FPGA_RAG_SYSTEM_PROMPT_TEMPLATE.format(
        project_list=project_list,
        context=context,
        question=question,
    )


def build_system_prefix(graph_store=None, source_chunk_store=None) -> str:
    """
    LLM çağrıları için dinamik sistem prefix'i döner.
    app_v2.py ve test script'lerindeki `.split("CONTEXT:")[0].strip()` idiomunu
    graph_store + source_chunk_store destekli hale getirir.

    Kullanım (app_v2.py'de):
        from rag_v2.response_builder import build_system_prefix
        system = build_system_prefix(gs, source_chunk_store=sc)
    """
    project_list = build_project_list_str(graph_store, source_chunk_store)
    full = _FPGA_RAG_SYSTEM_PROMPT_TEMPLATE.format(
        project_list=project_list,
        context="",
        question="",
    )
    return full.split("CONTEXT:")[0].strip()


# Backward compat: eski kod FPGA_RAG_SYSTEM_PROMPT string'ini doğrudan format() ile kullanır.
# Yeni kod build_system_prompt() / build_system_prefix() kullanmalı; bu alias eski çağrıları bozmaz.
FPGA_RAG_SYSTEM_PROMPT = _FPGA_RAG_SYSTEM_PROMPT_TEMPLATE.format(
    project_list=_STATIC_PROJECT_LIST,
    context="{context}",
    question="{question}",
)
