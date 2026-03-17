#!/usr/bin/env python3
"""
check_doc_coverage.py — Source-Driven DocStore Kapsam Analizi
=============================================================
Kaynak dosyalardaki IP VLNV'lerini tara → her IP için gerekli Xilinx
dokümantasyonunu kontrol et → DocStore'da eksik olanları raporla.

Bu script soru-bağımsızdır: boşluklar sorudan değil, kaynak koddan türetilir.
Yeni proje eklendiğinde çalıştır → hangi PDF'lerin eklenmesi gerektiği görünür.

Kullanım:
    cd /home/test123/GC-RAG-VIVADO-2
    source .venv/bin/activate
    python scripts/check_doc_coverage.py           # tam rapor
    python scripts/check_doc_coverage.py --missing # sadece eksikler
    python scripts/check_doc_coverage.py --json    # makine-okunabilir çıktı
"""

import argparse
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

# ─────────────────────────────────────────────────────────────────────────────
# IP → Xilinx Dokümantasyonu eşleme tablosu
#
# Kural: Her Xilinx IP'nin resmi Product Guide (PG) veya User Guide (UG) vardır.
# Bu tablo domain bilgisidir — soru bağımsız, IP ismine göre belirlenir.
# Yeni IP eklendiğinde buraya eklenir; yeni soru sormak gerekmez.
# ─────────────────────────────────────────────────────────────────────────────

IP_TO_DOCS: dict[str, list[tuple[str, str]]] = {
    # ── Saat & Reset ──────────────────────────────────────────────────────────
    "clk_wiz":               [("pg065", "Clocking Wizard PG"),
                               ("ug572", "7-Series Clocking Resources")],
    "proc_sys_reset":        [("pg164", "Processor System Reset Module PG")],

    # ── MicroBlaze işlemci ailesi ─────────────────────────────────────────────
    "microblaze":            [("ug984", "MicroBlaze Processor Reference"),
                               ("ug898", "Embedded Processor HW Design (UG1579)")],
    "microblaze_mcs":        [("pg048", "MicroBlaze MCS PG"),
                               ("ug984", "MicroBlaze Processor Reference")],
    "mdm":                   [("pg115", "MicroBlaze Debug Module PG"),
                               ("pg062", "MicroBlaze Debug Module PG (legacy v2.10)")],
    "lmb_bram_if_cntlr":     [("ug984", "MicroBlaze Processor Reference")],
    "lmb_v10":               [("ug984", "MicroBlaze Processor Reference")],

    # ── AXI Interconnect & Bus ────────────────────────────────────────────────
    "axi_interconnect":      [("pg059", "AXI Interconnect PG")],
    "smartconnect":          [("pg247", "SmartConnect PG")],
    "axi_register_slice":    [("pg373", "AXI Register Slice PG")],

    # ── AXI Periferaller ──────────────────────────────────────────────────────
    "axi_gpio":              [("pg144", "AXI GPIO PG")],
    "axi_uartlite":          [("pg142", "AXI UartLite PG")],
    "axi_iic":               [("pg090", "AXI IIC PG")],
    "axi_spi":               [("pg153", "AXI Quad SPI PG")],
    "axi_timer":             [("pg079", "AXI Timer PG")],
    "axi_intc":              [("pg099", "AXI Interrupt Controller PG")],
    "axi_bram_ctrl":         [("pg078", "AXI BRAM Controller PG")],

    # ── AXI DMA & Streaming ───────────────────────────────────────────────────
    "axi_dma":               [("pg021", "AXI DMA PG")],
    "axi_vdma":              [("pg020", "AXI VDMA PG")],
    "axis_subset_converter": [("pg085", "AXI4-Stream Infrastructure IP Suite PG")],
    "axis_data_fifo":        [("pg085", "AXI4-Stream Data FIFO PG")],

    # ── Bellek ────────────────────────────────────────────────────────────────
    "mig_7series":           [("ug586", "7-Series MIG UG")],
    "blk_mem_gen":           [("pg058", "Block Memory Generator PG")],
    "fifo_generator":        [("pg057", "FIFO Generator PG")],

    # ── PCIe ──────────────────────────────────────────────────────────────────
    "axi_pcie":              [("pg054", "AXI PCIe PG")],
    "xdma":                  [("pg195", "DMA/Bridge Subsystem for PCIe PG")],

    # ── Yüksek hızlı seri (GTX/Aurora) ───────────────────────────────────────
    "aurora_8b10b":          [("pg046", "Aurora 8B/10B PG")],
    "aurora_64b66b":         [("pg074", "Aurora 64B/66B PG")],
    "gig_ethernet_pcs_pma":  [("pg047", "1G/2.5G Ethernet PCS/PMA PG")],
    "tri_mode_ethernet_mac": [("pg051", "Tri-Mode Ethernet MAC PG")],

    # ── Video ─────────────────────────────────────────────────────────────────
    "v_tc":                  [("pg016", "Video Timing Controller PG")],
    "v_axi4s_vid_out":       [("pg044", "AXI4-Stream to Video Out PG")],
    "v_vid_in_axi4s":        [("pg043", "Video In to AXI4-Stream PG")],
    "rgb2dvi":               [("pg160", "RGB to DVI PG")],
    "dvi2rgb":               [("pg163", "DVI to RGB PG")],

    # ── Ölçüm & Debug ─────────────────────────────────────────────────────────
    "xadc_wiz":              [("pg091", "XADC Wizard PG"),
                               ("ug480", "7-Series XADC UG")],
    "ila":                   [("pg172", "Integrated Logic Analyzer PG")],
    "vio":                   [("pg159", "Virtual Input/Output PG")],

    # ── Zynq Processing System ────────────────────────────────────────────────
    "processing_system7":    [("ug585", "Zynq-7000 TRM"),
                               ("pg082", "Zynq-7000 PS PG"),
                               ("ug898", "Embedded Processor HW Design (UG1579)")],
}

# ─────────────────────────────────────────────────────────────────────────────
# Vivado workflow için her projede gerekli temel dokümanlar
# IP bağımsız — proje yaşam döngüsünün her aşaması için
# ─────────────────────────────────────────────────────────────────────────────

WORKFLOW_DOCS: list[tuple[str, str]] = [
    ("ug835",  "Vivado TCL Commands Reference"),
    ("ug893",  "Vivado IDE User Guide"),
    ("ug894",  "Vivado TCL Scripting User Guide"),
    ("ug895",  "Vivado System-Level Design Entry"),
    ("ug896",  "Vivado Designing with IP"),
    ("ug898", "Vivado Embedded Processor HW Design (UG1579, UG898 yerine)"),
    ("ug899",  "Vivado I/O and Clock Planning"),
    ("ug901",  "Vivado Synthesis User Guide"),
    ("ug903",  "Vivado Using Constraints"),
    ("ug904",  "Vivado Implementation User Guide"),
    ("ug908",  "Vivado Programming and Debugging"),
    ("ug912",  "Vivado Designing IP Subsystems (IP Integrator)"),
    ("ug984",  "MicroBlaze Processor Reference Guide"),
    ("ug994",  "Vivado IP Subsystems User Guide"),
    ("ug572",  "7-Series Clocking Resources User Guide"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Yardımcı fonksiyonlar
# ─────────────────────────────────────────────────────────────────────────────

_TCL_IP_RE = re.compile(r'xilinx\.com:ip:([^:]+):', re.IGNORECASE)


def _get_ip_project_counts() -> dict[str, set[str]]:
    """FTS5 index'inden TCL dosyalarındaki IP VLNV'lerini tara."""
    from rag_v2.fts5_index import FTS5Index
    fts = FTS5Index(str(_ROOT / "db/fts5_source.db"))
    ip_projects: dict[str, set[str]] = {}
    rows = fts._conn.execute(
        "SELECT content, project FROM fts"
        " WHERE file_type='tcl' AND content LIKE '%create_bd_cell%'"
    ).fetchall()
    for content, proj in rows:
        if not content:
            continue
        for m in _TCL_IP_RE.finditer(content):
            ip = m.group(1).lower()
            ip_projects.setdefault(ip, set()).add(proj)
    return ip_projects


def _get_indexed_doc_ids() -> set[str]:
    """DocStore'daki mevcut doc_id'leri döndür."""
    from rag_v2.doc_store import DocStore
    ds = DocStore(str(_ROOT / "db/chroma_docs"))
    col = ds._get_collection()
    present: set[str] = set()
    offset = 0
    while True:
        res = col.get(include=["metadatas"], limit=2000, offset=offset)
        if not res["metadatas"]:
            break
        for m in res["metadatas"]:
            did = m.get("doc_id", "")
            if did:
                present.add(did.lower())
        offset += 2000
        if len(res["metadatas"]) < 2000:
            break
    return present


# ─────────────────────────────────────────────────────────────────────────────
# Ana analiz
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis() -> dict:
    """
    Tam kapsam analizini çalıştır.
    Döndürür: {
        "workflow": [{"doc_id", "title", "present"}],
        "ip_docs":  [{"ip", "n_projects", "doc_id", "title", "present"}],
        "missing":  [{"doc_id", "title", "source", "n_projects"}],
    }
    """
    print("DocStore taranıyor...", end=" ", flush=True)
    present = _get_indexed_doc_ids()
    print(f"{len(present)} doküman")

    print("Kaynak dosyalar taranıyor...", end=" ", flush=True)
    ip_projects = _get_ip_project_counts()
    print(f"{len(ip_projects)} benzersiz IP")

    workflow_results = []
    for doc_id, title in WORKFLOW_DOCS:
        workflow_results.append({
            "doc_id": doc_id,
            "title": title,
            "present": doc_id in present,
        })

    ip_doc_results = []
    missing_set: dict[str, dict] = {}  # doc_id → en yüksek proje sayısı

    for ip, docs in sorted(IP_TO_DOCS.items(),
                           key=lambda x: -len(ip_projects.get(x[0], set()))):
        n = len(ip_projects.get(ip, set()))
        if n == 0:
            continue
        for doc_id, title in docs:
            is_present = doc_id in present
            ip_doc_results.append({
                "ip": ip,
                "n_projects": n,
                "doc_id": doc_id,
                "title": title,
                "present": is_present,
            })
            if not is_present:
                if (doc_id not in missing_set
                        or missing_set[doc_id]["n_projects"] < n):
                    missing_set[doc_id] = {
                        "doc_id": doc_id,
                        "title": title,
                        "source": f"IP: {ip}",
                        "n_projects": n,
                    }

    # Workflow'dan eksik olanları da ekle
    for item in workflow_results:
        if not item["present"]:
            doc_id = item["doc_id"]
            if doc_id not in missing_set:
                missing_set[doc_id] = {
                    "doc_id": doc_id,
                    "title": item["title"],
                    "source": "workflow",
                    "n_projects": 0,
                }

    missing = sorted(missing_set.values(),
                     key=lambda x: -x["n_projects"])

    return {
        "workflow": workflow_results,
        "ip_docs": ip_doc_results,
        "missing": missing,
        "stats": {
            "indexed_docs": len(present),
            "unique_ips_in_source": len(ip_projects),
            "missing_count": len(missing),
        },
    }


def print_report(result: dict, missing_only: bool = False) -> None:
    W = 70
    stats = result["stats"]

    if not missing_only:
        print("=" * W)
        print("WORKFLOW DOCS (proje bağımsız — her zaman gerekli)")
        print("=" * W)
        for item in result["workflow"]:
            status = "✓" if item["present"] else "✗ EKSİK"
            print(f"  {status:<8} {item['doc_id']:<10} {item['title']}")

        print()
        print("=" * W)
        print("IP-BAZLI DOCS (kaynak kodda kullanılan IP'lere göre)")
        print("=" * W)
        cur_ip = None
        for item in result["ip_docs"]:
            if item["ip"] != cur_ip:
                cur_ip = item["ip"]
                print(f"\n  [{item['ip']} — {item['n_projects']} projede]")
            status = "✓" if item["present"] else "✗ EKSİK"
            print(f"    {status:<8} {item['doc_id']:<10} {item['title']}")

    print()
    print("=" * W)
    if result["missing"]:
        print(f"EKSİK DOKÜMANLAR ({len(result['missing'])} adet)"
              " — proje etkisine göre sıralı")
        print("=" * W)
        for item in result["missing"]:
            proj_info = (f"[{item['n_projects']} projede]"
                         if item["n_projects"] > 0 else "[workflow]")
            print(f"  ✗  {item['doc_id']:<10} {item['title']:<42} {proj_info}")
        print()
        print("Bu PDF'leri Xilinx/AMD sitesinden indirip data/pdfs/ altına")
        print("koy, ardından scripts/index_docs.py ile indexle.")
    else:
        print("TÜM DOKÜMANLAR MEVCUT ✓")
        print("=" * W)

    print()
    print(f"Özet: {stats['indexed_docs']} döküman indexli · "
          f"{stats['unique_ips_in_source']} benzersiz IP · "
          f"{stats['missing_count']} eksik")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="DocStore IP kapsam analizi — eksik Xilinx dokümanlarını tespit et"
    )
    parser.add_argument("--missing", action="store_true",
                        help="Sadece eksik dokümanları göster")
    parser.add_argument("--json", action="store_true",
                        help="JSON formatında çıktı ver")
    args = parser.parse_args()

    result = run_analysis()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result, missing_only=args.missing)


if __name__ == "__main__":
    main()
