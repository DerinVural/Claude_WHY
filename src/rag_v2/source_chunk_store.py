"""
SourceChunkStore — FPGA RAG v2 — 4th Store
===========================================
Gerçek kaynak dosya içeriğini (RTL, C, XDC, TCL, BD/TCL) vektörize eder.

Graph node metadata → MİMARİ bilgi (kim, ne, neden)
Source chunks       → IMPLEMENTATION detayı (nasıl, hangi değer, hangi adres)

Dosya tipi başına akıllı chunklama:
  .v / .sv   → module sınırı (module ... endmodule)
  .vhd       → entity/architecture sınırı
  .c / .h    → fonksiyon sınırı + #define blokları
  .xdc       → tüm dosya (küçük dosyalar) veya pin gruplarına göre
  .tcl       → ADIM (step) bölümleri veya sabit boyutlu
  .bd/.json  → IP bloklarına göre (set_property -dict blokları)
  diğer      → sabit boyutlu, overlap'li pencereler

ChromaDB koleksiyonu: "source_chunks"
Persist dizini     : db/chroma_source_chunks/
"""

from __future__ import annotations

import os
import re
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_PROJ_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJ_ROOT / "src"))


# ─────────────────────────────────────────────────────────────────────────────
# Chunk dataclass
# ─────────────────────────────────────────────────────────────────────────────

class SourceChunk:
    __slots__ = ("chunk_id", "content", "file_path", "file_type",
                 "project", "start_line", "end_line", "chunk_label",
                 "related_node_ids")

    def __init__(
        self,
        chunk_id: str,
        content: str,
        file_path: str,
        file_type: str,
        project: str,
        start_line: int = 0,
        end_line: int = 0,
        chunk_label: str = "",
        related_node_ids: Optional[List[str]] = None,
    ):
        self.chunk_id = chunk_id
        self.content = content
        self.file_path = file_path
        self.file_type = file_type
        self.project = project
        self.start_line = start_line
        self.end_line = end_line
        self.chunk_label = chunk_label
        self.related_node_ids = related_node_ids or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "file_path": self.file_path,
            "file_type": self.file_type,
            "project": self.project,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "chunk_label": self.chunk_label,
            "related_node_ids": json.dumps(self.related_node_ids),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Chunker
# ─────────────────────────────────────────────────────────────────────────────

MAX_CHUNK_CHARS = 3000
OVERLAP_CHARS   = 300


class SourceFileChunker:
    """
    Dosya tipine göre içeriği anlamlı parçalara böler.
    Her chunk, bağımsız olarak semantic arama yapılabilecek kadar
    anlamlı bir birim olmalıdır.

    Index-time semantic enrichment: Her chunk'a dosya türüne göre
    okunabilir özet başlık eklenir. Bu sayede embedding modeli
    Türkçe/İngilizce doğal dil sorguları ile teknik sözdizimi arasındaki
    boşluğu kapatır — query-time augmentation'a gerek kalmaz.
    """

    # ---------------------------------------------------------------
    # Semantic summary generators — index time, no LLM, pure regex
    # ---------------------------------------------------------------

    @staticmethod
    def _xdc_pin_summary(content: str, file_name: str) -> str:
        """
        XDC içeriğinden pin atamalarını çıkar, okunabilir özet üret.
        Desteklenen formatlar:
          A) set_property -dict {PACKAGE_PIN X IOSTANDARD Y} [get_ports {sig}]
          B) set_property PACKAGE_PIN X [get_ports {sig}]   (ayrı satır)

        Yorum farkındalığı: aktif vs yorumlu (#) satır sayısı header'a eklenir.
        LLM yorumlu constraint'leri aktif olarak raporlamaz.
        """
        # ── Aktif vs yorumlu satır sayımı ─────────────────────────────
        active_constraints = 0
        commented_constraints = 0
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith('#') and 'set_property' in stripped.lower():
                commented_constraints += 1
            elif stripped.startswith('set_property') or stripped.startswith('create_clock'):
                active_constraints += 1

        entries: dict[str, tuple[str, str]] = {}

        # Format A — aktif satırlar: yorum satırı DEĞİL olanlar
        active_content = "\n".join(
            line for line in content.splitlines()
            if not line.strip().startswith('#')
        )

        re_a = re.compile(
            r'set_property\s+-dict\s+[{\[]\s*PACKAGE_PIN\s+(\w+)\s+IOSTANDARD\s+(\w+)\s*[}\]]\s*'
            r'\[get_ports\s+[{\[]?\s*([^\]\}]+?)\s*[}\]]?\]',
            re.IGNORECASE,
        )
        for m in re_a.finditer(active_content):
            entries[m.group(3).strip()] = (m.group(1), m.group(2))

        # Format B — iki ayrı set_property satırı (sadece aktif satırlardan)
        re_pin = re.compile(r'set_property\s+PACKAGE_PIN\s+(\w+)\s+\[get_ports\s+[{\[]?\s*([^\]\}]+?)\s*[}\]]?\]', re.IGNORECASE)
        re_std = re.compile(r'set_property\s+IOSTANDARD\s+(\w+)\s+\[get_ports\s+[{\[]?\s*([^\]\}]+?)\s*[}\]]?\]', re.IGNORECASE)
        pins: dict[str, str] = {m.group(2).strip(): m.group(1) for m in re_pin.finditer(active_content)}
        stds: dict[str, str] = {m.group(2).strip(): m.group(1) for m in re_std.finditer(active_content)}
        for sig, pin in pins.items():
            if sig not in entries:
                entries[sig] = (pin, stds.get(sig, ""))

        # Header: aktif/yorumlu bilgisi her zaman eklenir (pin yoksa bile)
        comment_note = ""
        if commented_constraints > 0:
            comment_note = (
                f"[NOT: Bu bölümde {active_constraints} aktif, "
                f"{commented_constraints} yorumlu (#) constraint var. "
                f"Yorumlu satırlar devre dışıdır — aktif constraint olarak raporlama.]\n"
            )

        if not entries and not comment_note:
            return ""

        if not entries:
            return f"[XDC — {file_name}]\n{comment_note}---\n"

        lines = [f"  {sig} -> {pin}" + (f" {std}" if std else "")
                 for sig, (pin, std) in sorted(entries.items())]
        header = f"[XDC Pin Assignments — {file_name}]\n"
        if comment_note:
            header += comment_note
        return header + "\n".join(lines) + "\n---\n"

    @staticmethod
    def _tcl_ip_summary(content: str, file_name: str) -> str:
        """
        TCL/BD-TCL chunk'ındaki IP örnekleri ve CONFIG parametrelerini özetle.
        create_bd_cell + set_property CONFIG bloklarını parse eder.
        """
        # VLNV ve IP adı
        vlnv_re = re.compile(r'create_bd_cell\s+-type\s+ip\s+-vlnv\s+(\S+)\s+(\w+)', re.IGNORECASE)
        # CONFIG parametreleri (hem -dict hem ayrı satır)
        cfg_re = re.compile(r'CONFIG\.(\w+)\s+[{\[]?([^\s\]}\n]+)', re.IGNORECASE)
        # address segment
        addr_re = re.compile(r'create_bd_addr_seg.*?-offset\s+(0x[0-9a-fA-F]+)', re.IGNORECASE)

        ips = vlnv_re.findall(content)
        cfgs = cfg_re.findall(content)
        addrs = addr_re.findall(content)

        if not ips and not cfgs and not addrs:
            return ""

        parts = []
        if ips:
            ip_lines = [f"  {name}: {vlnv.split(':')[-2] if ':' in vlnv else vlnv}"
                        for vlnv, name in ips[:6]]
            parts.append("[IP Instances]\n" + "\n".join(ip_lines))
        if cfgs:
            cfg_lines = [f"  {k} = {v}" for k, v in cfgs[:12]]
            parts.append("[IP Configuration]\n" + "\n".join(cfg_lines))
        if addrs:
            parts.append("[Address Map]\n" + "\n".join(f"  offset {a}" for a in addrs[:8]))

        return "\n".join(parts) + "\n---\n"

    @staticmethod
    def _c_func_summary(func_name: str, func_body: str) -> str:
        """C fonksiyon chunk'ı için kısa özet başlık."""
        # Önemli API çağrılarını bul
        api_re = re.compile(r'\b(X\w+(?:Initialize|Config|Send|Recv|Start|Stop|Reset|Enable|Disable|Transfer)\w*)\s*\(', re.IGNORECASE)
        # define sabitleri
        define_re = re.compile(r'#define\s+(\w+)\s+(\S+)')
        apis = list(dict.fromkeys(api_re.findall(func_body)))[:5]
        defines = define_re.findall(func_body)[:4]

        lines = [f"[C Function: {func_name}]"]
        if apis:
            lines.append("  API calls: " + ", ".join(apis))
        if defines:
            lines.append("  Defines: " + ", ".join(f"{k}={v}" for k, v in defines))
        return "\n".join(lines) + "\n---\n"

    @staticmethod
    def _c_header_summary(content: str, file_name: str) -> str:
        """C header/include chunk'ı için özet başlık."""
        define_re = re.compile(r'#define\s+(\w+)\s+(\S+)')
        struct_re = re.compile(r'typedef\s+struct\s*\{[^}]+\}\s*(\w+)\s*;', re.DOTALL)
        enum_re = re.compile(r'typedef\s+enum\s*\{([^}]+)\}\s*(\w+)\s*;', re.DOTALL)

        defines = define_re.findall(content)[:6]
        structs = struct_re.findall(content)
        enums = [(m.group(2), [e.strip().split('=')[0].strip() for e in m.group(1).split(',') if e.strip()][:4])
                 for m in enum_re.finditer(content)]

        if not defines and not structs and not enums:
            return ""

        lines = [f"[C Definitions — {file_name}]"]
        if defines:
            lines.append("  Constants: " + ", ".join(f"{k}={v}" for k, v in defines))
        if structs:
            lines.append("  Structs: " + ", ".join(structs))
        if enums:
            for ename, members in enums:
                lines.append(f"  Enum {ename}: " + ", ".join(members))
        return "\n".join(lines) + "\n---\n"

    @staticmethod
    def _pdf_section_summary(content: str, fname: str) -> str:
        """PDF bölümündeki teknik değerleri (parça numaraları, pin'ler, gerilimler) özetle."""
        # Part/model numbers: e.g., MT47H64M16HR-25E, LAN8720A, XC7A100T
        parts = re.findall(r'\b[A-Z]{2,}\d+[A-Z0-9]{2,}(?:[-/]\w+)?\b', content)
        # Pin references: "pin E3", "pins C4, D4"
        pins_raw = re.findall(r'\bpin[s]?\s+([A-Z]\d+(?:[,\s]+[A-Z]\d+)*)', content, re.IGNORECASE)
        # Voltage values: 1.8V, 3.3V
        voltages = re.findall(r'\b\d+\.\d+\s*[Vv]\b', content)
        # Frequencies: 100 MHz, 25 MHz
        freqs = re.findall(r'\b\d+(?:\.\d+)?\s*(?:MHz|KHz|GHz|Mbps|Gbps)\b', content, re.IGNORECASE)
        # Inline section headings (e.g., "Board Revisions", "Migrating from Nexys 4 DDR")
        # Lines that look like mini-headings: title-case, no trailing punctuation, 3-50 chars
        topic_re = re.compile(
            r'(?m)^[ \t]*([A-Z][A-Za-z]+(?: [A-Za-z0-9]+){1,6})\s*$'
        )
        topics = [m.group(1).strip() for m in topic_re.finditer(content)
                  if 5 < len(m.group(1)) < 50 and not m.group(1)[0].isdigit()][:4]

        parts_u = list(dict.fromkeys(p for p in parts if len(p) >= 5))[:5]
        pins_flat: list[str] = []
        for group in pins_raw:
            pins_flat.extend(p.strip() for p in re.split(r'[,\s]+', group) if re.match(r'^[A-Z]\d+$', p.strip()))
        pins_flat = list(dict.fromkeys(pins_flat))[:6]
        volt_u = list(dict.fromkeys(voltages))[:4]
        freq_u = list(dict.fromkeys(freqs))[:4]

        lines = [f"[PDF Section — {fname}]"]
        if topics:
            lines.append("  Topics: " + " | ".join(topics))
        if parts_u:
            lines.append("  Components: " + ", ".join(parts_u))
        if pins_flat:
            lines.append("  Pins: " + ", ".join(pins_flat))
        if volt_u:
            lines.append("  Voltages: " + ", ".join(volt_u))
        if freq_u:
            lines.append("  Frequencies: " + ", ".join(freq_u))
        if len(lines) == 1:
            return ""
        return "\n".join(lines) + "\n---\n"

    @staticmethod
    def _verilog_module_summary(module_name: str, content: str) -> str:
        """Verilog modülü için port/parametre özeti."""
        param_re = re.compile(r'parameter\s+(\w+)\s*=\s*(\S+)', re.IGNORECASE)
        port_re = re.compile(r'^\s*(input|output|inout)\s+(?:wire\s+|reg\s+)?(?:\[\d+:\d+\]\s+)?(\w+)', re.MULTILINE | re.IGNORECASE)
        params = param_re.findall(content)[:6]
        ports_in = [p for d, p in port_re.findall(content) if d.lower() == 'input'][:6]
        ports_out = [p for d, p in port_re.findall(content) if d.lower() == 'output'][:6]

        if not params and not ports_in and not ports_out:
            return ""

        lines = [f"[Verilog Module: {module_name}]"]
        if params:
            lines.append("  Parameters: " + ", ".join(f"{k}={v}" for k, v in params))
        if ports_in:
            lines.append("  Inputs: " + ", ".join(ports_in))
        if ports_out:
            lines.append("  Outputs: " + ", ".join(ports_out))
        return "\n".join(lines) + "\n---\n"

    def chunk_file(
        self,
        file_path: str,
        project: str,
        related_node_ids: Optional[List[str]] = None,
    ) -> List[SourceChunk]:
        """Bir kaynak dosyayı chunk'lara böl."""
        path = Path(file_path)
        if not path.exists():
            return []

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        ext = path.suffix.lower()
        fname = path.name

        if ext in (".v", ".sv"):
            return self._chunk_verilog(content, file_path, project, related_node_ids or [])
        elif ext in (".vhd", ".vhdl"):
            return self._chunk_vhdl(content, file_path, project, related_node_ids or [])
        elif ext in (".c", ".cpp"):
            return self._chunk_c(content, file_path, project, related_node_ids or [])
        elif ext in (".h", ".hpp"):
            return self._chunk_header(content, file_path, project, related_node_ids or [])
        elif ext == ".xdc":
            return self._chunk_xdc(content, file_path, project, related_node_ids or [])
        elif ext == ".tcl":
            return self._chunk_tcl(content, file_path, project, related_node_ids or [])
        elif ext == ".json" and "bd" in fname.lower():
            return self._chunk_bd_json(content, file_path, project, related_node_ids or [])
        elif ext == ".pdf":
            return self._chunk_pdf(file_path, project, related_node_ids or [])
        elif ext == ".prj":
            return self._chunk_mig_prj(content, file_path, project, related_node_ids or [])
        elif ext in (".md", ".txt"):
            return self._chunk_text(content, file_path, ext.lstrip("."), project, related_node_ids or [])
        else:
            return self._chunk_default(content, file_path, ext.lstrip(".") or "text",
                                       project, related_node_ids or [])

    # ------------------------------------------------------------------
    # Verilog / SystemVerilog — module sınırı
    # ------------------------------------------------------------------

    def _chunk_verilog(self, content: str, file_path: str, project: str,
                       node_ids: List[str]) -> List[SourceChunk]:
        chunks = []
        # module ... endmodule blokları
        module_re = re.compile(
            r'((?:^|\n)(?:/\*.*?\*/\n|//[^\n]*\n)*'
            r'\s*(?:`timescale[^\n]*\n)?'
            r'\s*module\s+\w+.*?endmodule)',
            re.DOTALL | re.MULTILINE,
        )
        matches = list(module_re.finditer(content))

        if not matches:
            # Modül bulunamadı → tüm dosya tek chunk
            return self._whole_file_chunk(content, file_path, "verilog", project, node_ids)

        for i, m in enumerate(matches):
            text = m.group(0).strip()
            start_line = content[:m.start()].count("\n") + 1
            end_line = content[:m.end()].count("\n") + 1

            # Modül adını çek
            mod_match = re.search(r'module\s+(\w+)', text)
            label = mod_match.group(1) if mod_match else f"module_{i+1}"

            summary = self._verilog_module_summary(label, text)
            enriched = (summary + text) if summary else text

            chunk_id = f"{Path(file_path).stem}_{label}"
            chunks.append(SourceChunk(
                chunk_id=chunk_id,
                content=enriched[:MAX_CHUNK_CHARS],
                file_path=file_path,
                file_type="verilog",
                project=project,
                start_line=start_line,
                end_line=end_line,
                chunk_label=label,
                related_node_ids=node_ids,
            ))

        return chunks if chunks else self._whole_file_chunk(
            content, file_path, "verilog", project, node_ids)

    # ------------------------------------------------------------------
    # VHDL — entity/architecture sınırı
    # ------------------------------------------------------------------

    def _chunk_vhdl(self, content: str, file_path: str, project: str,
                    node_ids: List[str]) -> List[SourceChunk]:
        # Tüm dosya genelde makul boyuttadır
        if len(content) <= MAX_CHUNK_CHARS:
            return self._whole_file_chunk(content, file_path, "vhdl", project, node_ids)
        return self._chunk_default(content, file_path, "vhdl", project, node_ids)

    # ------------------------------------------------------------------
    # C / C++ — fonksiyon sınırı + #define bloğu
    # ------------------------------------------------------------------

    def _chunk_c(self, content: str, file_path: str, project: str,
                 node_ids: List[str]) -> List[SourceChunk]:
        chunks = []
        lines = content.split("\n")

        file_prefix = Path(file_path).stem
        parent_name = Path(file_path).parent.parent.name[:8]
        file_prefix = f"{parent_name}_{file_prefix}"

        # Fonksiyon blokları: brace depth 0'da kapanan blok
        func_re = re.compile(
            r'^(?:[\w\s\*]+?)\s+(\w+)\s*\([^)]*\)\s*\{',
            re.MULTILINE,
        )

        func_matches = []
        for m in func_re.finditer(content):
            # Brace sayarak fonksiyon sonunu bul
            start = m.start()
            brace_start = content.index("{", m.start())
            depth = 0
            pos = brace_start
            while pos < len(content):
                if content[pos] == "{":
                    depth += 1
                elif content[pos] == "}":
                    depth -= 1
                    if depth == 0:
                        func_matches.append((start, pos + 1, m.group(1)))
                        break
                pos += 1

        # Header bloğu: ilk fonksiyondan önceki tüm içerik
        # (#include, #define, typedef, enum, struct, global vars)
        first_func_pos = func_matches[0][0] if func_matches else len(content)
        header_text = content[:first_func_pos].strip()
        if header_text:
            header_lines = header_text.count("\n") + 1
            # typedef struct varsa ayrı chunk'lara böl
            chunks.extend(self._split_c_headers(
                header_text, file_path, file_prefix, project, node_ids, header_lines
            ))

        for start_pos, end_pos, func_name in func_matches:
            text = content[start_pos:end_pos].strip()
            start_line = content[:start_pos].count("\n") + 1
            end_line = content[:end_pos].count("\n") + 1

            summary = self._c_func_summary(func_name, text)
            enriched = (summary + text) if summary else text

            # Büyük fonksiyonları böl
            if len(enriched) > MAX_CHUNK_CHARS:
                for j, sub in enumerate(self._split_text(enriched)):
                    chunks.append(SourceChunk(
                        chunk_id=f"{file_prefix}_{func_name}_{start_line}_{j}",
                        content=sub,
                        file_path=file_path,
                        file_type="c",
                        project=project,
                        start_line=start_line,
                        end_line=end_line,
                        chunk_label=f"{func_name} (part {j+1})",
                        related_node_ids=node_ids,
                    ))
            else:
                chunks.append(SourceChunk(
                    chunk_id=f"{file_prefix}_{func_name}_{start_line}",
                    content=enriched,
                    file_path=file_path,
                    file_type="c",
                    project=project,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_label=func_name,
                    related_node_ids=node_ids,
                ))

        # Fonksiyonlar arası içerik (typedef struct, global vars, #ifdef blokları)
        # func_matches sıralıdır; ardışık iki fonksiyon arasındaki boşluğu kontrol et
        for i, (s, e, _) in enumerate(func_matches):
            next_start = func_matches[i + 1][0] if i + 1 < len(func_matches) else len(content)
            inter = content[e:next_start].strip()
            if inter and len(inter) > 40:
                sl = content[:e].count("\n") + 1
                el = content[:next_start].count("\n") + 1
                for j, sub in enumerate(
                    self._split_text(inter) if len(inter) > MAX_CHUNK_CHARS else [inter]
                ):
                    chunks.append(SourceChunk(
                        chunk_id=f"{file_prefix}_decl_{sl}" + (f"_{j}" if j else ""),
                        content=sub,
                        file_path=file_path,
                        file_type="c",
                        project=project,
                        start_line=sl,
                        end_line=el,
                        chunk_label=f"declarations_after_line_{sl}",
                        related_node_ids=node_ids,
                    ))

        if not chunks:
            return self._chunk_default(content, file_path, "c", project, node_ids)

        return chunks

    def _split_c_headers(
        self,
        header_text: str,
        file_path: str,
        file_prefix: str,
        project: str,
        node_ids: List[str],
        end_line: int,
    ) -> List[SourceChunk]:
        """
        C header bloğunu typedef struct sınırlarına göre böl.
        Küçük header'lar (<= 800 chars) tek chunk olarak kalır.
        """
        typedef_re = re.compile(r'typedef\s+struct\s*\w*\s*\{', re.MULTILINE)
        matches = list(typedef_re.finditer(header_text))

        if not matches:
            # Struct yok → tek chunk
            summary = self._c_header_summary(header_text, Path(file_path).name)
            enriched = (summary + header_text) if summary else header_text
            return [SourceChunk(
                chunk_id=f"{file_prefix}_headers",
                content=enriched[:MAX_CHUNK_CHARS],
                file_path=file_path,
                file_type="c",
                project=project,
                start_line=1,
                end_line=end_line,
                chunk_label="includes_defines_typedefs",
                related_node_ids=node_ids,
            )]

        chunks: List[SourceChunk] = []
        last_pos = 0

        for i, m in enumerate(matches):
            # struct öncesi içerik (includes + defines)
            pre = header_text[last_pos:m.start()].strip()
            if pre and i == 0:
                summary = self._c_header_summary(pre, Path(file_path).name)
                enriched_pre = (summary + pre) if summary else pre
                chunks.append(SourceChunk(
                    chunk_id=f"{file_prefix}_headers_pre",
                    content=enriched_pre[:MAX_CHUNK_CHARS],
                    file_path=file_path,
                    file_type="c",
                    project=project,
                    start_line=1,
                    end_line=1 + pre.count("\n"),
                    chunk_label="includes_defines",
                    related_node_ids=node_ids,
                ))

            # struct bloğunun sonunu brace sayarak bul
            brace_depth = 0
            pos = m.start()
            struct_end = len(header_text)
            while pos < len(header_text):
                if header_text[pos] == "{":
                    brace_depth += 1
                elif header_text[pos] == "}":
                    brace_depth -= 1
                    if brace_depth == 0:
                        semi = header_text.find(";", pos)
                        struct_end = semi + 1 if semi != -1 else pos + 1
                        break
                pos += 1

            struct_text = header_text[m.start():struct_end]
            # "typedef struct { ... } NAME;" → NAME al
            name_m = re.search(r'\}\s*(\w+)\s*;', struct_text)
            struct_name = name_m.group(1) if name_m else f"struct_{i}"

            sl = 1 + header_text[:m.start()].count("\n")
            el = 1 + header_text[:struct_end].count("\n")
            chunks.append(SourceChunk(
                chunk_id=f"{file_prefix}_struct_{struct_name}",
                content=struct_text[:MAX_CHUNK_CHARS],
                file_path=file_path,
                file_type="c",
                project=project,
                start_line=sl,
                end_line=el,
                chunk_label=f"typedef struct {struct_name}",
                related_node_ids=node_ids,
            ))
            last_pos = struct_end

        # Son struct'tan sonra kalan içerik
        remaining = header_text[last_pos:].strip()
        if remaining:
            sl = 1 + header_text[:last_pos].count("\n")
            chunks.append(SourceChunk(
                chunk_id=f"{file_prefix}_headers_post",
                content=remaining[:MAX_CHUNK_CHARS],
                file_path=file_path,
                file_type="c",
                project=project,
                start_line=sl,
                end_line=end_line,
                chunk_label="global_vars",
                related_node_ids=node_ids,
            ))

        return chunks if chunks else [SourceChunk(
            chunk_id=f"{file_prefix}_headers",
            content=header_text[:MAX_CHUNK_CHARS],
            file_path=file_path,
            file_type="c",
            project=project,
            start_line=1,
            end_line=end_line,
            chunk_label="includes_defines_typedefs",
            related_node_ids=node_ids,
        )]

    # ------------------------------------------------------------------
    # Header dosyaları — #define + typedef + struct
    # ------------------------------------------------------------------

    def _chunk_header(self, content: str, file_path: str, project: str,
                      node_ids: List[str]) -> List[SourceChunk]:
        if len(content) <= MAX_CHUNK_CHARS:
            return self._whole_file_chunk(content, file_path, "header", project, node_ids)
        return self._chunk_default(content, file_path, "header", project, node_ids)

    # ------------------------------------------------------------------
    # XDC — küçük dosyalar → tümü; büyük dosyalar → pin grupları
    # ------------------------------------------------------------------

    def _chunk_xdc(self, content: str, file_path: str, project: str,
                   node_ids: List[str]) -> List[SourceChunk]:
        # Her XDC chunk'ına pin özeti ekle (index-time semantic enrichment)
        pin_summary = self._xdc_pin_summary(content, Path(file_path).name)
        enriched = pin_summary + content if pin_summary else content

        if len(enriched) <= MAX_CHUNK_CHARS:
            return self._whole_file_chunk(enriched, file_path, "xdc", project, node_ids)

        # Büyük XDC: ## başlıklı bölümlere göre böl
        # NOTE: Some XDC files use "## Section" (with space) and some "##Section" (no space)
        # Ayrıca "#PWM Audio Amplifier" gibi tek-hash subsection başlıkları da bölünüyor:
        # ^#(?=[A-Z]) — tek # + büyük harf (commented set_property'ler küçük harf ile başlar)
        fname = Path(file_path).name
        chunks = []
        sections = re.split(r'(?m)^##\s*|^#(?=[A-Z])', content)  # original content ile böl
        for i, sec in enumerate(sections):
            if not sec.strip():
                continue
            first_line = sec.split("\n")[0].strip()
            label = re.sub(r'[^\w\s]', '', first_line)[:40] or f"section_{i}"
            start_line = content[:content.find(sec)].count("\n") + 1 if sec in content else 0
            end_line = start_line + sec.count("\n")
            # Her section'a o section'ın pin özetini ekle
            sec_summary = self._xdc_pin_summary(sec, fname)
            sec_enriched = (sec_summary + sec) if sec_summary else sec
            chunks.append(SourceChunk(
                chunk_id=f"{Path(file_path).stem}_{i}_{label.replace(' ','_')}",
                content=sec_enriched[:MAX_CHUNK_CHARS],
                file_path=file_path,
                file_type="xdc",
                project=project,
                start_line=start_line,
                end_line=end_line,
                chunk_label=label,
                related_node_ids=node_ids,
            ))
        return chunks if chunks else self._whole_file_chunk(
            content, file_path, "xdc", project, node_ids)

    # ------------------------------------------------------------------
    # TCL — proc sınırları, # Create instance: blokları, veya ADIM/Step
    # ------------------------------------------------------------------

    def _chunk_tcl(self, content: str, file_path: str, project: str,
                   node_ids: List[str]) -> List[SourceChunk]:
        if len(content) <= MAX_CHUNK_CHARS:
            return self._whole_file_chunk(content, file_path, "tcl", project, node_ids)

        stem = Path(file_path).stem

        # ── Strategy 1: proc-level split (design_1.tcl / BD-TCL style) ──────
        # Each top-level "proc <name> {" becomes its own chunk.
        # Then within large procs, split further on "# Create instance:" lines.
        proc_re = re.compile(r'(?m)^proc\s+(\w+)', re.MULTILINE)
        proc_matches = list(proc_re.finditer(content))

        if proc_matches:
            chunks = []
            # Content before first proc (boilerplate / preamble)
            preamble = content[:proc_matches[0].start()].strip()
            if len(preamble) > 50:
                start_ln = 1
                end_ln = content[:proc_matches[0].start()].count("\n") + 1
                for j, sub in enumerate(self._split_text(preamble) if len(preamble) > MAX_CHUNK_CHARS else [preamble]):
                    chunks.append(SourceChunk(
                        chunk_id=f"{stem}_preamble_{j}" if j else f"{stem}_preamble",
                        content=sub,
                        file_path=file_path,
                        file_type="tcl",
                        project=project,
                        start_line=start_ln,
                        end_line=end_ln,
                        chunk_label="preamble",
                        related_node_ids=node_ids,
                    ))

            for pi, pm in enumerate(proc_matches):
                proc_name = pm.group(1)
                proc_start = pm.start()
                proc_end = proc_matches[pi + 1].start() if pi + 1 < len(proc_matches) else len(content)
                proc_body = content[proc_start:proc_end].strip()
                sl = content[:proc_start].count("\n") + 1
                el = content[:proc_end].count("\n") + 1

                # Try to split large procs on "# Create instance:" lines
                inst_re = re.compile(r'(?m)^\s*#\s*Create instance\s*:\s*(\w+)', re.IGNORECASE)
                inst_matches = list(inst_re.finditer(proc_body))

                if len(proc_body) > MAX_CHUNK_CHARS and inst_matches:
                    # Preamble of the proc (before first Create instance)
                    pre = proc_body[:inst_matches[0].start()].strip()
                    if len(pre) > 50:
                        chunks.append(SourceChunk(
                            chunk_id=f"{stem}_proc_{proc_name}_header",
                            content=pre[:MAX_CHUNK_CHARS],
                            file_path=file_path,
                            file_type="tcl",
                            project=project,
                            start_line=sl,
                            end_line=sl + pre.count("\n"),
                            chunk_label=f"{proc_name} (header)",
                            related_node_ids=node_ids,
                        ))
                    # Split regex'leri — komut adına dayalı (yorum satırına değil)
                    _addr_seg_re  = re.compile(r'(?m)^\s*create_bd_addr_seg\b')
                    # Yalnızca connect_bd_net (sinyal bağlantıları: interrupt wiring, clk, reset)
                    # connect_bd_intf_net (AXI bus) KAPSANMIYOR — AXI bus xadc/son-IP chunk'ında kalır
                    # Sebep: intf_net satırları sinyal sorularında gereksiz gürültü + MAX_CHUNK_CHARS'ı dolduruyor
                    _net_conn_re  = re.compile(r'(?m)^\s*connect_bd_net\b(?!.*intf)')

                    # Each IP instance block
                    for ii, im in enumerate(inst_matches):
                        ip_name = im.group(1)
                        blk_start = im.start()
                        blk_end = inst_matches[ii + 1].start() if ii + 1 < len(inst_matches) else len(proc_body)

                        # Son IP bloğunda: 3 kısma bölünebilir
                        # IP config | net_connections | address_map
                        addr_map_content = None
                        addr_map_sl = None
                        net_conn_content = None
                        net_conn_sl = None
                        if ii == len(inst_matches) - 1:
                            # Önce address_map sınırını bul
                            addr_m = _addr_seg_re.search(proc_body, blk_start)
                            if addr_m and addr_m.start() < blk_end:
                                addr_map_sl = sl + proc_body[:addr_m.start()].count("\n")
                                addr_map_content = proc_body[addr_m.start():blk_end].strip()
                                blk_end = addr_m.start()  # IP bloğunu kırp

                            # Sonra connect_bd_net sınırını bul (address_map'ten önceki bölgede)
                            net_m = _net_conn_re.search(proc_body, blk_start)
                            if net_m and net_m.start() < blk_end:
                                net_conn_sl = sl + proc_body[:net_m.start()].count("\n")
                                net_conn_content = proc_body[net_m.start():blk_end].strip()
                                blk_end = net_m.start()  # IP config'i kırp

                        blk = proc_body[blk_start:blk_end].strip()
                        blk_sl = sl + proc_body[:blk_start].count("\n")
                        blk_el = sl + proc_body[:blk_end].count("\n")
                        summary = self._tcl_ip_summary(blk, Path(file_path).name)
                        enriched_blk = (summary + blk) if summary else blk
                        for j, sub in enumerate(self._split_text(enriched_blk) if len(enriched_blk) > MAX_CHUNK_CHARS else [enriched_blk]):
                            chunks.append(SourceChunk(
                                chunk_id=f"{stem}_{ip_name}_{j}" if j else f"{stem}_{ip_name}",
                                content=sub,
                                file_path=file_path,
                                file_type="tcl",
                                project=project,
                                start_line=blk_sl,
                                end_line=blk_el,
                                chunk_label=ip_name,
                                related_node_ids=node_ids,
                            ))

                        # Net connections chunk: connect_bd_net sinyal bağlantıları
                        # Interrupt port assignments, clock routing, reset signals içerir.
                        # Büyük dosyalarda (çok sayıda net) _split_text ile birden fazla chunk.
                        if net_conn_content and len(net_conn_content) > 20:
                            net_header = (
                                f"[TCL Net Connections] {Path(file_path).name} — "
                                f"Signal wiring (connect_bd_net): interrupt port assignments, "
                                f"clock routing, reset signals, sensor connections.\n\n"
                            )
                            net_enriched = net_header + net_conn_content
                            net_el = net_conn_sl + net_conn_content.count("\n")
                            net_parts = self._split_text(net_enriched) if len(net_enriched) > MAX_CHUNK_CHARS else [net_enriched]
                            for j, sub in enumerate(net_parts):
                                chunks.append(SourceChunk(
                                    chunk_id=f"{stem}_net_connections_{j}" if j else f"{stem}_net_connections",
                                    content=sub,
                                    file_path=file_path,
                                    file_type="tcl",
                                    project=project,
                                    start_line=net_conn_sl,
                                    end_line=net_el,
                                    chunk_label="net_connections",
                                    related_node_ids=node_ids,
                                ))

                        # Address map chunk: create_bd_addr_seg bloğu
                        if addr_map_content and len(addr_map_content) > 20:
                            addr_header = (
                                f"[TCL Address Map] {Path(file_path).name} — "
                                f"AXI address segment assignments (create_bd_addr_seg).\n"
                                f"IP offset/range: peripheral base addresses for MicroBlaze data/instruction spaces.\n\n"
                            )
                            addr_enriched = addr_header + addr_map_content
                            addr_el = sl + proc_body[:blk_end + len(addr_map_content)].count("\n")
                            chunks.append(SourceChunk(
                                chunk_id=f"{stem}_address_map",
                                content=addr_enriched[:MAX_CHUNK_CHARS],
                                file_path=file_path,
                                file_type="tcl",
                                project=project,
                                start_line=addr_map_sl,
                                end_line=addr_el,
                                chunk_label="address_map",
                                related_node_ids=node_ids,
                            ))
                else:
                    # Proc small enough or no Create instance → whole proc or split
                    for j, sub in enumerate(self._split_text(proc_body) if len(proc_body) > MAX_CHUNK_CHARS else [proc_body]):
                        chunks.append(SourceChunk(
                            chunk_id=f"{stem}_proc_{proc_name}_{j}" if j else f"{stem}_proc_{proc_name}",
                            content=sub,
                            file_path=file_path,
                            file_type="tcl",
                            project=project,
                            start_line=sl,
                            end_line=el,
                            chunk_label=f"{proc_name} (part {j+1})" if j else proc_name,
                            related_node_ids=node_ids,
                        ))

            if chunks:
                return chunks

        # ── Strategy 2: ADIM / Step / #### separators ────────────────────────
        chunks = []
        section_re = re.compile(
            r'(?m)^(?:#+\s*(?:ADIM|Step|PHASE|Phase)\s*\d+|#{4,})', re.IGNORECASE)
        positions = [m.start() for m in section_re.finditer(content)]
        positions.append(len(content))

        for i in range(len(positions) - 1):
            sec = content[positions[i]:positions[i+1]].strip()
            if len(sec) < 20:
                continue
            first_line = sec.split("\n")[0].strip("# \t")[:50]
            label = re.sub(r'[^\w\s]', '', first_line) or f"section_{i}"
            start_line = content[:positions[i]].count("\n") + 1
            end_line = content[:positions[i+1]].count("\n") + 1

            if len(sec) > MAX_CHUNK_CHARS:
                for j, sub in enumerate(self._split_text(sec)):
                    chunks.append(SourceChunk(
                        chunk_id=f"{stem}_s{i}_{j}",
                        content=sub,
                        file_path=file_path,
                        file_type="tcl",
                        project=project,
                        start_line=start_line,
                        end_line=end_line,
                        chunk_label=f"{label} (part {j+1})",
                        related_node_ids=node_ids,
                    ))
            else:
                chunks.append(SourceChunk(
                    chunk_id=f"{stem}_s{i}",
                    content=sec,
                    file_path=file_path,
                    file_type="tcl",
                    project=project,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_label=label,
                    related_node_ids=node_ids,
                ))

        return chunks if chunks else self._chunk_default(
            content, file_path, "tcl", project, node_ids)

    # ------------------------------------------------------------------
    # BD JSON — IP bloklarına göre
    # ------------------------------------------------------------------

    def _chunk_bd_json(self, content: str, file_path: str, project: str,
                       node_ids: List[str]) -> List[SourceChunk]:
        # BD JSON dosyaları genellikle büyük olur, key bölümlere böl
        chunks = []
        try:
            data = json.loads(content)
            # cells / modules seviyesini çek
            cells = data.get("design", {}).get("cells", {})
            if not cells:
                cells = data.get("cells", {})

            for cell_name, cell_data in cells.items():
                cell_text = json.dumps({cell_name: cell_data}, indent=2, ensure_ascii=False)
                if len(cell_text) > 20:
                    chunks.append(SourceChunk(
                        chunk_id=f"{Path(file_path).stem}_{cell_name}",
                        content=cell_text[:MAX_CHUNK_CHARS],
                        file_path=file_path,
                        file_type="bd_json",
                        project=project,
                        start_line=0,
                        end_line=0,
                        chunk_label=cell_name,
                        related_node_ids=node_ids,
                    ))
        except Exception:
            pass

        return chunks if chunks else self._chunk_default(
            content, file_path, "json", project, node_ids)

    # ------------------------------------------------------------------
    # Markdown / Plain text — section breaks on ## headings or blank lines
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # PDF — section-based (PyMuPDF / fitz)
    # ------------------------------------------------------------------

    def _chunk_pdf(self, file_path: str, project: str, node_ids: List[str]) -> List[SourceChunk]:
        """PDF dosyasını section başlıklarına göre chunk'lara böl."""
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return []

        fname = Path(file_path).stem

        try:
            doc = fitz.open(str(file_path))
            page_blocks: list[tuple[int, str]] = []
            for i, page in enumerate(doc):
                txt = page.get_text("text")
                if txt.strip():
                    page_blocks.append((i + 1, txt))
            doc.close()
        except Exception:
            return []

        if not page_blocks:
            return []

        # Strip boilerplate footers/headers from each page
        footer_re = re.compile(
            r'(?:Copyright Digilent[^\n]*\n|Page \d+ of \d+\n|'
            r'Other product and company names[^\n]*\n)',
            re.IGNORECASE,
        )

        # Build one combined text with [PAGE N] markers
        full_text = ""
        for pnum, ptxt in page_blocks:
            cleaned = footer_re.sub("", ptxt).strip()
            if cleaned:
                full_text += f"\n[PAGE {pnum}]\n{cleaned}\n"

        # Section heading: lines like "1 Overview", "4.1 DDR2 Memory", "10 Pmod Ports"
        # Require: 1-2 digit section number (max 20), title at least 2 words (5+ chars each)
        section_re = re.compile(
            r'(?m)^[ \t]*([1-9]|1\d|20)(?:\.\d+)*\s+([A-Z][A-Za-z]{2,}(?:[\s/\-][A-Za-z].{1,30})?)\s*$'
        )

        boundaries: list[tuple[int, str]] = []
        for m in section_re.finditer(full_text):
            title = f"{m.group(1)} {m.group(2).strip()}"
            boundaries.append((m.start(), title))

        if not boundaries:
            return self._chunk_pdf_pages(page_blocks, file_path, fname, project, node_ids)

        boundaries.append((len(full_text), "_end"))

        chunks: list[SourceChunk] = []
        chunk_idx = 0

        # Pre-section intro text (split if too large)
        intro = full_text[:boundaries[0][0]].strip()
        if len(intro) > 100:
            if len(intro) <= MAX_CHUNK_CHARS:
                summary = self._pdf_section_summary(intro, fname)
                chunks.append(SourceChunk(
                    chunk_id=f"{fname}_intro",
                    content=summary + intro,
                    file_path=file_path, file_type="pdf",
                    project=project, start_line=0, end_line=0,
                    chunk_label=f"{fname}_intro",
                    related_node_ids=node_ids,
                ))
            else:
                for j, sub in enumerate(self._split_text(intro)):
                    sub_summary = self._pdf_section_summary(sub, fname)
                    chunks.append(SourceChunk(
                        chunk_id=f"{fname}_intro_{j}",
                        content=sub_summary + sub,
                        file_path=file_path, file_type="pdf",
                        project=project, start_line=0, end_line=0,
                        chunk_label=f"{fname}_intro_p{j+1}",
                        related_node_ids=node_ids,
                    ))

        for i, (pos, title) in enumerate(boundaries[:-1]):
            next_pos = boundaries[i + 1][0]
            sec_text = full_text[pos:next_pos].strip()

            if len(sec_text) < 50:
                continue

            label = re.sub(r'[^\w\s]', '_', title)[:50]
            summary = self._pdf_section_summary(sec_text, fname)

            if len(sec_text) <= MAX_CHUNK_CHARS:
                chunks.append(SourceChunk(
                    chunk_id=f"{fname}_s{chunk_idx}",
                    content=summary + sec_text,
                    file_path=file_path, file_type="pdf",
                    project=project, start_line=0, end_line=0,
                    chunk_label=f"{fname}_{label}",
                    related_node_ids=node_ids,
                ))
                chunk_idx += 1
            else:
                for j, sub in enumerate(self._split_text(sec_text)):
                    sub_summary = self._pdf_section_summary(sub, fname)
                    chunks.append(SourceChunk(
                        chunk_id=f"{fname}_s{chunk_idx}_{j}",
                        content=sub_summary + sub,
                        file_path=file_path, file_type="pdf",
                        project=project, start_line=0, end_line=0,
                        chunk_label=f"{fname}_{label}_p{j+1}",
                        related_node_ids=node_ids,
                    ))
                chunk_idx += 1

        return chunks if chunks else self._chunk_pdf_pages(page_blocks, file_path, fname, project, node_ids)

    def _chunk_pdf_pages(
        self,
        page_blocks: list,
        file_path: str,
        fname: str,
        project: str,
        node_ids: List[str],
    ) -> List[SourceChunk]:
        """PDF fallback: 2 sayfa birleştirip chunk yap."""
        chunks: list[SourceChunk] = []
        i = 0
        while i < len(page_blocks):
            batch = page_blocks[i:i + 2]
            text = "\n".join(f"[PAGE {p}]\n{t}" for p, t in batch).strip()
            if len(text) > 50:
                pnum = batch[0][0]
                summary = self._pdf_section_summary(text, fname)
                chunks.append(SourceChunk(
                    chunk_id=f"{fname}_p{pnum}",
                    content=(summary + text)[:MAX_CHUNK_CHARS],
                    file_path=file_path, file_type="pdf",
                    project=project, start_line=pnum, end_line=batch[-1][0],
                    chunk_label=f"{fname}_page{pnum}",
                    related_node_ids=node_ids,
                ))
            i += 2
        return chunks

    def _chunk_text(self, content: str, file_path: str, file_type: str,
                    project: str, node_ids: List[str]) -> List[SourceChunk]:
        if len(content) <= MAX_CHUNK_CHARS:
            return self._whole_file_chunk(content, file_path, file_type, project, node_ids)

        chunks = []
        stem = Path(file_path).stem
        # Split on markdown headings (## or ###) or standalone horizontal rules (not table rows)
        # Table separators (|---|---| or just ---) are excluded by requiring no '|' in the line
        section_re = re.compile(r'(?m)^(?:#{1,3}\s+.+|[-─=]{4,})\s*$')
        positions = [m.start() for m in section_re.finditer(content)
                     if '|' not in content[m.start():m.end()]]
        positions.append(len(content))

        for i in range(len(positions) - 1):
            sec = content[positions[i]:positions[i+1]].strip()
            if len(sec) < 20:
                continue
            first_line = sec.split("\n")[0].strip("# \t─-=")[:50]
            label = re.sub(r'[^\w\s]', '', first_line) or f"section_{i}"
            start_line = content[:positions[i]].count("\n") + 1
            end_line = content[:positions[i+1]].count("\n") + 1

            if len(sec) > MAX_CHUNK_CHARS:
                for j, sub in enumerate(self._split_text(sec)):
                    chunks.append(SourceChunk(
                        chunk_id=f"{stem}_t{i}_{j}",
                        content=sub,
                        file_path=file_path, file_type=file_type,
                        project=project, start_line=start_line, end_line=end_line,
                        chunk_label=f"{label} (part {j+1})",
                        related_node_ids=node_ids,
                    ))
            else:
                chunks.append(SourceChunk(
                    chunk_id=f"{stem}_t{i}",
                    content=sec,
                    file_path=file_path, file_type=file_type,
                    project=project, start_line=start_line, end_line=end_line,
                    chunk_label=label,
                    related_node_ids=node_ids,
                ))

        return chunks if chunks else self._chunk_default(content, file_path, file_type, project, node_ids)

    # ------------------------------------------------------------------
    # Xilinx MIG .prj (XML) — DDR3/DDR2 pin + clock + AXI ayarları
    # ------------------------------------------------------------------

    def _chunk_mig_prj(self, content: str, file_path: str, project: str,
                       node_ids: List[str]) -> List[SourceChunk]:
        """Xilinx MIG .prj XML dosyasını kapsamlı okunabilir metne çevir.
        Format imzası yoksa (sim filelist vb.) sıfır chunk döndür — gürültü yok.
        Tüm alanlar düz metin olarak çıkarılır — soru uzayı regex sınırı yok.
        """
        if "<Project NoOfControllers=" not in content[:500]:
            return []

        fname = Path(file_path).stem

        def _tag(tag: str, default: str = "?") -> str:
            m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', content, re.IGNORECASE | re.DOTALL)
            return m.group(1).strip() if m else default

        def _attr(tag: str, attr: str, default: str = "?") -> str:
            m = re.search(rf'<{tag}\b[^>]*/>', content, re.IGNORECASE)
            if m:
                a = re.search(rf'{attr}="([^"]*)"', m.group(0), re.IGNORECASE)
                return a.group(1).strip() if a else default
            return default

        # ── Genel yapılandırma ────────────────────────────────────────────────
        ctrl_m = re.search(r'NoOfControllers="(\d+)"', content)
        ddr_period = _tag("TimePeriod")
        try:
            ddr_freq = f"{1_000_000 / float(ddr_period):.0f} MHz"
        except Exception:
            ddr_freq = "?"

        mem_size_raw = _tag("C0_MEM_SIZE")
        try:
            mem_size_mb = f"{int(mem_size_raw) // (1024*1024)} MB"
        except Exception:
            mem_size_mb = mem_size_raw

        lines = [
            f"[MIG PRJ] {fname}",
            f"Kaynak: {file_path}",
            "",
            "── Genel Yapılandırma ──────────────────────────────────────",
            f"  FPGA Target        : {_tag('TargetFPGA')}",
            f"  MIG Version        : {_tag('Version')}",
            f"  Module Name        : {_tag('ModuleName')}",
            f"  Controllers        : {ctrl_m.group(1) if ctrl_m else '?'}",
            f"  System Clock       : {_tag('SystemClock')}",
            f"  Reference Clock    : {_tag('ReferenceClock')}",
            f"  Reset Polarity     : {_tag('SysResetPolarity')}",
            f"  Low Power          : {_tag('LowPower_En')}",
            f"  XADC               : {_tag('XADC_En')}",
            f"  DCI Inputs         : {_tag('dci_inputs')}",
            "",
            "── DDR3 Controller (C0) ────────────────────────────────────",
            f"  Memory Device      : {_tag('MemoryDevice')}",
            f"  Memory Voltage     : {_tag('MemoryVoltage')}",
            f"  Memory Size        : {mem_size_mb}  ({mem_size_raw} bytes)",
            f"  Data Width         : {_tag('DataWidth')} bit",
            f"  Data Mask          : {_tag('DataMask')}",
            f"  ECC                : {_tag('ECC')}",
            f"  Ordering           : {_tag('Ordering')}",
            f"  Bank Machine Count : {_tag('BankMachineCnt')}",
            f"  Address Map        : {_tag('UserMemoryAddressMap')}",
            f"  Row Address        : {_tag('RowAddress')} bit",
            f"  Col Address        : {_tag('ColAddress')} bit",
            f"  Bank Address       : {_tag('BankAddress')} bit",
            "",
            "── Clock & PHY ─────────────────────────────────────────────",
            f"  Input Clock Freq   : {_tag('InputClkFreq')} MHz",
            f"  DDR3 Period        : {ddr_period} ps  →  {ddr_freq}",
            f"  PHY Ratio          : {_tag('PHYRatio')}",
            f"  MMCM VCO           : {_tag('MMCM_VCO')} MHz",
            f"  MMCM ClkOut0       : {_tag('MMCMClkOut0')}",
            f"  UI Extra Clocks    : {_tag('UIExtraClocks')}",
            "",
            "── AXI Interface ───────────────────────────────────────────",
            f"  Port Interface     : {_tag('PortInterface')}",
            f"  AXI Addr Width     : {_tag('C0_S_AXI_ADDR_WIDTH')} bit",
            f"  AXI Data Width     : {_tag('C0_S_AXI_DATA_WIDTH')} bit",
            f"  AXI ID Width       : {_tag('C0_S_AXI_ID_WIDTH')} bit",
            f"  RD/WR Arb Algo     : {_tag('C0_C_RD_WR_ARB_ALGORITHM')}",
            f"  Narrow Burst       : {_tag('C0_S_AXI_SUPPORTS_NARROW_BURST')}",
            "",
            "── Timing Parameters ───────────────────────────────────────",
        ]

        # TimingParameters tek satır attribute olarak geliyor
        tp_m = re.search(r'<Parameters\s+([^/]+)/>', content, re.IGNORECASE)
        if tp_m:
            tp_attrs = dict(re.findall(r'(\w+)="([^"]*)"', tp_m.group(1)))
            for k, v in tp_attrs.items():
                lines.append(f"  {k:<20s} : {v}")
        else:
            lines.append("  (timing parametreleri bulunamadı)")

        lines += [
            "",
            "── Mode Register Değerleri ─────────────────────────────────",
            f"  Burst Length       : {_tag('mrBurstLength')}",
            f"  Burst Type         : {_tag('mrBurstType')}",
            f"  CAS Latency        : {_tag('mrCasLatency')}",
            f"  CAS Write Latency  : {_tag('mr2CasWriteLatency')}",
            f"  Mode               : {_tag('mrMode')}",
            f"  DLL Reset          : {_tag('mrDllReset')}",
            f"  PD Mode            : {_tag('mrPdMode')}",
            f"  DLL Enable         : {_tag('emrDllEnable')}",
            f"  Output Drive       : {_tag('emrOutputDriveStrength')}",
            f"  RTT (ODT)          : {_tag('emrRTT')}",
            f"  Additive Latency   : {_tag('emrPosted')}",
            f"  Address Mirroring  : {_tag('emrMirrorSelection')}",
            f"  TDQS Enable        : {_tag('emrDQS')}",
            f"  Auto Self Refresh  : {_tag('mr2AutoSelfRefresh')}",
            f"  RTT_WR             : {_tag('mr2RTTWR')}",
            f"  Partial Array SR   : {_tag('mr2PartialArraySelfRefresh')}",
            "",
            "── Pin Atamaları (PinSelection) ────────────────────────────",
        ]

        # Pin atamaları
        pin_re = re.compile(r'<Pin\b([^/]*)/>', re.IGNORECASE)
        attr_re = re.compile(r'(\w+)="([^"]*)"')
        pins = []
        for m in pin_re.finditer(content):
            attrs = dict(attr_re.findall(m.group(1)))
            pad = attrs.get("PADName", "?")
            sig = attrs.get("name", "?")
            ios = attrs.get("IOSTANDARD", "?")
            if pad and sig:
                pins.append((ios, pad, sig))

        for ios, pad, sig in pins:
            lines.append(f"  {sig:<35s} → PACKAGE_PIN {pad:<8s} IOSTANDARD={ios}")

        lines += [
            f"  Toplam pin sayısı  : {len(pins)}",
            "",
            "── Sistem Saati ────────────────────────────────────────────",
        ]

        # System_Clock
        sc_m = re.search(r'<System_Clock>(.*?)</System_Clock>', content, re.IGNORECASE | re.DOTALL)
        if sc_m:
            for pm in pin_re.finditer(sc_m.group(1)):
                attrs = dict(attr_re.findall(pm.group(1)))
                lines.append(f"  {attrs.get('name','?'):<20s} → Bank {attrs.get('Bank','?')}, PADName {attrs.get('PADName','?')}")

        lines += ["", "── Bağlanmamış Sinyaller (No connect) ──────────────────────"]

        # System_Control
        sctl_m = re.search(r'<System_Control>(.*?)</System_Control>', content, re.IGNORECASE | re.DOTALL)
        if sctl_m:
            for pm in pin_re.finditer(sctl_m.group(1)):
                attrs = dict(attr_re.findall(pm.group(1)))
                if "No connect" in attrs.get("PADName", ""):
                    lines.append(f"  {attrs.get('name','?')}")

        full_text = "\n".join(lines).strip()

        # Tek chunk — dosya küçük, bölmeye gerek yok
        # Büyük olursa (nadiren) config + pins olarak ikiye böl
        if len(full_text) <= MAX_CHUNK_CHARS:
            return [SourceChunk(
                chunk_id=f"{fname}_mig_prj",
                content=full_text,
                file_path=file_path,
                file_type="mig_prj",
                project=project,
                start_line=1,
                end_line=content.count("\n") + 1,
                chunk_label=f"{fname}_mig_full_config",
                related_node_ids=node_ids,
            )]

        # Büyük dosya: config + pins ayrı
        split_idx = full_text.find("── Pin Atamaları")
        chunks = []
        for i, part in enumerate([full_text[:split_idx], full_text[split_idx:]]):
            if part.strip():
                chunks.append(SourceChunk(
                    chunk_id=f"{fname}_mig_prj_p{i}",
                    content=part.strip(),
                    file_path=file_path,
                    file_type="mig_prj",
                    project=project,
                    start_line=0, end_line=0,
                    chunk_label=f"{fname}_mig_{'config' if i==0 else 'pins'}",
                    related_node_ids=node_ids,
                ))
        return chunks

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _whole_file_chunk(self, content: str, file_path: str, file_type: str,
                          project: str, node_ids: List[str]) -> List[SourceChunk]:
        """Küçük dosyalar için — tüm içerik tek chunk."""
        return [SourceChunk(
            chunk_id=Path(file_path).stem,
            content=content[:MAX_CHUNK_CHARS],
            file_path=file_path,
            file_type=file_type,
            project=project,
            start_line=1,
            end_line=content.count("\n") + 1,
            chunk_label=Path(file_path).name,
            related_node_ids=node_ids,
        )]

    def _chunk_default(self, content: str, file_path: str, file_type: str,
                       project: str, node_ids: List[str]) -> List[SourceChunk]:
        """Fallback: sabit boyutlu, overlap'li pencereler."""
        chunks = []
        lines = content.split("\n")
        total = len(lines)
        step = max(1, MAX_CHUNK_CHARS // 80)  # yaklaşık satır sayısı
        overlap = max(0, OVERLAP_CHARS // 80)

        i = 0
        chunk_idx = 0
        while i < total:
            end = min(i + step, total)
            text = "\n".join(lines[i:end]).strip()
            if text:
                chunks.append(SourceChunk(
                    chunk_id=f"{Path(file_path).stem}_c{chunk_idx}",
                    content=text[:MAX_CHUNK_CHARS],
                    file_path=file_path,
                    file_type=file_type,
                    project=project,
                    start_line=i + 1,
                    end_line=end,
                    chunk_label=f"lines {i+1}-{end}",
                    related_node_ids=node_ids,
                ))
                chunk_idx += 1
            i += step - overlap

        return chunks

    def _split_text(self, text: str) -> List[str]:
        """Büyük metni MAX_CHUNK_CHARS'lı parçalara böl."""
        parts = []
        while text:
            parts.append(text[:MAX_CHUNK_CHARS])
            text = text[MAX_CHUNK_CHARS - OVERLAP_CHARS:]
        return parts


# ─────────────────────────────────────────────────────────────────────────────
# SourceChunkStore
# ─────────────────────────────────────────────────────────────────────────────

class SourceChunkStore:
    """
    Kaynak dosya chunk'larının ChromaDB vektör deposu + BM25 keyword indeksi.

    Architecture: fpga_rag_architecture_v2.md — 4th store eki.
    Graph node store  → mimari metadata
    Source chunk store → implementasyon detayı (RTL, SW, XDC, TCL)

    Hybrid search: BM25 (exact keyword) + semantic (embedding) → RRF merge
    Bu sayede Türkçe doğal dil sorgular teknik kod içeriğini query-time
    augmentation'a ihtiyaç duymadan bulur.
    """

    COLLECTION_NAME = "source_chunks"
    _RRF_K = 60       # Reciprocal Rank Fusion sabit parametresi

    def __init__(
        self,
        persist_directory: str,
        threshold: float = 0.25,      # biraz daha geniş — kısa dosyalar için
    ):
        self.persist_directory = persist_directory
        self.threshold = threshold
        self._client = None
        self._collection = None
        self._embedder = None
        self._chunker = SourceFileChunker()
        # BM25 index — lazy build, disk-cached, invalidate on add/reset
        self._bm25 = None
        self._bm25_ids: List[str] = []
        self._bm25_metas: List[Dict] = []
        self._bm25_docs: List[str] = []
        # Disk cache path: persist_directory/bm25_cache.pkl
        self._bm25_cache_path = Path(persist_directory) / "bm25_cache.pkl"

    # ------------------------------------------------------------------
    # BM25 tokenizer ve index
    # ------------------------------------------------------------------

    @staticmethod
    def _bm25_tokenize(text: str) -> List[str]:
        """
        BM25 için tokenize et.
        - Alfanumerik + alt çizgi token'larını ayır (PACKAGE_PIN, spi_mosi, AB22)
        - Alt çizgili token'ları da parçalara böl (spi_mosi → spi, mosi)
        - Küçük harf: PACKAGE_PIN = package_pin = Package_Pin
        """
        full = re.findall(r'[a-zA-Z0-9_]+', text.lower())
        tokens: List[str] = []
        for t in full:
            tokens.append(t)
            if '_' in t:
                tokens.extend(p for p in t.split('_') if p)
        return tokens

    def _ensure_bm25(self):
        """
        BM25 index yoksa kur; önce disk cache'ten yükle, yoksa ChromaDB'den sıfırdan kur.
        100+ proje için kritik: 960+ chunk için yeniden tokenize etmek ~2-3 saniye sürebilir.
        Disk cache ile bu maliyet sadece ilk indexlemede ödenir.
        """
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            return  # rank-bm25 yüklü değilse sessizce atla

        col = self._get_collection()
        db_count = col.count()
        if db_count == 0:
            return

        # In-memory cache hâlâ geçerliyse atla
        if self._bm25 is not None and len(self._bm25_ids) == db_count:
            return

        # ── Disk cache'ten yükle ─────────────────────────────────────────────
        if self._bm25_cache_path.exists():
            import pickle
            try:
                with open(self._bm25_cache_path, "rb") as f:
                    cached = pickle.load(f)
                if cached.get("count") == db_count:
                    self._bm25_ids   = cached["ids"]
                    self._bm25_metas = cached["metas"]
                    self._bm25_docs  = cached["docs"]
                    self._bm25       = BM25Okapi(cached["tokenized"])
                    return  # Cache geçerli, yeniden kurmaya gerek yok
            except Exception:
                pass  # Bozuk cache → sıfırdan kur

        # ── ChromaDB'den sıfırdan kur ────────────────────────────────────────
        data = col.get(include=["documents", "metadatas"])
        self._bm25_ids   = data.get("ids", [])
        self._bm25_metas = data.get("metadatas", [])
        self._bm25_docs  = data.get("documents", [])
        tokenized = [self._bm25_tokenize(doc) for doc in self._bm25_docs]
        self._bm25 = BM25Okapi(tokenized)

        # Disk'e kaydet
        import pickle
        try:
            self._bm25_cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._bm25_cache_path, "wb") as f:
                pickle.dump({
                    "count":     db_count,
                    "ids":       self._bm25_ids,
                    "metas":     self._bm25_metas,
                    "docs":      self._bm25_docs,
                    "tokenized": tokenized,
                }, f)
        except Exception:
            pass  # Disk yazma hatası kritik değil — in-memory index hâlâ çalışır

    def _invalidate_bm25(self):
        """Yeni chunk eklenince veya reset'te BM25 index'i hem RAM'den hem diskten sıfırla."""
        self._bm25 = None
        self._bm25_ids = []
        self._bm25_metas = []
        self._bm25_docs = []
        # Disk cache geçersiz → sil, sonraki search'te yeniden build edilecek
        if self._bm25_cache_path.exists():
            try:
                self._bm25_cache_path.unlink()
            except Exception:
                pass

    def _bm25_search(
        self,
        query: str,
        n_results: int,
        project_filter: Optional[str],
        file_type_filter: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        BM25 keyword arama — filtrelenmiş alt küme üzerinde çalışır.
        Döndürülen dict'ler semantic search ile aynı yapıda; similarity yerine bm25_score.
        """
        self._ensure_bm25()
        if self._bm25 is None or not self._bm25_ids:
            return []

        # Filtre uygula
        indices = [
            i for i, m in enumerate(self._bm25_metas)
            if (not project_filter or m.get("project") == project_filter)
            and (not file_type_filter or m.get("file_type") == file_type_filter)
        ]
        if not indices:
            return []

        # BM25 skorlarını sadece filtrelenmiş subset üzerinde hesapla
        query_tokens = self._bm25_tokenize(query)
        # BM25Okapi.get_batch_scores subset için
        scores = self._bm25.get_batch_scores(query_tokens, indices)

        # (score, global_index) çiftleri, azalan sırada
        ranked = sorted(zip(scores, indices), key=lambda x: x[0], reverse=True)

        results = []
        for score, idx in ranked[:n_results]:
            if score <= 0:
                break
            meta = self._bm25_metas[idx]
            node_ids_raw = meta.get("related_node_ids", "[]")
            try:
                node_ids = json.loads(node_ids_raw) if node_ids_raw else []
            except Exception:
                node_ids = []
            results.append({
                "chunk_id":        meta.get("chunk_id", ""),
                "content":         self._bm25_docs[idx],
                "file_path":       meta.get("file_path", ""),
                "file_type":       meta.get("file_type", ""),
                "project":         meta.get("project", ""),
                "start_line":      meta.get("start_line", 0),
                "end_line":        meta.get("end_line", 0),
                "chunk_label":     meta.get("chunk_label", ""),
                "similarity":      round(score, 4),   # BM25 raw score
                "related_node_ids": node_ids,
            })
        return results

    @staticmethod
    def _rrf_merge(
        semantic: List[Dict[str, Any]],
        bm25: List[Dict[str, Any]],
        n_results: int,
        k: int = 60,
    ) -> List[Dict[str, Any]]:
        """
        Reciprocal Rank Fusion — iki listeyi rank'a göre birleştir.
        score(d) = Σ 1/(k + rank_i(d))
        """
        rrf: Dict[str, float] = {}
        best: Dict[str, Dict] = {}

        for rank, hit in enumerate(semantic, 1):
            cid = hit["chunk_id"]
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (k + rank)
            best[cid] = hit  # semantic hit'i temel al (similarity alanı var)

        for rank, hit in enumerate(bm25, 1):
            cid = hit["chunk_id"]
            rrf[cid] = rrf.get(cid, 0.0) + 1.0 / (k + rank)
            if cid not in best:
                best[cid] = hit

        # RRF skoruna göre sırala
        sorted_ids = sorted(rrf, key=lambda x: rrf[x], reverse=True)
        merged = []
        for cid in sorted_ids[:n_results]:
            hit = dict(best[cid])
            hit["rrf_score"] = round(rrf[cid], 6)
            merged.append(hit)
        return merged

    def _get_embedder(self):
        if self._embedder is None:
            from rag_v2.vector_store_v2 import VectorStoreV2
            # VectorStoreV2'nin embedder'ını paylaş
            tmp = VectorStoreV2.__new__(VectorStoreV2)
            tmp._embedder = None
            from sentence_transformers import SentenceTransformer
            import os
            # CUDA 12.1 > PyTorch max 12.0 — force CPU to avoid hang
            os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
            self._embedder = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2", device="cpu")
        return self._embedder

    def _get_collection(self):
        if self._collection is None:
            import chromadb
            self._client = chromadb.PersistentClient(path=self.persist_directory)
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def count(self) -> int:
        return self._get_collection().count()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        embedder = self._get_embedder()
        return embedder.encode(texts, batch_size=16, show_progress_bar=False).tolist()

    def add_chunks(self, chunks: List[SourceChunk], batch_size: int = 32) -> int:
        """Chunk'ları ChromaDB'ye ekle (upsert)."""
        if not chunks:
            return 0

        col = self._get_collection()
        stored = 0

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start:start + batch_size]
            texts = []
            for c in batch:
                # Embed metni: dosya adı + label + içerik
                embed_text = (
                    f"[{c.file_type.upper()}] {c.file_path} — {c.chunk_label}\n"
                    f"{c.content}"
                )
                texts.append(embed_text[:4096])  # token limiti

            try:
                embeddings = self.embed_texts(texts)
                col.upsert(
                    ids=[c.chunk_id for c in batch],
                    embeddings=embeddings,
                    documents=[c.content for c in batch],
                    metadatas=[c.to_dict() for c in batch],
                )
                stored += len(batch)
            except Exception as e:
                print(f"  [SourceChunkStore] Batch hata: {e}")

        self._invalidate_bm25()   # yeni chunk'lar → BM25 yeniden kurulacak
        return stored

    def add_file(
        self,
        file_path: str,
        project: str,
        related_node_ids: Optional[List[str]] = None,
    ) -> int:
        """Tek dosyayı chunk'layıp ekle."""
        chunks = self._chunker.chunk_file(file_path, project, related_node_ids)
        return self.add_chunks(chunks)

    def search(
        self,
        query: str,
        n_results: int = 4,
        project_filter: Optional[str] = None,
        file_type_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid arama: BM25 keyword + semantic embedding → RRF merge.

        - Semantic: ChromaDB cosine similarity (kavramsal eşleşme)
        - BM25: exact keyword match (teknik terim, pin numarası, sinyal adı)
        - RRF: iki listeyi rank'a göre parametre-free birleştir

        Her sonuç: {chunk_id, content, file_path, file_type, project,
                    start_line, end_line, chunk_label, similarity, rrf_score, related_node_ids}
        """
        col = self._get_collection()
        if col.count() == 0:
            return []

        # Çok az chunk varsa n_results'ı sınırla
        total = col.count()
        n_candidates = min(n_results * 3, total)

        # ── 1. Semantic search ───────────────────────────────────────────────
        conditions = []
        if project_filter:
            conditions.append({"project": project_filter})
        if file_type_filter:
            conditions.append({"file_type": file_type_filter})
        where = (
            {}                     if len(conditions) == 0 else
            conditions[0]          if len(conditions) == 1 else
            {"$and": conditions}
        )

        semantic_hits: List[Dict[str, Any]] = []
        try:
            embedding = self.embed_texts([query])[0]
            kwargs: Dict[str, Any] = {
                "query_embeddings": [embedding],
                "n_results": min(n_candidates, total),
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where

            raw = col.query(**kwargs)
            docs      = raw.get("documents", [[]])[0]
            metas     = raw.get("metadatas", [[]])[0]
            distances = raw.get("distances", [[]])[0]

            for doc, meta, dist in zip(docs, metas, distances):
                similarity = max(0.0, 1.0 - dist)
                if similarity < self.threshold:
                    continue
                node_ids_raw = meta.get("related_node_ids", "[]")
                try:
                    node_ids = json.loads(node_ids_raw) if node_ids_raw else []
                except Exception:
                    node_ids = []
                semantic_hits.append({
                    "chunk_id":        meta.get("chunk_id", ""),
                    "content":         doc,
                    "file_path":       meta.get("file_path", ""),
                    "file_type":       meta.get("file_type", ""),
                    "project":         meta.get("project", ""),
                    "start_line":      meta.get("start_line", 0),
                    "end_line":        meta.get("end_line", 0),
                    "chunk_label":     meta.get("chunk_label", ""),
                    "similarity":      round(similarity, 4),
                    "related_node_ids": node_ids,
                })
        except Exception as e:
            print(f"  [SourceChunkStore] Semantic search hata: {e}")

        # ── 2. BM25 search ───────────────────────────────────────────────────
        bm25_hits = self._bm25_search(query, n_candidates, project_filter, file_type_filter)

        # ── 3. RRF merge ─────────────────────────────────────────────────────
        if bm25_hits:
            merged = self._rrf_merge(semantic_hits, bm25_hits, n_results, self._RRF_K)
            # BM25 rank-1 garantisi: BM25'in en iyi eşleşmesi her zaman context'e girer.
            # Exact-keyword sorgularında (PIN adı, parametre adı, komut adı) kritik.
            bm25_top = bm25_hits[0]
            bm25_top_id = bm25_top["chunk_id"]
            if bm25_top_id not in {h["chunk_id"] for h in merged}:
                merged.append(bm25_top)
            return merged
        # BM25 yoksa (rank-bm25 kurulmamış) → sadece semantic
        return semantic_hits[:n_results]

    def search_within_file(
        self,
        query: str,
        file_stem: str,
        n_results: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Belirli bir dosyanın chunk'ları içinde semantik arama yap.
        C dosyaları için header/define chunk'larını her zaman dahil et.
        Bu sayede büyük dosyalarda (design_1.tcl gibi) sadece en ilgili
        chunk'lar context'e girer — context bloat önlenir.
        """
        col = self._get_collection()
        if col.count() == 0:
            return []
        try:
            all_data = col.get(include=["documents", "metadatas"])
        except Exception as e:
            print(f"  [SourceChunkStore] search_within_file get hata: {e}")
            return []

        # Bu dosyaya ait chunk ID'lerini ve metadata'larını topla
        stem_lower = file_stem.lower()
        file_ids: List[str] = []
        file_docs: Dict[str, str] = {}
        file_metas: Dict[str, Dict] = {}
        for cid, doc, meta in zip(
            all_data.get("ids", []),
            all_data.get("documents", []),
            all_data.get("metadatas", []),
        ):
            if stem_lower in Path(meta.get("file_path", "")).stem.lower():
                file_ids.append(cid)
                file_docs[cid] = doc
                file_metas[cid] = meta

        if not file_ids:
            return []

        # C dosyaları için header/define chunk'larını her zaman öne al
        # (#define sabitleri ve struct tanımları semantic aramada sıralamada geride kalabilir)
        _HEADER_LABELS = {"includes_defines", "global_vars"}
        pinned_ids: List[str] = []
        search_ids = list(file_ids)

        # İlk dosyanın türünü belirle
        sample_meta = file_metas[file_ids[0]]
        if sample_meta.get("file_type", "") in ("c", "cpp", "h", "hpp"):
            for cid in file_ids:
                label = file_metas[cid].get("chunk_label", "")
                if label in _HEADER_LABELS or label.startswith("typedef_struct_"):
                    pinned_ids.append(cid)
            # Pinned chunk'ları arama havuzundan çıkar
            search_ids = [cid for cid in file_ids if cid not in set(pinned_ids)]

        # Semantik arama için kalan slot sayısı
        semantic_n = max(1, n_results - len(pinned_ids))

        def _make_result(cid: str, sim: float) -> Dict[str, Any]:
            meta = file_metas[cid]
            node_ids_raw = meta.get("related_node_ids", "[]")
            try:
                node_ids = json.loads(node_ids_raw) if node_ids_raw else []
            except Exception:
                node_ids = []
            return {
                "chunk_id": cid,
                "content": file_docs[cid],
                "file_path": meta.get("file_path", ""),
                "file_type": meta.get("file_type", ""),
                "project": meta.get("project", ""),
                "start_line": meta.get("start_line", 0),
                "end_line": meta.get("end_line", 0),
                "chunk_label": meta.get("chunk_label", ""),
                "similarity": round(max(sim, 0.95), 4),
                "related_node_ids": node_ids,
            }

        # Pinned chunk'ları ekle
        results: List[Dict[str, Any]] = [_make_result(cid, 0.97) for cid in pinned_ids]
        seen_ids: set = set(pinned_ids)

        # Kalan chunk'lar içinde semantik arama
        if search_ids and semantic_n > 0:
            try:
                embedding = self.embed_texts([query])[0]
                raw = col.query(
                    query_embeddings=[embedding],
                    n_results=min(semantic_n, len(search_ids)),
                    include=["documents", "metadatas", "distances"],
                    where={"chunk_id": {"$in": search_ids}},
                )
                for doc, meta, dist in zip(
                    raw.get("documents", [[]])[0],
                    raw.get("metadatas", [[]])[0],
                    raw.get("distances", [[]])[0],
                ):
                    cid = meta.get("chunk_id", "")
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        sim = max(0.0, 1.0 - dist)
                        results.append(_make_result(cid, sim))
            except Exception as e:
                print(f"  [SourceChunkStore] search_within_file query hata: {e}")

        return results

    def search_by_filename(self, file_stem: str) -> List[Dict[str, Any]]:
        """
        Belirli bir dosyaya ait tüm chunk'ları döndür (file_path substring match).
        Küçük dosyalar (<= 8 chunk) için tümünü döndür.
        Büyük dosyalar için search_within_file() kullan.
        """
        col = self._get_collection()
        if col.count() == 0:
            return []
        try:
            all_data = col.get(include=["documents", "metadatas"])
        except Exception as e:
            print(f"  [SourceChunkStore] search_by_filename hata: {e}")
            return []

        results = []
        stem_lower = file_stem.lower()
        for doc, meta in zip(all_data.get("documents", []), all_data.get("metadatas", [])):
            fp = meta.get("file_path", "")
            if stem_lower in Path(fp).stem.lower():
                node_ids_raw = meta.get("related_node_ids", "[]")
                try:
                    node_ids = json.loads(node_ids_raw) if node_ids_raw else []
                except Exception:
                    node_ids = []
                results.append({
                    "chunk_id": meta.get("chunk_id", ""),
                    "content": doc,
                    "file_path": fp,
                    "file_type": meta.get("file_type", ""),
                    "project": meta.get("project", ""),
                    "start_line": meta.get("start_line", 0),
                    "end_line": meta.get("end_line", 0),
                    "chunk_label": meta.get("chunk_label", ""),
                    "similarity": 1.0,   # dosya adı eşleşmesi → en yüksek öncelik
                    "related_node_ids": node_ids,
                })
        return results

    def enumerate_project_chunks(
        self,
        project: str,
        file_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Bir projenin tüm chunk metadata'larını döndür (içerik yok).
        ENUMERATE sorgu modu için — top-K değil, tam liste.
        file_types: ["tcl", "xdc"] gibi filtre; None → tümü.
        """
        col = self._get_collection()
        if col.count() == 0:
            return []
        try:
            conditions: List[Dict] = [{"project": project}]
            if file_types:
                conditions.append({"file_type": {"$in": file_types}})
            where = {"$and": conditions} if len(conditions) > 1 else conditions[0]
            data = col.get(where=where, include=["metadatas"])
            return data.get("metadatas", [])
        except Exception as e:
            print(f"  [SourceChunkStore] enumerate_project_chunks hata: {e}")
            return []

    def delete_by_filepath(self, file_path: str) -> int:
        """
        Belirli bir dosyaya ait tüm chunk'ları sil.
        ChromaDB'den siler VE BM25 cache'i sıfırlar.
        Döndürür: silinen chunk sayısı.
        """
        col = self._get_collection()
        result = col.get(where={"file_path": file_path}, include=[])
        ids = result.get("ids", [])
        if ids:
            col.delete(ids=ids)
        self._invalidate_bm25()
        return len(ids)

    def reset(self):
        """Koleksiyonu sil ve yeniden oluştur."""
        import chromadb
        client = chromadb.PersistentClient(path=self.persist_directory)
        try:
            client.delete_collection(self.COLLECTION_NAME)
        except Exception:
            pass
        self._collection = None
        self._client = None
        self._invalidate_bm25()
