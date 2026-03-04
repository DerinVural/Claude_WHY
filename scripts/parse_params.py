#!/usr/bin/env python3
"""
FPGA RAG v2 — Generic Parameter Parser Agent
=============================================
Herhangi bir proje dizininden IP konfigürasyon, C define, Verilog
parametre ve PDF tablo bilgilerini otomatik çıkarır.

Kullanım:
    # Yeni proje ekle (ben çalıştırırım, sen "şu projeyi ekle" dersin):
    python scripts/parse_params.py \\
        --project-dir validation_test/MyProject \\
        --project-id PROJECT-C

    # Mevcut projeyi yeniden işle:
    python scripts/parse_params.py --project-id PROJECT-A
    python scripts/parse_params.py --project-id PROJECT-B

    # Dry-run (ne yapacağını göster, değiştirme):
    python scripts/parse_params.py --project-id PROJECT-B --dry-run

    # Sadece belirli parser'ları çalıştır:
    python scripts/parse_params.py --project-id PROJECT-B --parser tcl

Desteklenen parser'lar:
    tcl     → TCL block design → [IP CONFIG] chunk'ları
    c       → C/H dosyaları   → #define, struct, enum chunk'ları
    verilog → .v dosyaları    → parameter/localparam chunk'ları
    pdf     → PDF dosyaları   → tablo chunk'ları (--pdf-path ile)
"""

from __future__ import annotations

import re
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

GRAPH_PATH  = str(_ROOT / "db/graph/fpga_rag_v2_graph.json")
CHROMA_PATH = str(_ROOT / "db/chroma_source_chunks")

# Bilinen proje dizinleri (--project-id tek başına kullanılırsa buradan alınır)
_VT = "/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test"

KNOWN_PROJECTS: Dict[str, str] = {
    "nexys_a7_dma_audio":   str(_ROOT / "data/code/Nexys-A7-100T-DMA-Audio"),
    "axi_gpio_example":     f"{_VT}/axi_example",
    "gtx_ddr_example":      f"{_VT}/gtx_ddr_example",
    "i2c_example":          f"{_VT}/i2c_example",
    "pcie_dma_ddr_example": f"{_VT}/pcie_dma_ddr_example",
    "pcie_xdma_mb_example": f"{_VT}/pcie_xdma_mb_example",
    "rgmii_example":        f"{_VT}/rgmii_example",
    "spi_example":          f"{_VT}/spi_example",
    "uart_example":         f"{_VT}/uart_example",
    "v2_mig":               f"{_VT}/v2_mig",
    "v3_gtx":               f"{_VT}/v3_gtx",
}

# Gürültülü CONFIG anahtarları — timing/jitter değerleri atlanır
_TCL_SKIP_KEYS = {
    "CLKOUT1_JITTER", "CLKOUT2_JITTER", "CLKOUT3_JITTER", "CLKOUT4_JITTER",
    "CLKOUT1_PHASE_ERROR", "CLKOUT2_PHASE_ERROR", "CLKOUT3_PHASE_ERROR",
    "MMCM_CLKFBOUT_MULT_F", "MMCM_CLKOUT0_DIVIDE_F", "MMCM_CLKOUT1_DIVIDE",
    "MMCM_CLKOUT2_DIVIDE", "MMCM_DIVCLK_DIVIDE",
    "Full_Threshold_Assert_Value", "Full_Threshold_Negate_Value",
    "Write_Data_Count_Width", "Read_Data_Count_Width", "Data_Count_Width",
}


# ═════════════════════════════════════════════════════════════════════════════
# Graph'tan otomatik node map oluştur
# ═════════════════════════════════════════════════════════════════════════════

def build_node_map(project_id: str) -> Dict[str, str]:
    """
    Graph'taki COMP node'larını okuyarak ip_instance_name → node_id map'i döndürür.
    Hardcoded mapping'e gerek yok — graph zaten hangi IP'nin hangi node olduğunu bilir.

    Örnek:
        COMP-B-axi_gpio_0  → {"axi_gpio_0": "COMP-B-axi_gpio_0"}
        COMP-A-axi_dma_0   → {"axi_dma_0":  "COMP-A-axi_dma_0"}
    """
    from rag_v2.graph_store import GraphStore
    gs = GraphStore(persist_path=GRAPH_PATH)
    node_map: Dict[str, str] = {}

    for item in gs.get_all_nodes():
        nid   = item.get("node_id", "")
        attrs = gs.get_node(nid) or {}
        node_project = attrs.get("project", "")

        # COMP-{PROJE}-{instance} formatını çöz
        # Hem "COMP-A-axi_dma_0" hem "COMP-B-axi_gpio_0" gibi ID'leri destekle
        if not nid.startswith("COMP-"):
            continue

        # Proje filtresi: node'un projesi eşleşmeli
        # Graph'ta project field varsa kullan, yoksa ID prefix'ten tahmin et
        proj_tag = project_id.replace("PROJECT-", "")  # "A" veya "B" veya "C"
        if node_project and node_project != project_id:
            continue
        if not node_project:
            # project field yoksa ID'den çıkar: COMP-A-... → "A"
            parts = nid.split("-", 2)
            if len(parts) >= 2 and parts[1] != proj_tag:
                continue

        # instance name: COMP-A-axi_dma_0 → "axi_dma_0"
        parts = nid.split("-", 2)
        if len(parts) == 3:
            instance = parts[2]
        else:
            instance = nid

        # Hem tam instance adı hem de kısa versiyonunu ekle
        node_map[instance] = nid
        # Bazen TCL'de farklı isim olabilir — name field varsa onu da ekle
        name_field = attrs.get("name", "")
        if name_field and name_field != instance and name_field != nid:
            node_map[name_field] = nid

    return node_map


# ═════════════════════════════════════════════════════════════════════════════
# PARSER 1 — TCL Block Design IP Config
# ═════════════════════════════════════════════════════════════════════════════

def find_tcl_files(project_dir: Path) -> List[Path]:
    """
    Proje dizininde BD-TCL dosyalarını bul.
    create_bd_cell komutu içeren TCL'ler IP config kaynağıdır.
    """
    candidates = []
    for tcl in project_dir.rglob("*.tcl"):
        try:
            content = tcl.read_text(encoding="utf-8", errors="replace")
            if "create_bd_cell" in content and "-type ip" in content:
                candidates.append(tcl)
        except Exception:
            pass
    return candidates


def parse_tcl(tcl_path: Path) -> List[Dict[str, Any]]:
    """
    Bir TCL block design dosyasını parse eder.
    Her IP instance için: {ip_name, vlnv, params, file_path} döndürür.
    """
    content = tcl_path.read_text(encoding="utf-8", errors="replace")
    results = []

    # Pattern 1: "set NAME [ create_bd_cell -type ip -vlnv VLNV NAME ]"
    create_re = re.compile(
        r'set\s+(\w+)\s*\[\s*create_bd_cell\s+-type\s+ip\s+-vlnv\s+([\w.:/]+)\s+\1\s*\]',
        re.MULTILINE,
    )
    # Pattern 2: "create_bd_cell -type ip -vlnv VLNV NAME" (set olmadan)
    create_re2 = re.compile(
        r'create_bd_cell\s+-type\s+ip\s+-vlnv\s+([\w.:/]+)\s+(\w+)',
        re.MULTILINE,
    )
    # Pattern A: set_property -dict [ list ... ] $instance
    prop_block_re_var = re.compile(
        r'set_property\s+-dict\s*\[\s*list\s*(.*?)\]\s*\$(\w+)',
        re.DOTALL,
    )
    # Pattern B: set_property -dict [list ...] [get_bd_cells instance]
    prop_block_re_get = re.compile(
        r'set_property\s+-dict\s*\[list\s*(.*?)\]\s*\[get_bd_cells\s+(\w+)\]',
        re.DOTALL,
    )
    kv_re = re.compile(r'CONFIG\.(\w+)\s+\{([^}]*)\}')

    ip_map: Dict[str, Dict] = {}

    # Pattern 1: set NAME [ create_bd_cell ... NAME ]
    for m in create_re.finditer(content):
        ip_name, vlnv = m.group(1), m.group(2)
        ip_map[ip_name] = {"vlnv": vlnv, "params": {}}

    # Pattern 2: create_bd_cell ... VLNV NAME (set olmadan)
    for m in create_re2.finditer(content):
        vlnv, ip_name = m.group(1), m.group(2)
        if ip_name not in ip_map:
            ip_map[ip_name] = {"vlnv": vlnv, "params": {}}

    # CONFIG parametrelerini çek — hem $var hem [get_bd_cells] formatı
    for prop_re in (prop_block_re_var, prop_block_re_get):
        for m in prop_re.finditer(content):
            block, instance = m.group(1), m.group(2)
            if instance not in ip_map:
                continue
            for kv in kv_re.finditer(block):
                key, val = kv.group(1), kv.group(2).strip()
                if key not in _TCL_SKIP_KEYS:
                    ip_map[instance]["params"][key] = val

    for ip_name, data in ip_map.items():
        if not data["params"]:
            continue
        results.append({
            "ip_name":   ip_name,
            "vlnv":      data["vlnv"],
            "params":    data["params"],
            "file_path": str(tcl_path),
        })

    return results


def tcl_to_chunks(tcl_results: List[Dict], project_id: str,
                  node_map: Dict[str, str]) -> List:
    from rag_v2.source_chunk_store import SourceChunk

    chunks = []
    for ip in tcl_results:
        ip_name  = ip["ip_name"]
        vlnv     = ip["vlnv"]
        params   = ip["params"]
        fp       = ip["file_path"]

        # Graph node_id'yi otomatik bul
        node_id  = node_map.get(ip_name, "")
        node_ids = [node_id] if node_id else []

        param_lines = "\n".join(f"  {k} = {v}" for k, v in sorted(params.items()))
        content = (
            f"[IP CONFIG] {ip_name} ({vlnv})\n"
            f"Kaynak: {Path(fp).name}\n\n"
            f"{param_lines}"
        )

        # chunk_id: proje prefix'i ile çakışma önlenir
        proj_tag = project_id.replace("PROJECT-", "").lower()
        chunk_id = f"tcl_params_{proj_tag}_{ip_name}" if proj_tag != "a" else f"tcl_params_{ip_name}"

        chunks.append(SourceChunk(
            chunk_id         = chunk_id,
            content          = content[:3000],
            file_path        = fp,
            file_type        = "params",
            project          = project_id,
            start_line       = 0,
            end_line         = 0,
            chunk_label      = f"IP CONFIG: {ip_name}",
            related_node_ids = node_ids,
        ))
    return chunks


# ═════════════════════════════════════════════════════════════════════════════
# PARSER 2 — C Defines + Structs
# ═════════════════════════════════════════════════════════════════════════════

def find_c_files(project_dir: Path) -> List[Path]:
    c_files = list(project_dir.rglob("*.c")) + list(project_dir.rglob("*.h"))
    # Gereksiz dosyaları filtrele
    skip_patterns = ["auto_", "xparameters", "mb_interface", "sleep", "xil_"]
    return [
        f for f in c_files
        if not any(s in f.name.lower() for s in skip_patterns)
        and f.stat().st_size > 0
    ]


def parse_c(c_path: Path) -> Dict[str, Any]:
    content = c_path.read_text(encoding="utf-8", errors="replace")
    result: Dict[str, Any] = {
        "file_path": str(c_path),
        "defines":   {},
        "structs":   {},
        "enums":     {},
    }

    define_re = re.compile(r'^#define\s+(\w+)\s+(.+)$', re.MULTILINE)
    for m in define_re.finditer(content):
        name, val = m.group(1).strip(), m.group(2).strip()
        if not val.startswith("(") or any(c.isdigit() for c in val):
            result["defines"][name] = val

    struct_re = re.compile(
        r'typedef\s+struct\s+\w*\s*\{([^}]+)\}\s*(\w+)\s*;', re.DOTALL)
    for m in struct_re.finditer(content):
        body, name = m.group(1), m.group(2)
        fields = [
            line.strip().rstrip(";").strip()
            for line in body.splitlines()
            if line.strip() and not line.strip().startswith(("//", "/*"))
        ]
        if fields:
            result["structs"][name] = fields

    enum_re = re.compile(
        r'typedef\s+enum\s+\w*\s*\{([^}]+)\}\s*(\w+)\s*;', re.DOTALL)
    for m in enum_re.finditer(content):
        body, name = m.group(1), m.group(2)
        result["enums"][name] = [v.strip() for v in body.split(",") if v.strip()]

    return result


def c_to_chunks(c_results: List[Dict], project_id: str,
                node_map: Dict[str, str]) -> List:
    from rag_v2.source_chunk_store import SourceChunk
    chunks = []
    for res in c_results:
        fp    = res["file_path"]
        fname = Path(fp).name

        if not (res["defines"] or res["structs"] or res["enums"]):
            continue

        node_id  = node_map.get(Path(fp).stem, "")
        node_ids = [node_id] if node_id else []

        lines = [f"[C TANIMLAR] {fname}\n"]
        if res["defines"]:
            lines.append("## #define Sabitleri")
            for k, v in res["defines"].items():
                lines.append(f"  #define {k} = {v}")
        if res["enums"]:
            lines.append("\n## enum Tipleri")
            for name, vals in res["enums"].items():
                lines.append(f"  {name}: {', '.join(vals)}")
        if res["structs"]:
            lines.append("\n## struct Tipleri")
            for name, fields in res["structs"].items():
                lines.append(f"  struct {name}:")
                for f in fields:
                    lines.append(f"    {f}")

        proj_tag = project_id.replace("PROJECT-", "").lower()
        stem     = Path(fp).stem
        suffix   = Path(fp).suffix.lstrip(".")

        chunks.append(SourceChunk(
            chunk_id         = f"c_params_{proj_tag}_{stem}_{suffix}",
            content          = "\n".join(lines)[:3000],
            file_path        = fp,
            file_type        = "params",
            project          = project_id,
            start_line       = 0,
            end_line         = 0,
            chunk_label      = f"C Tanımlar: {fname}",
            related_node_ids = node_ids,
        ))
    return chunks


# ═════════════════════════════════════════════════════════════════════════════
# PARSER 3 — Verilog Parameters
# ═════════════════════════════════════════════════════════════════════════════

def find_verilog_files(project_dir: Path) -> List[Path]:
    return list(project_dir.rglob("*.v")) + list(project_dir.rglob("*.sv"))


def parse_verilog(v_path: Path) -> Dict[str, Any]:
    content = v_path.read_text(encoding="utf-8", errors="replace")
    result: Dict[str, Any] = {
        "file_path":   str(v_path),
        "module":      "",
        "parameters":  {},
        "localparams": {},
    }

    mod_m = re.search(r'\bmodule\s+(\w+)', content)
    if mod_m:
        result["module"] = mod_m.group(1)

    param_re = re.compile(
        r'\bparameter\s+(?:\w+\s+)?(\w+)\s*=\s*([^,;\n)]+)', re.MULTILINE)
    for m in param_re.finditer(content):
        name = m.group(1).strip()
        val  = re.sub(r'//.*', '', m.group(2)).strip().rstrip(',').strip()
        result["parameters"][name] = val

    local_re = re.compile(
        r'\blocalparam\s+(?:\w+\s+)?(\w+)\s*=\s*([^;]+);', re.MULTILINE)
    for m in local_re.finditer(content):
        name = m.group(1).strip()
        val  = re.sub(r'//.*', '', m.group(2)).strip()
        result["localparams"][name] = val

    return result


def verilog_to_chunks(v_results: List[Dict], project_id: str,
                      node_map: Dict[str, str]) -> List:
    from rag_v2.source_chunk_store import SourceChunk
    chunks = []
    for res in v_results:
        module = res["module"]
        fp     = res["file_path"]
        params = res["parameters"]
        locs   = res["localparams"]

        if not params and not locs:
            continue

        node_id  = node_map.get(module, node_map.get(Path(fp).stem, ""))
        node_ids = [node_id] if node_id else []

        lines = [f"[VERILOG PARAMETRELER] module {module}\nKaynak: {Path(fp).name}\n"]
        if params:
            lines.append("## parameter")
            for k, v in params.items():
                lines.append(f"  parameter {k} = {v}")
        if locs:
            lines.append("\n## localparam")
            for k, v in locs.items():
                lines.append(f"  localparam {k} = {v}")

        proj_tag = project_id.replace("PROJECT-", "").lower()
        chunks.append(SourceChunk(
            chunk_id         = f"verilog_params_{proj_tag}_{module}",
            content          = "\n".join(lines)[:3000],
            file_path        = fp,
            file_type        = "params",
            project          = project_id,
            start_line       = 0,
            end_line         = 0,
            chunk_label      = f"Verilog Params: {module}",
            related_node_ids = node_ids,
        ))
    return chunks


# ═════════════════════════════════════════════════════════════════════════════
# PARSER 4 — PDF Tables (opsiyonel, --pdf-path ile)
# ═════════════════════════════════════════════════════════════════════════════

def parse_pdf_tables(pdf_path: Path, pages_spec: Optional[str] = None) -> List[Dict]:
    """
    PDF'den tablo satırlarını çıkarır.
    pages_spec: "6,8,11" veya None (tüm sayfa)
    """
    try:
        import fitz
    except ImportError:
        print("  UYARI: PyMuPDF kurulu değil. PDF parser atlanıyor.")
        return []

    doc = fitz.open(str(pdf_path))
    total = len(doc)

    if pages_spec:
        pages = [int(p) for p in pages_spec.split(",") if p.strip().isdigit()]
    else:
        pages = list(range(1, total + 1))

    results = []
    for pg_num in pages:
        if pg_num - 1 >= total:
            continue
        text = doc[pg_num - 1].get_text("text")
        rows = []
        for line in text.splitlines():
            parts = re.split(r'\t|  {2,}', line.strip(), maxsplit=1)
            if len(parts) == 2:
                k, v = parts[0].strip(), parts[1].strip()
                if k and v and len(k) > 1:
                    rows.append((k, v))
        if rows or text.strip():
            results.append({
                "page":     pg_num,
                "title":    f"Page {pg_num}",
                "rows":     rows,
                "raw_text": text.strip()[:2000] if not rows else "",
            })

    doc.close()
    return results


def pdf_to_chunks(pdf_results: List[Dict], pdf_path: Path,
                  project_id: str) -> List:
    from rag_v2.source_chunk_store import SourceChunk
    chunks = []
    proj_tag = project_id.replace("PROJECT-", "").lower()

    for res in pdf_results:
        page  = res["page"]
        title = res["title"]
        rows  = res["rows"]
        raw   = res["raw_text"]

        if rows:
            lines = [f"[PDF TABLO] {title}\nKaynak: {pdf_path.name} sayfa {page}\n"]
            for k, v in rows:
                lines.append(f"  {k} = {v}")
            content = "\n".join(lines)
        else:
            content = f"[PDF BÖLÜM] {title}\nKaynak: {pdf_path.name} sayfa {page}\n\n{raw}"

        if not content.strip():
            continue

        slug = re.sub(r'[^a-z0-9]+', '_', title.lower())[:30]
        chunks.append(SourceChunk(
            chunk_id         = f"pdf_{proj_tag}_p{page}_{slug}",
            content          = content[:3000],
            file_path        = str(pdf_path),
            file_type        = "params",
            project          = project_id,
            start_line       = page,
            end_line         = page,
            chunk_label      = f"PDF: {title}",
            related_node_ids = [],
        ))
    return chunks


# ═════════════════════════════════════════════════════════════════════════════
# Graph Node Güncelleme
# ═════════════════════════════════════════════════════════════════════════════

def update_graph_nodes(tcl_results: List[Dict], v_results: List[Dict],
                       node_map: Dict[str, str], dry_run: bool = False) -> int:
    from rag_v2.graph_store import GraphStore
    gs = GraphStore(persist_path=GRAPH_PATH)
    updated = 0

    # TCL → graph node description'a extracted_params ekle
    for ip in tcl_results:
        ip_name   = ip["ip_name"]
        node_id   = node_map.get(ip_name, "")
        if not node_id:
            continue
        node = gs.get_node(node_id)
        if not node:
            continue

        param_str = ", ".join(
            f"{k}={v}" for k, v in sorted(ip["params"].items())
        )
        desc = node.get("description", "")
        if "extracted_params:" not in desc:
            new_desc = desc.rstrip() + f"\nextracted_params: {param_str}"
        else:
            new_desc = re.sub(r'extracted_params:.*', f'extracted_params: {param_str}', desc)

        if not dry_run:
            gs.add_node(node_id, {**node, "description": new_desc})
        print(f"  [GRAPH] {node_id}: params güncellendi")
        updated += 1

    # Verilog → graph node description'a verilog_params ekle
    for res in v_results:
        module  = res["module"]
        node_id = node_map.get(module, node_map.get(Path(res["file_path"]).stem, ""))
        if not node_id:
            continue
        node = gs.get_node(node_id)
        if not node:
            continue

        all_params = {**res["parameters"], **res["localparams"]}
        if not all_params:
            continue

        param_str = ", ".join(f"{k}={v}" for k, v in all_params.items())
        desc = node.get("description", "")
        if "verilog_params:" not in desc:
            new_desc = desc.rstrip() + f"\nverilog_params: {param_str}"
        else:
            new_desc = re.sub(r'verilog_params:.*', f'verilog_params: {param_str}', desc)

        if not dry_run:
            gs.add_node(node_id, {**node, "description": new_desc})
        print(f"  [GRAPH] {node_id}: verilog params güncellendi")
        updated += 1

    return updated


# ═════════════════════════════════════════════════════════════════════════════
# Ana işlev
# ═════════════════════════════════════════════════════════════════════════════

def run(
    project_id:  str,
    project_dir: Optional[Path] = None,
    parsers:     Optional[List[str]] = None,
    pdf_path:    Optional[Path] = None,
    pdf_pages:   Optional[str] = None,
    dry_run:     bool = False,
):
    # Proje dizinini belirle
    if project_dir is None:
        if project_id in KNOWN_PROJECTS:
            project_dir = Path(KNOWN_PROJECTS[project_id])
        else:
            print(f"HATA: --project-dir belirtilmedi ve '{project_id}' KNOWN_PROJECTS'ta yok.")
            print(f"Bilinen projeler: {list(KNOWN_PROJECTS.keys())}")
            sys.exit(1)

    if not project_dir.exists():
        print(f"HATA: Proje dizini bulunamadı: {project_dir}")
        sys.exit(1)

    all_parsers = ["tcl", "c", "verilog", "pdf"]
    run_parsers = parsers if parsers else all_parsers

    print("=" * 70)
    print(f"  FPGA RAG v2 — Parameter Parser Agent")
    print(f"  Proje  : {project_id}")
    print(f"  Dizin  : {project_dir}")
    print(f"  Parser : {run_parsers}")
    if dry_run:
        print("  MOD    : DRY-RUN (değişiklik yapılmaz)")
    print("=" * 70)

    # Graph'tan node map'i otomatik kur
    print("\n[0] Graph'tan node map oluşturuluyor...")
    node_map = build_node_map(project_id)
    print(f"  {len(node_map)} COMP node bulundu: {list(node_map.keys())[:8]}{'...' if len(node_map) > 8 else ''}")

    all_chunks   = []
    tcl_results  = []
    v_results    = []

    # ── 1. TCL Parser ─────────────────────────────────────────────────────────
    if "tcl" in run_parsers:
        print("\n[1/4] TCL IP Config Parser")
        tcl_files = find_tcl_files(project_dir)
        print(f"  {len(tcl_files)} TCL dosyası bulundu:")
        for tf in tcl_files:
            print(f"    {tf.relative_to(project_dir)}")

        for tcl_path in tcl_files:
            ips = parse_tcl(tcl_path)
            if ips:
                print(f"  {tcl_path.name}: {len(ips)} IP instance")
                for ip in ips:
                    mapped = node_map.get(ip["ip_name"], "—")
                    print(f"    {ip['ip_name']:35s} {len(ip['params'])} param  → {mapped}")
                tcl_results.extend(ips)

        # Aynı IP birden fazla TCL dosyasında olabilir — parametreleri merge et
        # (daha fazla param içeren dosya kaynak olarak gösterilir)
        merged: Dict[str, Dict] = {}
        for ip in tcl_results:
            name = ip["ip_name"]
            if name not in merged:
                merged[name] = ip.copy()
            else:
                # Daha fazla param varsa üzerine yaz, yoksa ekle
                for k, v in ip["params"].items():
                    if k not in merged[name]["params"]:
                        merged[name]["params"][k] = v
                if len(ip["params"]) > len(merged[name]["params"]):
                    merged[name]["file_path"] = ip["file_path"]
        tcl_results = list(merged.values())
        print(f"  (Merge sonrası: {len(tcl_results)} benzersiz IP)")

        chunks = tcl_to_chunks(tcl_results, project_id, node_map)
        all_chunks.extend(chunks)
        print(f"  → {len(chunks)} [IP CONFIG] chunk oluşturuldu")

    # ── 2. C Parser ───────────────────────────────────────────────────────────
    if "c" in run_parsers:
        print("\n[2/4] C Defines Parser")
        c_files = find_c_files(project_dir)
        print(f"  {len(c_files)} C/H dosyası taranıyor")
        c_results_list = []
        for cf in c_files:
            res = parse_c(cf)
            total = len(res["defines"]) + len(res["structs"]) + len(res["enums"])
            if total > 0:
                print(f"    {cf.name:35s} {len(res['defines'])} define, "
                      f"{len(res['structs'])} struct, {len(res['enums'])} enum")
                c_results_list.append(res)

        chunks = c_to_chunks(c_results_list, project_id, node_map)
        all_chunks.extend(chunks)
        print(f"  → {len(chunks)} [C TANIMLAR] chunk oluşturuldu")

    # ── 3. Verilog Parser ─────────────────────────────────────────────────────
    if "verilog" in run_parsers:
        print("\n[3/4] Verilog Parameter Parser")
        v_files = find_verilog_files(project_dir)
        print(f"  {len(v_files)} Verilog dosyası taranıyor")
        for vf in v_files:
            res = parse_verilog(vf)
            if res["parameters"] or res["localparams"]:
                print(f"    {vf.name:35s} {len(res['parameters'])} param, "
                      f"{len(res['localparams'])} localparam")
                v_results.append(res)

        chunks = verilog_to_chunks(v_results, project_id, node_map)
        all_chunks.extend(chunks)
        print(f"  → {len(chunks)} [VERILOG PARAMETRELER] chunk oluşturuldu")

    # ── 4. PDF Parser ─────────────────────────────────────────────────────────
    if "pdf" in run_parsers and pdf_path:
        print("\n[4/4] PDF Table Parser")
        if pdf_path.exists():
            pdf_results = parse_pdf_tables(pdf_path, pdf_pages)
            print(f"  {len(pdf_results)} sayfa işlendi")
            chunks = pdf_to_chunks(pdf_results, pdf_path, project_id)
            all_chunks.extend(chunks)
            print(f"  → {len(chunks)} [PDF TABLO] chunk oluşturuldu")
        else:
            print(f"  UYARI: PDF bulunamadı: {pdf_path}")
    elif "pdf" in run_parsers and not pdf_path:
        print("\n[4/4] PDF Parser — atlandı (--pdf-path belirtilmedi)")

    # ── Graph güncellemeleri ──────────────────────────────────────────────────
    print(f"\n[GRAPH] Node güncellemeleri...")
    n_updated = update_graph_nodes(tcl_results, v_results, node_map, dry_run=dry_run)
    print(f"  {n_updated} node güncellendi")

    # ── ChromaDB'ye ekle ──────────────────────────────────────────────────────
    print(f"\n[STORE] {len(all_chunks)} chunk ChromaDB'ye ekleniyor...")

    if dry_run:
        print("  [DRY-RUN] Hiçbir değişiklik yapılmadı.")
        print(f"\n  Chunk listesi:")
        for c in all_chunks:
            print(f"    [{c.file_type:8s}] {c.chunk_label:45s}  {c.chunk_id}")
        return

    if not all_chunks:
        print("  Eklenecek chunk yok.")
        return

    from rag_v2.source_chunk_store import SourceChunkStore
    store  = SourceChunkStore(persist_directory=CHROMA_PATH)
    before = store.count()
    added  = store.add_chunks(all_chunks)
    after  = store.count()

    print(f"  Eklenen : {added}")
    print(f"  ChromaDB: {before} → {after} chunk")
    print(f"\n  ✅ {project_id} parser tamamlandı!")


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="FPGA RAG v2 — Generic Parameter Parser Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  # PROJECT-B'yi işle (bilinen proje, dizin otomatik):
  python scripts/parse_params.py --project-id PROJECT-B

  # Yeni bir proje ekle:
  python scripts/parse_params.py --project-dir /path/to/project --project-id PROJECT-C

  # Sadece TCL parser, dry-run:
  python scripts/parse_params.py --project-id PROJECT-B --parser tcl --dry-run

  # PDF ile birlikte:
  python scripts/parse_params.py --project-id PROJECT-A --pdf-path ~/Documents/nexys-a7_rm.pdf --pdf-pages 6,8,11
        """,
    )
    ap.add_argument("--project-id",  required=True,
                    help="Proje kimliği (ör. PROJECT-A, PROJECT-B, PROJECT-C)")
    ap.add_argument("--project-dir", type=Path, default=None,
                    help="Proje kök dizini (belirtilmezse KNOWN_PROJECTS'tan alınır)")
    ap.add_argument("--parser", choices=["tcl", "c", "verilog", "pdf"],
                    action="append", dest="parsers",
                    help="Çalıştırılacak parser'lar (tekrar edilebilir, varsayılan: hepsi)")
    ap.add_argument("--pdf-path",  type=Path, default=None,
                    help="PDF dosyası yolu (pdf parser için gerekli)")
    ap.add_argument("--pdf-pages", type=str, default=None,
                    help="İşlenecek PDF sayfaları, virgülle ayrılmış (ör. 6,8,11)")
    ap.add_argument("--dry-run",   action="store_true",
                    help="Değişiklik yapmadan ne yapacağını göster")

    args = ap.parse_args()
    run(
        project_id  = args.project_id,
        project_dir = args.project_dir,
        parsers     = args.parsers,
        pdf_path    = args.pdf_path,
        pdf_pages   = args.pdf_pages,
        dry_run     = args.dry_run,
    )
