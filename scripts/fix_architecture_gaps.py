#!/usr/bin/env python3
"""
Mimari Boşluk Düzeltme Scripti — FPGA RAG v2
Architecture ref: fpga_rag_architecture_v2.md

Eklenecekler (ister dokümanı §3 ve §6 referansıyla):
  1. 20 SOURCE_DOC node'u (SDOC-A-001..009, SDOC-B-001..011)
  2. VERIFIED_BY: COMPONENT → SOURCE_DOC (kaynak dosya izlenebilirliği)
  3.  3 eksik MOTIVATED_BY edge (DECISION → REQUIREMENT)
  4.  1 CONTRADICTS edge (AXI:microblaze_0 v11.0 vs DMA:microblaze_0 v10.0)
  5.  1 INFORMED_BY edge (PROJECT-B eğitim → PROJECT-A uygulama)
  6.  1 eksik REUSES_PATTERN edge (PAT-B-001 AXI Tie-Off → PAT-A-003 AXI Stream Tie-Off)
  7. Vector store rebuild (yeni node'lar için)

NOT: ALTERNATIVE_TO edge'leri §6.3'te analiz edilmiştir.
     Uygun node yapısı için ayrı bir patch gerektiriyor (bakınız analiz).
"""

import sys
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rag_v2.graph_store import GraphStore
from rag_v2.vector_store_v2 import VectorStoreV2

GRAPH_PATH  = str(ROOT / "db" / "graph" / "fpga_rag_v2_graph.json")
CHROMA_PATH = str(ROOT / "db" / "chroma_graph_nodes")

# ===========================================================================
# 1. SOURCE_DOC NODE'LARI (ister dokümanı §3)
# ===========================================================================

SOURCE_DOC_NODES = [
    # PROJECT-A: Nexys-A7-100T-DMA-Audio
    {
        "node_id": "SDOC-A-001",
        "node_type": "SOURCE_DOC",
        "name": "axis2fifo.v",
        "description": "AXI-Stream → FIFO dönüştürücü RTL modülü. axis_tdata[31:0] → fifo_wr_data[15:0] dönüşümü.",
        "project": "PROJECT-A",
        "path": "/home/test123/GC-RAG-VIVADO-2/data/code/Nexys-A7-100T-DMA-Audio/src/hdl/axis2fifo.v",
        "doc_type": "hdl_source",
        "language": "Verilog",
        "lines": "37",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-A-002",
        "node_type": "SOURCE_DOC",
        "name": "fifo2audpwm.v",
        "description": "FIFO → PWM ses çıkışı dönüştürücü. DATA_WIDTH=8, FIFO_DATA_WIDTH=32. aud_pwm ve aud_en çıkışları.",
        "project": "PROJECT-A",
        "path": "/home/test123/GC-RAG-VIVADO-2/data/code/Nexys-A7-100T-DMA-Audio/src/hdl/fifo2audpwm.v",
        "doc_type": "hdl_source",
        "language": "Verilog",
        "lines": "39",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-A-003",
        "node_type": "SOURCE_DOC",
        "name": "tone_generator.v",
        "description": "Phase accumulator tabanlı donanım ton üreteci. INCREMENT=0x00B22D0E. ISSUE: axis_tlast=1 hatası mevcut.",
        "project": "PROJECT-A",
        "path": "/home/test123/GC-RAG-VIVADO-2/data/code/Nexys-A7-100T-DMA-Audio/src/hdl/tone_generator.v",
        "doc_type": "hdl_source",
        "language": "Verilog",
        "lines": "73",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-A-004",
        "node_type": "SOURCE_DOC",
        "name": "helloworld.c",
        "description": "MicroBlaze SDK uygulaması — DMA kontrolü, WAV parser, demo modları. 395 satır C kodu. "
                       "Fonksiyonlar: main(), dma_sw_tone_gen(), recv_wav(), play_wav().",
        "project": "PROJECT-A",
        "path": "/home/test123/GC-RAG-VIVADO-2/data/code/Nexys-A7-100T-DMA-Audio/sdk/appsrc/helloworld.c",
        "doc_type": "sw_source",
        "language": "C",
        "lines": "395",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-A-005",
        "node_type": "SOURCE_DOC",
        "name": "design_1.tcl",
        "description": "Vivado Block Design recreation script. 745 satır TCL. Tüm IP instance'ları ve bağlantıları tanımlar. "
                       "NOT: Satır 53'te xc7a50ticsg324-1L part → CONFLICT-A-001.",
        "project": "PROJECT-A",
        "path": "/home/test123/GC-RAG-VIVADO-2/data/code/Nexys-A7-100T-DMA-Audio/src/bd/design_1.tcl",
        "doc_type": "tcl_script",
        "lines": "745",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-A-006",
        "node_type": "SOURCE_DOC",
        "name": "Nexys-A7-100T-Master.xdc",
        "description": "Pin ve timing constraint dosyası. 212 satır. "
                       "100 MHz clock E3 pini. Audio PWM A11 pini. UART USB-RS232.",
        "project": "PROJECT-A",
        "path": "/home/test123/GC-RAG-VIVADO-2/data/code/Nexys-A7-100T-DMA-Audio/src/constraints/Nexys-A7-100T-Master.xdc",
        "doc_type": "constraint",
        "lines": "212",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-A-007",
        "node_type": "SOURCE_DOC",
        "name": "project_info.tcl",
        "description": "Proje konfigürasyon dosyası. FPGA part: xc7a50ticsg324-1L (CONFLICT-A-001: 100T board için yanlış part).",
        "project": "PROJECT-A",
        "path": "/home/test123/GC-RAG-VIVADO-2/data/code/Nexys-A7-100T-DMA-Audio/project_info.tcl",
        "doc_type": "tcl_script",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-A-008",
        "node_type": "SOURCE_DOC",
        "name": "README.md (DMA-Audio)",
        "description": "DMA-Audio proje README. Bilinen sorunlar: tone_generator devre dışı, UART WAV aktarımı. Kullanım talimatları.",
        "project": "PROJECT-A",
        "path": "/home/test123/GC-RAG-VIVADO-2/data/code/Nexys-A7-100T-DMA-Audio/README.md",
        "doc_type": "documentation",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-A-009",
        "node_type": "SOURCE_DOC",
        "name": "pwm_audio_rtl.xml",
        "description": "Custom PWM audio bus interface tanımı. IP definition XML.",
        "project": "PROJECT-A",
        "path": "/home/test123/GC-RAG-VIVADO-2/data/code/Nexys-A7-100T-DMA-Audio/repo/local/if/pwm_audio/pwm_audio_rtl.xml",
        "doc_type": "ip_definition",
        "confidence": "HIGH",
        "version": "1",
    },
    # PROJECT-B: axi_example
    {
        "node_id": "SDOC-B-001",
        "node_type": "SOURCE_DOC",
        "name": "axi_gpio_wrapper.v",
        "description": "Standalone AXI GPIO wrapper — AXI tie-off pattern. switches[7:0] → leds[7:0]. Kullanılmayan AXI sinyalleri tie-off.",
        "project": "PROJECT-B",
        "path": "/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test/axi_example/vivado_axi_simple/axi_gpio_wrapper.v",
        "doc_type": "hdl_source",
        "language": "Verilog",
        "lines": "37",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-B-002",
        "node_type": "SOURCE_DOC",
        "name": "simple_top.v",
        "description": "4-bit counter test modülü. clk(in), reset(in), led[3:0](out). Minimal FPGA tasarımı.",
        "project": "PROJECT-B",
        "path": "/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test/axi_example/simple_working/simple_project.srcs/sources_1/new/simple_top.v",
        "doc_type": "hdl_source",
        "language": "Verilog",
        "lines": "12",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-B-003",
        "node_type": "SOURCE_DOC",
        "name": "axi_gpio_bd.bd",
        "description": "MicroBlaze + GPIO block design. MicroBlaze v11.0, AXI GPIO, Clocking Wizard, Reset Controller, MDM, LMB BRAM.",
        "project": "PROJECT-B",
        "path": "/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test/axi_example/axi_example_build/axi_example_build.srcs/sources_1/bd/axi_gpio_bd/axi_gpio_bd.bd",
        "doc_type": "block_design",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-B-004",
        "node_type": "SOURCE_DOC",
        "name": "nexys_video.xdc",
        "description": "Nexys Video pin constraint dosyası. 30 satır. 100 MHz differential clock R4/T4. LED pinleri.",
        "project": "PROJECT-B",
        "path": "/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test/axi_example/vivado_axi_simple/nexys_video.xdc",
        "doc_type": "constraint",
        "lines": "30",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-B-005",
        "node_type": "SOURCE_DOC",
        "name": "create_axi_simple_gpio.tcl",
        "description": "Standalone GPIO proje oluşturma scripti. 132 satır. Seviye 1: MicroBlaze olmadan GPIO. AXI tie-off pattern uygular.",
        "project": "PROJECT-B",
        "path": "/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test/axi_example/create_axi_simple_gpio.tcl",
        "doc_type": "tcl_script",
        "lines": "132",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-B-006",
        "node_type": "SOURCE_DOC",
        "name": "create_minimal_microblaze.tcl",
        "description": "Minimal MicroBlaze BD oluşturma scripti. 162 satır. Seviye 2: MicroBlaze + LMB BRAM 8KB. Block Automation kullanır.",
        "project": "PROJECT-B",
        "path": "/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test/axi_example/create_minimal_microblaze.tcl",
        "doc_type": "tcl_script",
        "lines": "162",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-B-007",
        "node_type": "SOURCE_DOC",
        "name": "add_axi_gpio.tcl",
        "description": "Mevcut MicroBlaze projesine AXI GPIO ekleme scripti. 157 satır. Seviye 3: MicroBlaze + AXI GPIO.",
        "project": "PROJECT-B",
        "path": "/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test/axi_example/add_axi_gpio.tcl",
        "doc_type": "tcl_script",
        "lines": "157",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-B-008",
        "node_type": "SOURCE_DOC",
        "name": "run_synthesis.tcl",
        "description": "Sentez çalıştırma ve rapor üretme scripti. 82 satır. Timing ve utilization raporları üretir.",
        "project": "PROJECT-B",
        "path": "/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test/axi_example/run_synthesis.tcl",
        "doc_type": "tcl_script",
        "lines": "82",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-B-009",
        "node_type": "SOURCE_DOC",
        "name": "SYNTHESIS_RESULTS.md",
        "description": "Sentez sonuçları raporu. WNS=+2.128ns (timing met). LUT: 1193/134600 (%0.89). FF: 902/269200 (%0.34). BRAM: 2.",
        "project": "PROJECT-B",
        "path": "/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test/axi_example/SYNTHESIS_RESULTS.md",
        "doc_type": "documentation",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-B-010",
        "node_type": "SOURCE_DOC",
        "name": "utilization_summary.txt",
        "description": "Detaylı kaynak kullanım raporu. LUT: 1193 (%0.89), FF: 902 (%0.34), BRAM: 2/365 (%0.55).",
        "project": "PROJECT-B",
        "path": "/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test/axi_example/utilization_summary.txt",
        "doc_type": "report",
        "confidence": "HIGH",
        "version": "1",
    },
    {
        "node_id": "SDOC-B-011",
        "node_type": "SOURCE_DOC",
        "name": "README.md (axi_example)",
        "description": "axi_example proje README. Türkçe/İngilizce dokümantasyon. 3 seviyeli kademeli öğrenme rehberi.",
        "project": "PROJECT-B",
        "path": "/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test/axi_example/README.md",
        "doc_type": "documentation",
        "confidence": "HIGH",
        "version": "1",
    },
]

# ===========================================================================
# 2. COMPONENT → SOURCE_DOC VERIFIED_BY EDGES
#    (ister dokümanı §4.4.1 ve §5.4.1 "Source" sütununa göre)
# ===========================================================================

COMP_TO_SDOC_VERIFIED_BY = [
    # PROJECT-A components
    ("COMP-A-axis2fifo_0",              "SDOC-A-001", "RTL modülü kaynak dosyası"),
    ("COMP-A-fifo2audpwm_0",            "SDOC-A-002", "RTL modülü kaynak dosyası"),
    ("COMP-A-tone_generator_0",         "SDOC-A-003", "RTL modülü kaynak dosyası (tone_generator.v:69 axis_tlast bug)"),
    ("COMP-A-helloworld",               "SDOC-A-004", "MicroBlaze SDK uygulama kaynak kodu"),
    ("COMP-A-fifo_generator_0",         "SDOC-A-005", "design_1.tcl IP instance tanımı"),
    ("COMP-A-axi_uartlite_0",           "SDOC-A-005", "design_1.tcl IP instance tanımı"),
    ("COMP-A-GPIO_IN",                  "SDOC-A-005", "design_1.tcl IP instance tanımı"),
    ("COMP-A-GPIO_OUT",                 "SDOC-A-005", "design_1.tcl IP instance tanımı"),
    ("COMP-A-clk_wiz_0",                "SDOC-A-005", "design_1.tcl IP instance tanımı"),
    ("COMP-A-rst_mig_7series_0_81M",    "SDOC-A-005", "design_1.tcl IP instance tanımı"),
    ("COMP-A-mdm_1",                    "SDOC-A-005", "design_1.tcl IP instance tanımı"),
    ("COMP-A-microblaze_0_axi_intc",    "SDOC-A-005", "design_1.tcl IP instance tanımı"),
    ("COMP-A-microblaze_0",             "SDOC-A-005", "design_1.tcl IP instance tanımı"),
    ("COMP-A-axi_dma_0",                "SDOC-A-005", "design_1.tcl IP instance tanımı"),
    ("COMP-A-mig_7series_0",            "SDOC-A-005", "design_1.tcl IP instance tanımı"),
    ("COMP-A-axi_interconnect_0",       "SDOC-A-005", "design_1.tcl IP instance tanımı"),
    # PROJECT-B components
    ("COMP-B-axi_gpio_wrapper",         "SDOC-B-001", "RTL modülü kaynak dosyası"),
    ("COMP-B-simple_top",               "SDOC-B-002", "RTL modülü kaynak dosyası"),
    ("COMP-B-axi_gpio_0",               "SDOC-B-003", "axi_gpio_bd.bd block design"),
    ("COMP-B-microblaze_0",             "SDOC-B-003", "axi_gpio_bd.bd block design"),
    ("COMP-B-clk_wiz_0",                "SDOC-B-003", "axi_gpio_bd.bd block design"),
    ("COMP-B-rst_clk_wiz_0_100M",       "SDOC-B-003", "axi_gpio_bd.bd block design"),
    ("COMP-B-mdm_1",                    "SDOC-B-003", "axi_gpio_bd.bd block design"),
    ("COMP-B-lmb_bram_0",               "SDOC-B-003", "axi_gpio_bd.bd block design"),
]

# ===========================================================================
# 3. EKSİK MOTIVATED_BY EDGES (ister dokümanı §4.3 related_requirements)
#    Mevcut: 8 edge. Hedef: 11 edge. Eksik: 3 adet.
# ===========================================================================

MISSING_MOTIVATED_BY = [
    # DMA-DEC-002 ikinci related_requirement
    {
        "source": "DMA-DEC-002",
        "target": "DMA-REQ-L1-003",
        "note": "MicroBlaze+DMA mimarisi güç ve saat yönetimini (L1-003) doğrudan etkiler",
        "confidence": "HIGH",
    },
    # AXI-DEC-003: MicroBlaze v11.0 seçimi
    {
        "source": "AXI-DEC-003",
        "target": "AXI-REQ-L1-002",
        "note": "MicroBlaze v11.0 seçimi işleme gereksinimini (L1-002) karşılar",
        "confidence": "HIGH",
    },
    # AXI-DEC-004: 8 KB LMB BRAM
    {
        "source": "AXI-DEC-004",
        "target": "AXI-REQ-L2-004",
        "note": "8 KB LMB BRAM kararı bellek gereksinimini (L2-004) belirler",
        "confidence": "HIGH",
    },
]

# ===========================================================================
# 4. CONTRADICTS EDGE — ister dokümanı §7.3
#    AXI:microblaze_0 v11.0 vs DMA:microblaze_0 v10.0
#    Sürüm farkı → config önerileri farklılaşabilir (Layer 6 tetikleyicisi)
# ===========================================================================

CONTRADICTS_EDGES = [
    {
        "source": "COMP-B-microblaze_0",
        "target": "COMP-A-microblaze_0",
        "note": "MicroBlaze versiyon çakışması: axi_example v11.0 (Vivado 2025.1) vs DMA-Audio v10.0 (Vivado 2018.2). "
                "Cache config farklı: B'de cache yok, A'da I+D cache var. "
                "Tavsiye: B'deki config'i A'ya direk uygulamayın.",
        "confidence": "MEDIUM",
    },
]

# ===========================================================================
# 5. INFORMED_BY EDGE — ister dokümanı §7.3
#    axi_example (eğitim) → DMA-Audio (uygulama): eğitim projesini anlamak
#    DMA-Audio'yu anlamayı kolaylaştırır.
# ===========================================================================

INFORMED_BY_EDGES = [
    {
        "source": "PROJECT-B",
        "target": "PROJECT-A",
        "note": "axi_example AXI bus mimarisini öğretir; DMA-Audio bunu gerçek uygulamada kullanır. "
                "Öğrenci B'yi anlayarak A'yı daha iyi kavrar.",
        "confidence": "MEDIUM",
    },
]

# ===========================================================================
# 6. EKSİK REUSES_PATTERN EDGE — ister dokümanı §7.3
#    PAT-B-001 (AXI Tie-Off) → axis2fifo_0 (dolaylı tie-off)
# ===========================================================================

MISSING_REUSES_PATTERN = [
    {
        "source": "PAT-B-001",
        "target": "PAT-A-003",
        "note": "Her iki projede AXI Tie-Off pattern kullanılıyor: "
                "B'de explicit axi_gpio_wrapper.v, A'da axis2fifo'da kullanılmayan AXI sinyalleri implicit tie-off",
        "confidence": "MEDIUM",
    },
]

# ===========================================================================
# 7. SOURCE_DOC NODES → PROJECT VERIFIED_BY EDGES (provenance)
# ===========================================================================

PROJECT_TO_SDOC_VERIFIED_BY = [
    # PROJECT-A kaynak dosyaları
    ("PROJECT-A", "SDOC-A-001", "Proje HDL kaynak dosyası"),
    ("PROJECT-A", "SDOC-A-002", "Proje HDL kaynak dosyası"),
    ("PROJECT-A", "SDOC-A-003", "Proje HDL kaynak dosyası"),
    ("PROJECT-A", "SDOC-A-004", "Proje SW kaynak dosyası"),
    ("PROJECT-A", "SDOC-A-005", "Proje TCL BD scripti"),
    ("PROJECT-A", "SDOC-A-006", "Proje constraint dosyası"),
    ("PROJECT-A", "SDOC-A-007", "Proje konfigürasyon dosyası"),
    ("PROJECT-A", "SDOC-A-008", "Proje dokümantasyonu"),
    ("PROJECT-A", "SDOC-A-009", "Proje IP tanımı"),
    # PROJECT-B kaynak dosyaları
    ("PROJECT-B", "SDOC-B-001", "Proje HDL kaynak dosyası"),
    ("PROJECT-B", "SDOC-B-002", "Proje HDL kaynak dosyası"),
    ("PROJECT-B", "SDOC-B-003", "Proje block design dosyası"),
    ("PROJECT-B", "SDOC-B-004", "Proje constraint dosyası"),
    ("PROJECT-B", "SDOC-B-005", "Proje TCL scripti"),
    ("PROJECT-B", "SDOC-B-006", "Proje TCL scripti"),
    ("PROJECT-B", "SDOC-B-007", "Proje TCL scripti"),
    ("PROJECT-B", "SDOC-B-008", "Proje sentez scripti"),
    ("PROJECT-B", "SDOC-B-009", "Proje sentez raporu"),
    ("PROJECT-B", "SDOC-B-010", "Proje kullanım raporu"),
    ("PROJECT-B", "SDOC-B-011", "Proje dokümantasyonu"),
]


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    print("=" * 60)
    print("FPGA RAG v2 — Mimari Boşluk Düzeltme Scripti")
    print("=" * 60)

    gs = GraphStore(persist_path=GRAPH_PATH)
    stats_before = gs.stats()
    print(f"\nBaşlangıç: {stats_before['total_nodes']} node, {stats_before['total_edges']} edge")

    added_nodes = 0
    added_edges = 0

    # -----------------------------------------------------------------------
    # 1. SOURCE_DOC nodes
    # -----------------------------------------------------------------------
    print("\n[1] SOURCE_DOC node'ları ekleniyor...")
    existing_ids = {n["node_id"] for n in gs.get_all_nodes()}
    for node in SOURCE_DOC_NODES:
        nid = node["node_id"]
        if nid not in existing_ids:
            gs.add_node(nid, node)
            added_nodes += 1
            print(f"  + {nid}: {node['name']}")
        else:
            # Update existing to ensure richness
            gs.add_node(nid, node)
            print(f"  ~ {nid}: güncellendi")

    # -----------------------------------------------------------------------
    # 2. COMPONENT → SOURCE_DOC VERIFIED_BY edges
    # -----------------------------------------------------------------------
    print("\n[2] COMPONENT → SOURCE_DOC VERIFIED_BY edge'leri ekleniyor...")
    existing_nodes = {n["node_id"] for n in gs.get_all_nodes()}
    existing_edges = {(u, v, attrs.get("edge_type", ""))
                      for u, v, attrs in gs._graph.edges(data=True)}

    for comp_id, sdoc_id, note in COMP_TO_SDOC_VERIFIED_BY:
        if comp_id not in existing_nodes:
            print(f"  SKIP {comp_id} → {sdoc_id}: kaynak node yok")
            continue
        if sdoc_id not in existing_nodes:
            print(f"  SKIP {comp_id} → {sdoc_id}: hedef node yok")
            continue
        key = (comp_id, sdoc_id, "VERIFIED_BY")
        if key not in existing_edges:
            eid = f"E-VB-SDOC-{comp_id}-{sdoc_id}"
            gs.add_edge(comp_id, sdoc_id, "VERIFIED_BY", {
                "edge_id": eid,
                "confidence": "HIGH",
                "note": note,
                "provenance": '{"phase": 6, "source": "fix_architecture_gaps"}',
            })
            existing_edges.add(key)
            added_edges += 1
            print(f"  + {comp_id} --[VERIFIED_BY]--> {sdoc_id}")
        else:
            print(f"  = {comp_id} → {sdoc_id}: zaten var")

    # -----------------------------------------------------------------------
    # 3. Missing MOTIVATED_BY edges
    # -----------------------------------------------------------------------
    print("\n[3] Eksik MOTIVATED_BY edge'leri ekleniyor...")
    for e in MISSING_MOTIVATED_BY:
        key = (e["source"], e["target"], "MOTIVATED_BY")
        if e["source"] not in existing_nodes:
            print(f"  SKIP {e['source']}: node yok")
            continue
        if e["target"] not in existing_nodes:
            print(f"  SKIP {e['target']}: node yok")
            continue
        if key not in existing_edges:
            eid = f"E-MOT-{e['source']}-{e['target']}"
            gs.add_edge(e["source"], e["target"], "MOTIVATED_BY", {
                "edge_id": eid,
                "confidence": e["confidence"],
                "note": e["note"],
                "provenance": '{"phase": 3, "source": "fix_architecture_gaps"}',
            })
            existing_edges.add(key)
            added_edges += 1
            print(f"  + {e['source']} --[MOTIVATED_BY]--> {e['target']}")
        else:
            print(f"  = {e['source']} → {e['target']}: zaten var")

    # -----------------------------------------------------------------------
    # 4. CONTRADICTS edges
    # -----------------------------------------------------------------------
    print("\n[4] CONTRADICTS edge'i ekleniyor...")
    for e in CONTRADICTS_EDGES:
        key = (e["source"], e["target"], "CONTRADICTS")
        if e["source"] not in existing_nodes or e["target"] not in existing_nodes:
            print(f"  SKIP {e['source']} → {e['target']}: node yok")
            continue
        if key not in existing_edges:
            eid = f"E-CONT-{e['source']}-{e['target']}"
            gs.add_edge(e["source"], e["target"], "CONTRADICTS", {
                "edge_id": eid,
                "confidence": e["confidence"],
                "note": e["note"],
                "provenance": '{"phase": 5, "source": "fix_architecture_gaps"}',
            })
            existing_edges.add(key)
            added_edges += 1
            print(f"  + {e['source']} --[CONTRADICTS]--> {e['target']}")
        else:
            print(f"  = {e['source']} → {e['target']}: zaten var")

    # -----------------------------------------------------------------------
    # 5. INFORMED_BY edges
    # -----------------------------------------------------------------------
    print("\n[5] INFORMED_BY edge'i ekleniyor...")
    for e in INFORMED_BY_EDGES:
        key = (e["source"], e["target"], "INFORMED_BY")
        if e["source"] not in existing_nodes or e["target"] not in existing_nodes:
            print(f"  SKIP: node yok")
            continue
        if key not in existing_edges:
            eid = f"E-INF-{e['source']}-{e['target']}"
            gs.add_edge(e["source"], e["target"], "INFORMED_BY", {
                "edge_id": eid,
                "confidence": e["confidence"],
                "note": e["note"],
                "provenance": '{"phase": 5, "source": "fix_architecture_gaps"}',
            })
            existing_edges.add(key)
            added_edges += 1
            print(f"  + {e['source']} --[INFORMED_BY]--> {e['target']}")
        else:
            print(f"  = {e['source']} → {e['target']}: zaten var")

    # -----------------------------------------------------------------------
    # 6. Missing REUSES_PATTERN edge
    # -----------------------------------------------------------------------
    print("\n[6] Eksik REUSES_PATTERN edge'i ekleniyor...")
    for e in MISSING_REUSES_PATTERN:
        key = (e["source"], e["target"], "REUSES_PATTERN")
        if e["source"] not in existing_nodes or e["target"] not in existing_nodes:
            print(f"  SKIP {e['source']} → {e['target']}: node yok")
            continue
        if key not in existing_edges:
            eid = f"E-RPAT-{e['source']}-{e['target']}"
            gs.add_edge(e["source"], e["target"], "REUSES_PATTERN", {
                "edge_id": eid,
                "confidence": e["confidence"],
                "note": e["note"],
                "provenance": '{"phase": 5, "source": "fix_architecture_gaps"}',
            })
            existing_edges.add(key)
            added_edges += 1
            print(f"  + {e['source']} --[REUSES_PATTERN]--> {e['target']}")
        else:
            print(f"  = {e['source']} → {e['target']}: zaten var")

    # -----------------------------------------------------------------------
    # 7. PROJECT → SOURCE_DOC VERIFIED_BY edges
    # -----------------------------------------------------------------------
    print("\n[7] PROJECT → SOURCE_DOC VERIFIED_BY edge'leri ekleniyor...")
    for proj_id, sdoc_id, note in PROJECT_TO_SDOC_VERIFIED_BY:
        key = (proj_id, sdoc_id, "VERIFIED_BY")
        if proj_id not in existing_nodes or sdoc_id not in existing_nodes:
            continue
        if key not in existing_edges:
            eid = f"E-VB-PROJ-{proj_id}-{sdoc_id}"
            gs.add_edge(proj_id, sdoc_id, "VERIFIED_BY", {
                "edge_id": eid,
                "confidence": "HIGH",
                "note": note,
                "provenance": '{"phase": 6, "source": "fix_architecture_gaps"}',
            })
            existing_edges.add(key)
            added_edges += 1
            print(f"  + {proj_id} --[VERIFIED_BY]--> {sdoc_id}")

    # Save
    gs.save()
    stats_after = gs.stats()
    print(f"\nSonuç: {stats_after['total_nodes']} node (+{added_nodes}), "
          f"{stats_after['total_edges']} edge (+{added_edges})")

    # -----------------------------------------------------------------------
    # 8. Vector store rebuild — SOURCE_DOC node'ları için
    # -----------------------------------------------------------------------
    print("\n[8] Vector store rebuild (SOURCE_DOC + yeni node'lar)...")
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        client.delete_collection("fpga_rag_v2_nodes")
        print("  Eski koleksiyon silindi.")
    except Exception:
        pass

    vs = VectorStoreV2(persist_directory=CHROMA_PATH, threshold=0.35)
    all_nodes = gs.get_all_nodes()
    count = vs.add_nodes_batch(all_nodes, batch_size=50)
    print(f"  Vector store rebuild tamamlandı: {count} node embed edildi.")

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("TAMAMLANDI")
    print(f"  Eklenen node  : {added_nodes}")
    print(f"  Eklenen edge  : {added_edges}")
    print(f"  Toplam node   : {stats_after['total_nodes']}")
    print(f"  Toplam edge   : {stats_after['total_edges']}")
    print()
    print("Aktif edge tipleri:")
    from collections import Counter
    with open(GRAPH_PATH) as f:
        gdata = json.load(f)
    for et, cnt in sorted(Counter(e["edge_type"] for e in gdata["edges"]).items()):
        print(f"  {et}: {cnt}")
    print()
    print("Node tipleri:")
    for nt, cnt in sorted(Counter(n["node_type"] for n in gdata["nodes"]).items()):
        print(f"  {nt}: {cnt}")


if __name__ == "__main__":
    main()
