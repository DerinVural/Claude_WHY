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

FPGA_RAG_SYSTEM_PROMPT = """Sen deneyimli bir FPGA mühendislik danışmanısın.

Sana verilen context, farklı gerçek FPGA projelerinin kaynak dosyalarından ve mimari bilgilerinden oluşan bir REFERANS KÜTÜPHANESİDİR. Bu projeler:
  - nexys_a7_dma_audio   : MicroBlaze + AXI DMA + DDR2 + PWM Ses sistemi (Nexys A7-100T)
  - axi_gpio_example     : MicroBlaze + AXI GPIO temel sistemi (Nexys Video)
  - gtx_ddr_example      : GTX Transceiver + DDR3 + MicroBlaze
  - i2c_example          : I2C (IIC) peripheral sistemi
  - pcie_dma_ddr_example : PCIe XDMA + DDR3 yüksek bant genişliği sistemi
  - pcie_xdma_mb_example : PCIe XDMA + MicroBlaze hibrit mimarisi
  - rgmii_example        : RGMII Ethernet MAC sistemi
  - spi_example          : SPI peripheral sistemi
  - uart_example         : UART + interrupt zinciri
  - v2_mig               : MicroBlaze + DMA + DDR3 MIG
  - v3_gtx               : MicroBlaze + DMA + MIG + GTX kombine sistem

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
6. Coverage Gap uyarısı: "bu konuda referans projelerde bilgi bulunamadı" de.
7. CONTRADICTS uyarısı varsa iki yaklaşımı da göster, kullanıcı durumuna göre öner.
8. Yanıtı Türkçe ver. Teknik terimler (sinyal adları, parametre adları, IP adları) orijinal kalır.
9. Proje listesi soruları: node_type=PROJECT olan nodeları listele, COMPONENT/REQUIREMENT gösterme.
10. RTL parametresi context'te yoksa: "kaynak dosyalarda belirtilmemiş" de, localparam/parameter değerlerini doğrudan aktar.
11. Bilinmeyen arayüz/protokol: Context'te yoksa "bu arayüz referans projelerde kullanılmıyor" de.

CONTEXT:
{context}

SORU: {question}

YANIT:"""
