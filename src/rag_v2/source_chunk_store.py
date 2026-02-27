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
    """

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

            chunk_id = f"{Path(file_path).stem}_{label}"
            chunks.append(SourceChunk(
                chunk_id=chunk_id,
                content=text[:MAX_CHUNK_CHARS],
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

            # Büyük fonksiyonları böl
            if len(text) > MAX_CHUNK_CHARS:
                for j, sub in enumerate(self._split_text(text)):
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
                    content=text,
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
            return [SourceChunk(
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

        chunks: List[SourceChunk] = []
        last_pos = 0

        for i, m in enumerate(matches):
            # struct öncesi içerik (includes + defines)
            pre = header_text[last_pos:m.start()].strip()
            if pre and i == 0:
                chunks.append(SourceChunk(
                    chunk_id=f"{file_prefix}_headers_pre",
                    content=pre[:MAX_CHUNK_CHARS],
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
        if len(content) <= MAX_CHUNK_CHARS:
            return self._whole_file_chunk(content, file_path, "xdc", project, node_ids)

        # Büyük XDC: ## başlıklı bölümlere göre böl
        # NOTE: Some XDC files use "## Section" (with space) and some "##Section" (no space)
        # Ayrıca "#PWM Audio Amplifier" gibi tek-hash subsection başlıkları da bölünüyor:
        # ^#(?=[A-Z]) — tek # + büyük harf (commented set_property'ler küçük harf ile başlar)
        chunks = []
        sections = re.split(r'(?m)^##\s*|^#(?=[A-Z])', content)
        for i, sec in enumerate(sections):
            if not sec.strip():
                continue
            first_line = sec.split("\n")[0].strip()
            label = re.sub(r'[^\w\s]', '', first_line)[:40] or f"section_{i}"
            start_line = content[:content.find(sec)].count("\n") + 1 if sec in content else 0
            end_line = start_line + sec.count("\n")
            chunks.append(SourceChunk(
                chunk_id=f"{Path(file_path).stem}_{i}_{label.replace(' ','_')}",
                content=sec[:MAX_CHUNK_CHARS],
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
                    # Each IP instance block
                    for ii, im in enumerate(inst_matches):
                        ip_name = im.group(1)
                        blk_start = im.start()
                        blk_end = inst_matches[ii + 1].start() if ii + 1 < len(inst_matches) else len(proc_body)
                        blk = proc_body[blk_start:blk_end].strip()
                        blk_sl = sl + proc_body[:blk_start].count("\n")
                        blk_el = sl + proc_body[:blk_end].count("\n")
                        for j, sub in enumerate(self._split_text(blk) if len(blk) > MAX_CHUNK_CHARS else [blk]):
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
    Kaynak dosya chunk'larının ChromaDB vektör deposu.

    Architecture: fpga_rag_architecture_v2.md — 4th store eki.
    Graph node store  → mimari metadata
    Source chunk store → implementasyon detayı (RTL, SW, XDC, TCL)
    """

    COLLECTION_NAME = "source_chunks"

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

    def _get_embedder(self):
        if self._embedder is None:
            from rag_v2.vector_store_v2 import VectorStoreV2
            # VectorStoreV2'nin embedder'ını paylaş
            tmp = VectorStoreV2.__new__(VectorStoreV2)
            tmp._embedder = None
            from sentence_transformers import SentenceTransformer
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._embedder = SentenceTransformer("all-mpnet-base-v2", device=device)
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
        Semantic arama.
        Her sonuç: {chunk_id, content, file_path, file_type, project,
                    start_line, end_line, chunk_label, similarity, related_node_ids}
        """
        col = self._get_collection()
        if col.count() == 0:
            return []

        where = {}
        if project_filter:
            where["project"] = project_filter
        if file_type_filter:
            where["file_type"] = file_type_filter

        try:
            embedding = self.embed_texts([query])[0]
            kwargs: Dict[str, Any] = {
                "query_embeddings": [embedding],
                "n_results": min(n_results, col.count()),
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where

            raw = col.query(**kwargs)
        except Exception as e:
            print(f"  [SourceChunkStore] Search hata: {e}")
            return []

        results = []
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

            results.append({
                "chunk_id": meta.get("chunk_id", ""),
                "content": doc,
                "file_path": meta.get("file_path", ""),
                "file_type": meta.get("file_type", ""),
                "project": meta.get("project", ""),
                "start_line": meta.get("start_line", 0),
                "end_line": meta.get("end_line", 0),
                "chunk_label": meta.get("chunk_label", ""),
                "similarity": round(similarity, 4),
                "related_node_ids": node_ids,
            })

        return results

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
