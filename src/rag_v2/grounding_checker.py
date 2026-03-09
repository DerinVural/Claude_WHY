"""
Grounding Checker — FPGA RAG v2
================================
LLM cevabındaki sayısal/teknik değerlerin gerçekten retrieval context'inde
(source chunks + graph node metadata) var olup olmadığını doğrular.

Eğer bir değer context'te bulunmuyorsa → UNGROUNDED_VALUE uyarısı.
Bu sayede LLM'in parametrik belleğinden ürettiği "uydurma" değerler
kullanıcıya işaretlenerek sunulur.

Kullanım:
    from rag_v2.grounding_checker import GroundingChecker
    checker = GroundingChecker()
    warnings = checker.check(llm_answer, source_chunks, graph_nodes)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Regex patterns — sayısal / teknik değer tespiti
# ---------------------------------------------------------------------------

# Sayısal teknik değerler: "32 bit", "8 KB", "4 stage" vb.
# NOT: mhz/khz/ghz/ns/us/ms KASITLI çıkarıldı — bu değerler genellikle
# hesaplanmış/türetilmiş (ör. 325 MHz = 650/2) ve kaynak dosyada birebir
# geçmeyebilir. Frekans/zaman doğrulaması yanlış pozitif üretir.
_VALUE_PATTERN = re.compile(
    r'\b(\d+(?:\.\d+)?)\s*'
    r'(?:bit|bits|kb|mb|gb|stage|stages|'
    r'word|words|byte|bytes|cycle|cycles|channel|channels|way|ways|'
    r'line|lines|entry|entries|tap|taps)\b',
    re.IGNORECASE,
)

# Özel sabit değerler: hex adresleri, Verilog parametreleri
_HEX_PATTERN    = re.compile(r'\b0x[0-9a-fA-F]{4,}\b')
_LOCALPARAM_VAL = re.compile(r'localparam\s+\w+\s*=\s*(\d+)', re.IGNORECASE)

# Teknik protokol isimleri — kaynak kodda geçmiyorsa bunları da işaretle
_PROTOCOL_PATTERN = re.compile(
    r'\b(i2s|spi(?!\s*nor)|uart|pcie|can\s*bus|i2c|mipi|hdmi|displayport|'
    r'thunderbolt|usb\s*3|ethernet\s*mac)\b',
    re.IGNORECASE,
)

# Bunlar genellikle meşru referanslardır — false positive bastır
_COMMON_BENIGN = {
    "32 bit",  "64 bit",  "16 bit",   "8 bit",  "1 bit",   "2 bit",
    "1 kb",    "2 kb",    "4 kb",
    "50 mhz",  "100 mhz", "200 mhz",
    "1 cycle", "2 cycle",
}


class GroundingChecker:
    """
    LLM cevabındaki teknik değerlerin context'te gerçekten var olup
    olmadığını denetler.
    """

    def check(
        self,
        answer: str,
        source_chunks: List[Dict[str, Any]],
        graph_nodes: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Returns list of UNGROUNDED_VALUE warning strings.
        Empty list → all values grounded (or no values found).
        """
        if not answer:
            return []

        # Build context corpus from chunks + node metadata
        corpus = self._build_corpus(source_chunks, graph_nodes)

        warnings: List[str] = []
        answer_lower = answer.lower()

        # ── Numeric technical values ───────────────────────────────────────
        for match in _VALUE_PATTERN.finditer(answer_lower):
            val_str = match.group(0).strip()
            if val_str in _COMMON_BENIGN:
                continue
            if not self._value_in_corpus(val_str, match.group(1), corpus):
                warnings.append(
                    f"[GroundingChecker] UNGROUNDED_VALUE '{val_str}' — "
                    f"bu değer context kaynak dosyalarında bulunamadı. "
                    f"LLM parametrik bilgisinden üretilmiş olabilir."
                )

        # ── Hex addresses ──────────────────────────────────────────────────
        for match in _HEX_PATTERN.finditer(answer_lower):
            hex_val = match.group(0)
            if hex_val not in corpus:
                warnings.append(
                    f"[GroundingChecker] UNGROUNDED_ADDRESS '{hex_val}' — "
                    f"bu adres context'te doğrulanamadı."
                )

        # ── Unknown protocols ─────────────────────────────────────────────
        for match in _PROTOCOL_PATTERN.finditer(answer_lower):
            protocol = match.group(1).strip()
            if protocol not in corpus:
                warnings.append(
                    f"[GroundingChecker] UNGROUNDED_PROTOCOL '{protocol}' — "
                    f"bu arayüz/protokol context kaynak dosyalarında geçmiyor."
                )

        # Deduplicate
        seen: set = set()
        unique: List[str] = []
        for w in warnings:
            key = w[:60]
            if key not in seen:
                seen.add(key)
                unique.append(w)

        return unique

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_corpus(
        self,
        source_chunks: List[Dict[str, Any]],
        graph_nodes: List[Dict[str, Any]],
    ) -> str:
        """Build a single lowercase string from all context material."""
        parts: List[str] = []

        # Source chunk content
        for chunk in source_chunks:
            parts.append(chunk.get("content", ""))

        # Graph node fields that contain technical values
        for node in graph_nodes:
            for field in ("description", "key_logic", "acceptance_criteria",
                          "summary", "rationale", "name"):
                val = node.get(field, "")
                if val:
                    parts.append(str(val))

        return " ".join(parts).lower()

    def _value_in_corpus(
        self, val_str: str, number: str, corpus: str
    ) -> bool:
        """
        Check if the value string or just the number appears in corpus.
        Allows for minor formatting differences (e.g. "32bit" vs "32 bit").
        """
        # Exact string match
        if val_str in corpus:
            return True
        # Number without unit (avoids false negatives for "32 bit" vs "32-bit")
        # Only accept if number is >= 3 digits or appears as standalone word
        if len(number) >= 2 and re.search(r'\b' + re.escape(number) + r'\b', corpus):
            return True
        # Compact form (no space): "32bit", "8kb"
        compact = val_str.replace(" ", "")
        if compact in corpus:
            return True
        return False
