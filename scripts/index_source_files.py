#!/usr/bin/env python3
"""
FPGA RAG v2 — Source File Indexer
===================================
İki projenin tüm kaynak dosyalarını (RTL, C, XDC, TCL) okur,
akıllı şekilde chunk'lar ve SourceChunkStore'a (ChromaDB) ekler.

Çalıştırma:
    python scripts/index_source_files.py
    python scripts/index_source_files.py --reset     # Mevcut indexi sil, yeniden yap
    python scripts/index_source_files.py --dry-run   # Hangi dosyalar eklenecek, göster

Bağlantı:
  - Graph'taki SOURCE_DOC node'ları → dosya yolu eşleştirmesi için kullanılır
  - Graph'taki COMPONENT node'ları → kaynak dosyaya bağlı node_id'ler
  - SourceChunkStore → db/chroma_source_chunks/ (yeni ChromaDB koleksiyonu)
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")


# ─────────────────────────────────────────────────────────────────────────────
# Proje kaynak dosya kataloğu
# ─────────────────────────────────────────────────────────────────────────────

# Her proje için: project_id, kaynak dizinleri, ilgili graph node_id'leri
# NOT: Graph'taki PROJECT-A = nexys_a7_dma_audio, PROJECT-B = axi_gpio_example

_VT = str(Path.home() / "Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test")

PROJECT_SOURCE_CATALOG = [
    # ── PROJECT-A: Nexys A7 DMA Audio ────────────────────────────────────────
    {
        "project": "nexys_a7_dma_audio",
        "display_name": "Nexys A7 DMA Audio",
        "roots": [
            str(_ROOT / "data/code/Nexys-A7-100T-DMA-Audio"),
        ],
        "include_exts": [".v", ".sv", ".c", ".h", ".xdc", ".tcl", ".json"],
        "exclude_patterns": [".git", "__pycache__", "node_modules", ".ip_user_files",
                              "_pycache_", "sim_", ".cache"],
        "file_node_map": {
            "axis2fifo.v": ["COMP-A-axis2fifo_0"],
            "fifo2audpwm.v": ["COMP-A-fifo2audpwm_0"],
            "tone_generator.v": ["COMP-A-tone_generator_0"],
            "design_1.tcl": ["COMP-A-axi_dma_0", "COMP-A-mig_7series_0"],
            "Nexys-A7-100T-Master.xdc": ["COMP-A-clk_wiz_0"],
            "helloworld.c": ["COMP-A-helloworld", "COMP-A-axi_dma_0"],
            "platform.c": [],
            "platform.h": [],
        },
    },
    # ── PROJECT-B: AXI GPIO Example (Nexys Video) ────────────────────────────
    {
        "project": "axi_gpio_example",
        "display_name": "AXI GPIO Example (Nexys Video)",
        "roots": [
            f"{_VT}/axi_example",
        ],
        "include_exts": [".v", ".sv", ".c", ".h", ".xdc", ".tcl", ".json"],
        "exclude_patterns": [".git", "__pycache__", "vivado_minimal_mb", "RUN_AXI"],
        "file_node_map": {
            "nexys_video.xdc": ["COMP-B-clk_wiz_0", "COMP-B-rst_clk_wiz_0_100M"],
            "Nexys-Video-Master.xdc": ["COMP-B-clk_wiz_0"],
            "axi_gpio_wrapper.v": ["COMP-B-axi_gpio_wrapper"],
            "add_axi_gpio.tcl": ["COMP-B-axi_gpio_0", "COMP-B-microblaze_0_axi_periph"],
            "create_minimal_microblaze.tcl": ["COMP-B-microblaze_0", "COMP-B-clk_wiz_0", "COMP-B-mdm_1"],
            "create_axi_simple_gpio.tcl": ["COMP-B-axi_gpio_0"],
            "SYNTHESIS_RESULTS.md": ["COMP-B-microblaze_0", "COMP-B-axi_gpio_0", "COMP-B-clk_wiz_0"],
        },
        "specific_files": [
            f"{_VT}/axi_example/SYNTHESIS_RESULTS.md",
            str(_ROOT / "data/code/digilent-xdc/Nexys-Video-Master.xdc"),
        ],
    },
    # ── Validation test projects ──────────────────────────────────────────────
    {
        "project": "gtx_ddr_example",
        "display_name": "GTX DDR Example (Nexys Video)",
        "roots": [f"{_VT}/gtx_ddr_example"],
        "include_exts": [".v", ".sv", ".c", ".h", ".xdc", ".tcl"],
        "exclude_patterns": [".git", "__pycache__", ".cache"],
        "file_node_map": {},
    },
    {
        "project": "i2c_example",
        "display_name": "I2C Example (Nexys Video)",
        "roots": [f"{_VT}/i2c_example"],
        "include_exts": [".v", ".sv", ".c", ".h", ".xdc", ".tcl"],
        "exclude_patterns": [".git", "__pycache__", ".cache"],
        "file_node_map": {},
    },
    {
        "project": "pcie_dma_ddr_example",
        "display_name": "PCIe DMA DDR Example",
        "roots": [f"{_VT}/pcie_dma_ddr_example"],
        "include_exts": [".v", ".sv", ".c", ".h", ".xdc", ".tcl"],
        "exclude_patterns": [".git", "__pycache__", ".cache"],
        "file_node_map": {},
    },
    {
        "project": "pcie_xdma_mb_example",
        "display_name": "PCIe XDMA MicroBlaze Example",
        "roots": [f"{_VT}/pcie_xdma_mb_example"],
        "include_exts": [".v", ".sv", ".c", ".h", ".xdc", ".tcl"],
        "exclude_patterns": [".git", "__pycache__", ".cache"],
        "file_node_map": {},
    },
    {
        "project": "rgmii_example",
        "display_name": "RGMII Ethernet Example (Nexys Video)",
        "roots": [f"{_VT}/rgmii_example"],
        "include_exts": [".v", ".sv", ".c", ".h", ".xdc", ".tcl"],
        "exclude_patterns": [".git", "__pycache__", ".cache"],
        "file_node_map": {},
    },
    {
        "project": "v2_mig",
        "display_name": "MIG DDR3 v2 Example",
        "roots": [f"{_VT}/v2_mig"],
        "include_exts": [".v", ".sv", ".c", ".h", ".xdc", ".tcl"],
        "exclude_patterns": [".git", "__pycache__", ".cache"],
        "file_node_map": {},
    },
    {
        "project": "v3_gtx",
        "display_name": "GTX Transceiver v3 Example",
        "roots": [f"{_VT}/v3_gtx"],
        "include_exts": [".v", ".sv", ".c", ".h", ".xdc", ".tcl"],
        "exclude_patterns": [".git", "__pycache__", ".cache"],
        "file_node_map": {},
    },
    {
        "project": "spi_example",
        "display_name": "SPI Pmod Example (Nexys Video)",
        "roots": [f"{_VT}/spi_example"],
        "include_exts": [".v", ".sv", ".c", ".h", ".xdc", ".tcl"],
        "exclude_patterns": [".git", "__pycache__", ".cache"],
        "file_node_map": {},
    },
    {
        "project": "uart_example",
        "display_name": "UART Example",
        "roots": [f"{_VT}/uart_example"],
        "include_exts": [".v", ".sv", ".c", ".h", ".xdc", ".tcl"],
        "exclude_patterns": [".git", "__pycache__", ".cache"],
        "file_node_map": {},
    },
]

# Proje dokümanları (data/docs/)
# NOT: Bu dosyalar SourceChunkStore'a dahil edilmiyor.
# Sebep: SYSTEM_CONFIGURATION.md gibi Türkçe sistem dökümanları
# Türkçe sorguları yanlış eşleştiriyor ve proje kaynak chunk'larını gürültüyle bozuyor.
# Bu dosyalar zaten ana eğitim ChromaDB'sinde (chroma_graph_nodes) bulunuyor.
DOC_SOURCES: list = []  # Boş — docs intentionally excluded from source chunk store


# ─────────────────────────────────────────────────────────────────────────────
# Dosya keşif fonksiyonları
# ─────────────────────────────────────────────────────────────────────────────

def discover_files(
    root: str,
    include_exts: List[str],
    exclude_patterns: List[str],
) -> List[Path]:
    """Dizini tara, eşleşen dosyaları döndür."""
    root_path = Path(root)
    if not root_path.exists():
        return []

    files = []
    for p in root_path.rglob("*"):
        if not p.is_file():
            continue
        # Hariç tutma kontrolü
        skip = False
        for exc in exclude_patterns:
            if exc in str(p):
                skip = True
                break
        if skip:
            continue
        # Uzantı kontrolü
        if p.suffix.lower() in include_exts:
            files.append(p)

    return sorted(files)


def get_node_ids_for_file(
    file_name: str,
    file_node_map: Dict[str, List[str]],
) -> List[str]:
    """Dosya adından ilgili graph node_id'lerini çek."""
    return file_node_map.get(file_name, [])


# ─────────────────────────────────────────────────────────────────────────────
# Ana indexleme fonksiyonu
# ─────────────────────────────────────────────────────────────────────────────

def run_indexing(reset: bool = False, dry_run: bool = False, verbose: bool = False):
    print("=" * 72)
    print("  FPGA RAG v2 — Source File Indexer")
    print("=" * 72)

    if not dry_run:
        from rag_v2.source_chunk_store import SourceChunkStore
        store = SourceChunkStore(
            persist_directory=str(_ROOT / "db" / "chroma_source_chunks")
        )
        if reset:
            print("  [RESET] Mevcut index siliniyor...")
            store.reset()
            print("  [RESET] Tamamlandı.")

    total_files = 0
    total_chunks_added = 0
    project_stats = {}

    # ── Proje kaynak dosyaları ────────────────────────────────────────────────
    for proj_cfg in PROJECT_SOURCE_CATALOG:
        project = proj_cfg["project"]
        display = proj_cfg["display_name"]
        print(f"\n  [{project}] {display}")
        print(f"  {'─' * 60}")

        proj_files = 0
        proj_chunks = 0

        for root in proj_cfg["roots"]:
            root_path = Path(root)
            if not root_path.exists():
                print(f"    ⚠️  Dizin bulunamadı: {root}")
                continue

            files = discover_files(
                root,
                proj_cfg["include_exts"],
                proj_cfg["exclude_patterns"],
            )

            print(f"    Dizin: {root}")
            print(f"    Bulunan dosya: {len(files)}")

            for f in files:
                node_ids = get_node_ids_for_file(f.name, proj_cfg["file_node_map"])
                rel_path = str(f.relative_to(_ROOT)) if _ROOT in f.parents else str(f)

                if verbose or dry_run:
                    print(f"      {f.name:40s} → nodes: {node_ids or ['—']}")

                if not dry_run:
                    n = store.add_file(str(f), project, node_ids)
                    proj_chunks += n
                    if verbose:
                        print(f"         → {n} chunk eklendi")

                proj_files += 1
                total_files += 1

        # ── Specific files (extension filter'ı bypass eder) ──────────────────
        for specific_path in proj_cfg.get("specific_files", []):
            sp = Path(specific_path)
            if not sp.exists():
                if verbose or dry_run:
                    print(f"    ⚠️  Specific dosya bulunamadı: {specific_path}")
                continue
            node_ids = get_node_ids_for_file(sp.name, proj_cfg["file_node_map"])
            if verbose or dry_run:
                print(f"      {sp.name:40s} → nodes: {node_ids or ['—']} [specific]")
            if not dry_run:
                n = store.add_file(str(sp), project, node_ids)
                proj_chunks += n
                if verbose:
                    print(f"         → {n} chunk eklendi")
            proj_files += 1
            total_files += 1

        print(f"    Toplam: {proj_files} dosya, {proj_chunks} chunk")
        project_stats[project] = {"files": proj_files, "chunks": proj_chunks}
        total_chunks_added += proj_chunks

    # ── Döküman dosyaları ─────────────────────────────────────────────────────
    print(f"\n  [DOCS] Proje dokümanları")
    print(f"  {'─' * 60}")
    doc_files = 0
    doc_chunks = 0

    for doc_cfg in DOC_SOURCES:
        project = doc_cfg["project"]
        for path_str in doc_cfg["paths"]:
            p = Path(path_str)
            if not p.exists():
                if verbose:
                    print(f"    ⚠️  Bulunamadı: {path_str}")
                continue
            node_ids = get_node_ids_for_file(p.name, doc_cfg["file_node_map"])
            if verbose or dry_run:
                print(f"    {p.name}")
            if not dry_run:
                n = store.add_file(str(p), project, node_ids)
                doc_chunks += n
            doc_files += 1
            total_files += 1

    total_chunks_added += doc_chunks
    print(f"    Toplam: {doc_files} dosya, {doc_chunks} chunk")

    # ── Özet ──────────────────────────────────────────────────────────────────
    print(f"\n  {'=' * 72}")
    print(f"  ÖZET")
    print(f"  {'=' * 72}")
    print(f"  Toplam dosya      : {total_files}")
    print(f"  Toplam chunk      : {total_chunks_added}")

    if not dry_run:
        final_count = store.count()
        print(f"  ChromaDB kayıt    : {final_count}")
        print(f"  Persist dizin     : {_ROOT / 'db' / 'chroma_source_chunks'}")

    for proj, stats in project_stats.items():
        print(f"  {proj}: {stats['files']} dosya, {stats['chunks']} chunk")

    if dry_run:
        print(f"\n  [DRY-RUN] Hiçbir değişiklik yapılmadı.")
    else:
        print(f"\n  ✅ İndeksleme tamamlandı!")

    return total_chunks_added


# ─────────────────────────────────────────────────────────────────────────────
# Grafik ve graph bağlantısı güncelleme
# ─────────────────────────────────────────────────────────────────────────────

def update_graph_source_docs(verbose: bool = False):
    """
    Graph'taki SOURCE_DOC node'larını gerçek dosya yollarıyla güncelle.
    COMP node'larının source_file alanını doğrula.
    """
    print("\n  [GRAPH] SOURCE_DOC node'ları güncelleniyor...")
    from rag_v2.graph_store import GraphStore

    gs = GraphStore(persist_path=str(_ROOT / "db" / "graph" / "fpga_rag_v2_graph.json"))
    nodes = gs.get_all_nodes()

    updates = 0
    for node in nodes:
        nid = node.get("node_id", "")
        ntype = node.get("node_type", "")

        if ntype == "SOURCE_DOC":
            # SOURCE_DOC node'unun file_path alanını güncelle
            source_file = node.get("source_file", "")
            if source_file and verbose:
                print(f"    {nid}: {source_file}")
            updates += 1

    print(f"  {updates} SOURCE_DOC node incelendi.")


# ─────────────────────────────────────────────────────────────────────────────
# Ana giriş
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FPGA RAG v2 Source File Indexer")
    parser.add_argument("--reset", action="store_true",
                        help="Mevcut source chunk index'i sil ve yeniden oluştur")
    parser.add_argument("--dry-run", action="store_true",
                        help="Hangi dosyaların ekleneceğini göster (değişiklik yok)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Ayrıntılı çıktı")

    args = parser.parse_args()

    run_indexing(
        reset=args.reset,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
