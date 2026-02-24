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

    # Collect all relevant nodes, filtered by stale
    all_nodes = query_result.all_nodes()
    active_nodes = [n for n in all_nodes
                    if n.get("node_id", "") not in gate_result.filtered_node_ids]

    # Sort: PROJECT nodes first (they provide essential context), then by type priority
    # Architecture §3: PROJECT nodes are root context — must appear before requirements
    type_priority = {
        "PROJECT": 0, "DECISION": 1, "REQUIREMENT": 2, "COMPONENT": 3,
        "EVIDENCE": 4, "CONSTRAINT": 5, "PATTERN": 6,
        "ISSUE": 7, "SOURCE_DOC": 8,
    }
    active_nodes.sort(key=lambda n: type_priority.get(n.get("node_type", ""), 9))

    # Trim to max_nodes
    active_nodes = active_nodes[:max_nodes]

    # Format nodes
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
            # key_logic may be JSON string from loader
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

    # ── 4. Store: Source Code Snippets ──────────────────────────────────────
    # Kaynak dosya chunk'larını ekle — implementasyon detayları burada
    # Graph metadata yanıt veremiyorsa gerçek kod gösterilir
    if hasattr(query_result, "source_chunks") and query_result.source_chunks:
        lines.append("=" * 60)
        lines.append("=== KAYNAK DOSYA İÇERİKLERİ ===")
        lines.append("(Aşağıdaki kod/konfigürasyon gerçek proje dosyalarından alınmıştır)")
        lines.append("")

        # Benzerlik skoruna göre sırala
        chunks = sorted(
            query_result.source_chunks,
            key=lambda c: c.get("similarity", 0),
            reverse=True,
        )

        # Bütçe: max_chars'ın ~%60'ı kaynak kodlara ayrılır (küçük XDC/RTL dosyaların kaybolmaması için)
        remaining = max(2000, int(max_chars * 0.60))
        for chunk in chunks[:10]:  # en fazla 10 chunk
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
                # "data/code/..." veya "validation_test/..." kısalt
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

            # İçeriği kırp (remaining bütçe dahilinde)
            content_trimmed = content[:min(len(content), remaining - len(header) - 4)]
            lines.append(content_trimmed)
            lines.append("")

            remaining -= len(content_trimmed) + len(header) + 4
            if remaining <= 200:
                lines.append("[... daha fazla kaynak chunk mevcut ama bütçe aşıldı ...]")
                break

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

FPGA_RAG_SYSTEM_PROMPT = """Sen bir FPGA mühendislik asistanısın. Sana verilen context FPGA RAG v2 sisteminden alınmış yapılandırılmış bilgilerdir.

KURALAR:
1. Yalnızca verilen context içindeki bilgileri kullan — asla tahmin üretme.
2. KAYNAK DOSYA İÇERİKLERİ bölümü gerçek proje dosyalarından alınmıştır — bu değerleri doğrudan kullan (IOSTANDARD, adresler, parametreler vb.).
3. Graph metadata (node'lar) mimari bağlamı, kaynak dosyalar ise implementasyon detayını verir. İkisini birleştir.
4. Her iddia için kaynak belirt: node_id veya dosya adı + satır numarası.
5. Güven seviyesi PARSE_UNCERTAIN olan bilgileri "belirsiz" olarak işaretle.
6. Coverage Gap uyarısı varsa "bu konuda sistemde bilgi bulunamadı" de — ama KAYNAK DOSYA bölümünde ilgili kod varsa onu kullan.
7. CONTRADICTS uyarısı varsa her iki görüşü de sun, tercih etme.
8. Yanıtı Türkçe ver. Teknik terimleri (sinyal adları, parametre adları) orijinal haliyle bırak.
9. KRİTİK — Proje listesi soruları: "projeler", "kaç proje", "hangi projeler", "sistemdeki projeler" gibi sorularda YALNIZCA node_type=PROJECT olan nodeları listele. REQUIREMENT, COMPONENT veya başka tipteki nodeları proje olarak GÖSTERME.

CONTEXT:
{context}

SORU: {question}

YANIT:"""
