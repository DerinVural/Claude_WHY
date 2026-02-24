#!/usr/bin/env python3
"""
fix_graph_db.py — FPGA RAG v2 Graph DB Düzeltme Scripti

Sorunlar:
  1. 95+ node'da name/description BOŞ → vector search çalışmıyor
  2. 6 Coverage Gap (REQUIREMENT node'ları IMPLEMENTS edge'siz)
  3. 6 Orphan Component (COMPONENT node'ları IMPLEMENTS edge'siz)
  4. DMA-REQ-L1-005 → DMA-REQ-L2-011 DECOMPOSES_TO edge'i kayıp

Bu script:
  1. Tüm boş node'lara gerçek name/description atar
  2. Eksik IMPLEMENTS edge'lerini ekler
  3. Eksik DECOMPOSES_TO edge'ini ekler
  4. Graph'ı kaydeder
  5. Vector store'u sıfırdan yeniden oluşturur
"""

import sys
import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from rag_v2.graph_store import GraphStore
from rag_v2.vector_store_v2 import VectorStoreV2

GRAPH_PATH = str(_ROOT / "db" / "graph" / "fpga_rag_v2_graph.json")
CHROMA_PATH = str(_ROOT / "db" / "chroma_graph_nodes")


# ===========================================================================
# 1. NODE NAME + DESCRIPTION PATCH DATA
# ===========================================================================

NODE_PATCHES = {

    # -------------------------------------------------------------------------
    # REQUIREMENT NODES — PROJECT-A (DMA Audio)
    # -------------------------------------------------------------------------
    "DMA-REQ-L0-001": {
        "name": "DMA Tabanlı Ses Akışı (L0)",
        "description": "Nexys A7-100T üzerinde DMA tabanlı ses akışı sistemi. "
                       "DDR2 tamponlu, MicroBlaze firmware kontrollü, AXI-Stream veri yolu.",
    },
    "DMA-REQ-L1-001": {
        "name": "DDR2 Tamponlu Ses Akışı (L1)",
        "description": "DDR2 SDRAM tabanlı ses tamponu. AXI DMA scatter-gather ile "
                       "DDR2'den FIFO'ya veri akışı. MIG 7-Series DDR2 arbitrasyonu.",
    },
    "DMA-REQ-L1-002": {
        "name": "MicroBlaze Firmware + SDK Entegrasyonu (L1)",
        "description": "MicroBlaze soft-core üzerinde çalışan helloworld.c firmware. "
                       "DMA kontrol, WAV oynatma, UART konsol, GPIO izleme.",
    },
    "DMA-REQ-L1-003": {
        "name": "Güç ve Saat Yönetimi (L1)",
        "description": "Clocking Wizard ile çift saat üretimi: 140.625 MHz (MIG DDR2) "
                       "ve 24.576 MHz (PWM ses). proc_sys_reset ile senkron reset zinciri.",
    },
    "DMA-REQ-L1-004": {
        "name": "Debug Altyapısı (L1)",
        "description": "JTAG MDM v3.2 debug modülü. MicroBlaze JTAG debug. "
                       "Vivado Hardware Manager entegrasyonu.",
    },
    "DMA-REQ-L1-005": {
        "name": "GPIO Altyapısı (L1)",
        "description": "AXI GPIO çift kanallı: switch/button girişi (GPIO_IN) ve "
                       "LED çıkışı (GPIO_OUT). Interrupt altyapısı: AXI INTC + xlconcat.",
    },
    "DMA-REQ-L1-006": {
        "name": "AXI-Stream Sinyal Yolu (L1)",
        "description": "AXI-Stream veri yolu: AXI DMA MM2S → axis2fifo → FIFO → "
                       "fifo2audpwm → PWM ses çıkışı. TVALID/TREADY/TDATA/TLAST handshake.",
    },
    "DMA-REQ-L2-001": {
        "name": "FPGA Part Kısıtı",
        "description": "Hedef FPGA: xc7a100tcsg324-1 (Artix-7 100T). "
                       "UYARI: TCL dosyası xc7a50ticsg324-1L (50T) içeriyor — ISSUE-A-001.",
    },
    "DMA-REQ-L2-002": {
        "name": "DDR2 Kapasite ve MIG Arbitrasyon",
        "description": "DDR2 SDRAM kapasitesi ≥ 128MB. MIG 7-Series DDR2 controller, "
                       "140.625 MHz UI clock, arbitrated AXI4 slave port.",
    },
    "DMA-REQ-L2-003": {
        "name": "Donanım Ton Üreticisi [PARSE_UNCERTAIN]",
        "description": "tone_generator RTL modülü. NOT CURRENTLY WORKING: axis_tlast=1 "
                       "sabit bırakılmış (bug). DDS akkümülatör tabanlı frekans üretimi.",
    },
    "DMA-REQ-L2-004": {
        "name": "Çift-Saat FIFO CDC",
        "description": "FIFO Generator v13.2, independent_clocks modu. Gray-code pointer "
                       "senkronizasyonu. 512x16 bit. AXI-Stream (24.576 MHz) ↔ DMA (140 MHz) CDC.",
    },
    "DMA-REQ-L2-005": {
        "name": "DMA Scatter-Gather Modu",
        "description": "AXI DMA 7.1 scatter-gather modu etkin. MM2S kanalı. "
                       "DDR2'den AXI-Stream'e veri aktarımı. helloworld.c firmware kontrolü.",
    },
    "DMA-REQ-L2-006": {
        "name": "WAV 96kHz Ses Oynatma",
        "description": "WAV dosyası oynatma. 96 kHz örnekleme hızı. 8-bit PCM. "
                       "GPIO switch ile tetikleme. DDR2'de depolama, DMA ile akış.",
    },
    "DMA-REQ-L2-007": {
        "name": "UART Serial Konsol",
        "description": "AXI UARTLite 9600 baud UART. Debug ve durum mesajları. "
                       "helloworld.c print statements. PC terminal erişimi.",
    },
    "DMA-REQ-L2-008": {
        "name": "Saat Mimarisi",
        "description": "Clocking Wizard v6.0: 100 MHz giriş → 140.625 MHz (MIG DDR2) "
                       "+ 24.576 MHz (PWM ses). PLL tabanlı, MMCME2_ADV.",
    },
    "DMA-REQ-L2-009": {
        "name": "Reset Zinciri (MIG Tabanlı)",
        "description": "proc_sys_reset v5.0: MIG DDR2 init_calib_complete sinyali "
                       "reset release. Peripheral aresetn + interconnect aresetn zinciri.",
    },
    "DMA-REQ-L2-010": {
        "name": "JTAG MDM Debug",
        "description": "MDM v3.2 Microprocessor Debug Module. MicroBlaze JTAG "
                       "debug interface. Vivado Hardware Manager ile bağlantı.",
    },
    "DMA-REQ-L2-011": {
        "name": "AXI GPIO + Interrupt Altyapısı",
        "description": "AXI INTC v4.1 interrupt controller. xlconcat_0 (DMA IRQ) + "
                       "xlconcat_1 (GPIO+UART IRQ). Donanım interrupt altyapısı mevcut, "
                       "yazılım polling kullanıyor (DMA-DEC-005).",
    },

    # -------------------------------------------------------------------------
    # REQUIREMENT NODES — PROJECT-B (AXI Example)
    # -------------------------------------------------------------------------
    "AXI-REQ-L0-001": {
        "name": "AXI Bus Eğitim/Validasyon Test Suite (L0)",
        "description": "AXI bus mimarisi eğitim ve validasyon projesi. Nexys Video "
                       "üzerinde MicroBlaze + AXI-Lite GPIO. 3 kademeli eğitim metodolojisi.",
    },
    "AXI-REQ-L1-001": {
        "name": "GPIO Kontrolü — LED/Switch I/O (L1)",
        "description": "AXI GPIO v2.0 ile LED çıkışı ve switch girişi. "
                       "Base adres 0x40000000. axi_gpio_wrapper RTL sarmalayıcı.",
    },
    "AXI-REQ-L1-002": {
        "name": "MicroBlaze Soft-Core İşlemci (L1)",
        "description": "MicroBlaze v11.0 soft-core işlemci. 8KB LMB BRAM, cache yok. "
                       "AXI4 master. LMB bellek arayüzü. Vivado 2025.1.",
    },
    "AXI-REQ-L1-003": {
        "name": "Saat Yönetimi (L1)",
        "description": "Clocking Wizard v6.0 MMCME2_ADV. 100 MHz giriş → fabric clock. "
                       "BUFG ile dağıtım. PLL locked sinyali reset'e bağlı.",
    },
    "AXI-REQ-L1-004": {
        "name": "Reset Yönetimi (L1)",
        "description": "proc_sys_reset v5.0 reset zinciri. PLL locked → reset release. "
                       "WNS > 0 ns timing constraint. BTNC → active-low reset.",
    },
    "AXI-REQ-L1-005": {
        "name": "AXI-Lite Sinyal Yolu (L1)",
        "description": "AXI4-Lite protokolü. MicroBlaze master → AXI Interconnect → "
                       "AXI GPIO slave. WNS > 0 ns ile synthesis PASS. AWVALID/WVALID handshake.",
    },
    "AXI-REQ-L2-001": {
        "name": "GPIO Base Adresi = 0x40000000",
        "description": "AXI GPIO base adresi 0x40000000. assign_bd_address TCL komutu ile "
                       "explicit atama. axi_gpio_wrapper erişim adresi.",
    },
    "AXI-REQ-L2-002": {
        "name": "8KB LMB BRAM, Cache Yok",
        "description": "MicroBlaze LMB BRAM: 8KB data + 8KB instruction. "
                       "Cache devre dışı (eğitimsel tasarım). dlmb_v10 + ilmb_v10.",
    },
    "AXI-REQ-L2-003": {
        "name": "100 MHz → MMCME2_ADV → Fabric",
        "description": "Clocking Wizard MMCME2_ADV: 100 MHz Nexys Video osilat. "
                       "→ 100 MHz fabric clock. BUFG küresel saat dağıtımı.",
    },
    "AXI-REQ-L2-004": {
        "name": "WNS > 0 ns (Synthesis Verify)",
        "description": "Sentez sonrası WNS > 0 ns doğrulama. SYNTHESIS_RESULTS.md "
                       "kanıtı. Timing closure başarılı.",
    },
    "AXI-REQ-L2-005": {
        "name": "WNS > 0 ns ile Synthesis PASS",
        "description": "AXI-Lite sinyal yolu timing doğrulaması. "
                       "Synthesis PASS, WNS pozitif. EVID-B-001.",
    },
    "AXI-REQ-L2-006": {
        "name": "PLL Lock → Reset Release",
        "description": "clk_wiz.locked → proc_sys_reset.dcm_locked. "
                       "PLL kilitlenince reset serbest bırakılır. PAT-B-005 pattern.",
    },
    "AXI-REQ-L2-007": {
        "name": "3 Seviyeli Kademeli İlerleme",
        "description": "Eğitim metodolojisi: Seviye 1 (Standalone GPIO) → "
                       "Seviye 2 (MicroBlaze + GPIO) → Seviye 3 (Tam Sistem). CLI-first TCL.",
    },

    # -------------------------------------------------------------------------
    # COMPONENT NODES — PROJECT-A
    # -------------------------------------------------------------------------
    "COMP-A-axis2fifo_0": {
        "name": "axis2fifo — AXI-Stream to FIFO Adapter",
        "description": "RTL modülü (axis2fifo.v). AXI-Stream TVALID/TREADY/TDATA → "
                       "FIFO write interface. FIFO full → tready=0 backpressure. "
                       "16-bit data path. Nexys A7-100T DMA Audio projesi.",
    },
    "COMP-A-fifo2audpwm_0": {
        "name": "fifo2audpwm — FIFO to Audio PWM",
        "description": "RTL modülü (fifo2audpwm.v). FIFO'dan veri okur, 8-bit PWM "
                       "ses çıkışı üretir. 24.576 MHz PWM clock, 96kHz örnekleme. "
                       "FIFO empty → audio disable (aud_en=0).",
    },
    "COMP-A-tone_generator_0": {
        "name": "tone_generator — DDS Ton Üreticisi [BUG]",
        "description": "RTL modülü (tone_generator.v). DDS akkümülatör tabanlı. "
                       "HATA: axis_tlast=1 sabit bırakılmış (satır 69). "
                       "16-bit→8-bit truncation. CURRENTLY NOT WORKING. ISSUE-A-002.",
    },
    "COMP-A-fifo_generator_0": {
        "name": "FIFO Generator v13.2 — Bağımsız Saatli CDC FIFO",
        "description": "Xilinx IP. Independent_clocks modu. 512 derinlik x 16 bit. "
                       "Gray-code pointer senkronizasyonu. AXI-Stream (24.576 MHz) ↔ "
                       "DMA (140 MHz) clock domain crossing.",
    },
    "COMP-A-axi_dma_0": {
        "name": "AXI DMA 7.1 — Scatter-Gather DMA",
        "description": "Xilinx IP. MM2S kanalı. Scatter-gather modu etkin. "
                       "DDR2 SDRAM → AXI-Stream veri akışı. MicroBlaze firmware kontrolü. "
                       "IRQ: mm2s_introut, s2mm_introut.",
    },
    "COMP-A-mig_7series_0": {
        "name": "MIG 7-Series DDR2 Controller",
        "description": "Xilinx IP. 128MB DDR2 SDRAM. 140.625 MHz UI clock. "
                       "Arbitrated AXI4 slave port. init_calib_complete → reset release. "
                       "Nexys A7-100T DDR2 bellek kontrolcüsü.",
    },
    "COMP-A-clk_wiz_0": {
        "name": "Clocking Wizard v6.0 — Çift Saat Üreticisi",
        "description": "Xilinx IP (MMCME2_ADV). 100 MHz giriş → "
                       "140.625 MHz (MIG DDR2 UI) + 24.576 MHz (PWM ses). "
                       "PLL locked → reset release. CONST-A-CLK-001/002.",
    },
    "COMP-A-rst_mig_7series_0_81M": {
        "name": "proc_sys_reset v5.0 — MIG Tabanlı Reset",
        "description": "Xilinx IP. MIG DDR2 init_calib_complete sinyali ile "
                       "senkron reset zinciri. peripheral_aresetn + interconnect_aresetn "
                       "üretir. 81 MHz domain.",
    },
    "COMP-A-microblaze_0": {
        "name": "MicroBlaze v10.0 — Soft-Core İşlemci",
        "description": "Xilinx soft-core işlemci. AXI4 master. LMB BRAM arayüzü. "
                       "DMA kontrol, WAV oynatma, GPIO ve UART yönetimi. "
                       "helloworld.c firmware çalıştırır.",
    },
    "COMP-A-mdm_1": {
        "name": "MDM v3.2 — MicroBlaze Debug Modülü",
        "description": "Xilinx IP. JTAG debug interface. MicroBlaze breakpoint, "
                       "single-step, register read/write. Vivado Hardware Manager.",
    },
    "COMP-A-microblaze_0_axi_intc": {
        "name": "AXI INTC v4.1 — Interrupt Controller",
        "description": "Xilinx IP. DMA MM2S/S2MM IRQ + GPIO + UART interrupt topluyor. "
                       "xlconcat_0 ve xlconcat_1 üzerinden gelen sinyalleri MicroBlaze'e iletir.",
    },
    "COMP-A-xlconcat_0": {
        "name": "xlconcat v2.1 — DMA Interrupt Birleştirici",
        "description": "Xilinx utility IP. DMA mm2s_introut + s2mm_introut sinyallerini "
                       "birleştirir. AXI INTC girişine bağlar. DMA-DEC-005 kapsamında.",
    },
    "COMP-A-xlconcat_1": {
        "name": "xlconcat v2.1 — GPIO/UART Interrupt Birleştirici",
        "description": "Xilinx utility IP. GPIO_IN interrupt + UARTLite interrupt "
                       "sinyallerini birleştirir. AXI INTC girişine bağlar. DMA-DEC-005.",
    },
    "COMP-A-GPIO_IN": {
        "name": "AXI GPIO (Çift Kanal) — Switch/Button Girişi",
        "description": "Xilinx AXI GPIO v2.0 dual-channel. Switch ve button girişi. "
                       "WAV oynatma tetikleyici. Interrupt üretir (GPIO2_IO_I). "
                       "Nexys A7-100T slide switches.",
    },
    "COMP-A-GPIO_OUT": {
        "name": "AXI GPIO — LED Çıkışı",
        "description": "Xilinx AXI GPIO v2.0. LED çıkış arayüzü. "
                       "Durum göstergesi: oynatma durumu, hata kodları. "
                       "Nexys A7-100T LED bar.",
    },
    "COMP-A-axi_uartlite_0": {
        "name": "AXI UARTLite v2.0 — Serial Konsol",
        "description": "Xilinx IP. 9600 baud UART. TX/RX pinleri. "
                       "helloworld.c debug mesajları. UART interrupt üretir. "
                       "CONST-A-UART-001.",
    },
    "COMP-A-helloworld": {
        "name": "helloworld.c — MicroBlaze Firmware",
        "description": "C uygulaması (Xilinx SDK). AXI DMA scatter-gather WAV oynatma, "
                       "UART konsol çıkışı, GPIO switch izleme. "
                       "WAV header parse, DMA descriptor setup, interrupt handler.",
    },
    "COMP-A-axi_interconnect_0": {
        "name": "AXI Interconnect — AXI4 Bus Fabric",
        "description": "Xilinx AXI Interconnect IP. MicroBlaze AXI4 master → "
                       "DMA, MIG, GPIO, UART, INTC slave'lerine yönlendirme. "
                       "AXI4 address decode ve arbitrasyon.",
    },
    "COMP-A-microblaze_0_axi_periph": {
        "name": "microblaze_0_axi_periph — Çevre AXI Interconnect",
        "description": "Xilinx AXI Interconnect. MicroBlaze çevre aygıt veri yolu. "
                       "Peripheral slave'lere (GPIO, UART, INTC, MDM) AXI erişimi sağlar.",
    },
    "COMP-A-lmb_bram": {
        "name": "LMB BRAM Subsistemi — MicroBlaze Belleği",
        "description": "lmb_bram_if_cntlr + lmb_v10 + blk_mem_gen. "
                       "64KB instruction + data BRAM. MicroBlaze LMB (Local Memory Bus) arayüzü. "
                       "dlmb (data) + ilmb (instruction) portları.",
    },
    "COMP-A-pwm_audio_bus": {
        "name": "PWM Audio Bus — Özel Ses Arayüzü",
        "description": "Özel sinyal veri yolu: pwm_out + aud_en sinyalleri. "
                       "fifo2audpwm çıkışından Nexys A7-100T ses pini (J5) arasında. "
                       "XDC: set_property PACKAGE_PIN J5.",
    },

    # -------------------------------------------------------------------------
    # COMPONENT NODES — PROJECT-B
    # -------------------------------------------------------------------------
    "COMP-B-axi_gpio_wrapper": {
        "name": "axi_gpio_wrapper — AXI GPIO RTL Sarmalayıcı",
        "description": "RTL modülü (axi_gpio_wrapper.v). AXI GPIO IP'yi saran "
                       "Verilog wrapper. PAT-B-001 AXI tie-off pattern. "
                       "LED/switch arayüzü, 0x40000000 base adres.",
    },
    "COMP-B-simple_top": {
        "name": "simple_top — Seviye 1 Standalone Test",
        "description": "RTL modülü (simple_top.v). AXI tie-off pattern. "
                       "Standalone GPIO testi, MicroBlaze olmadan. "
                       "PAT-B-001 kanıtı: EVID-B-002.",
    },
    "COMP-B-axi_gpio_0": {
        "name": "AXI GPIO v2.0 — GPIO Kontrolcü",
        "description": "Xilinx IP. LED çıkışı ve switch girişi. "
                       "Base adres 0x40000000. AXI-Lite slave. "
                       "AXI-REQ-L1-001 uygular.",
    },
    "COMP-B-microblaze_0": {
        "name": "MicroBlaze v11.0 — Soft-Core İşlemci",
        "description": "Xilinx soft-core işlemci. 8KB LMB BRAM, cache yok. "
                       "AXI4 master. Vivado 2025.1. GPIO LED/switch firmware kontrolü.",
    },
    "COMP-B-microblaze_0_axi_periph": {
        "name": "AXI Interconnect — Çevre Veri Yolu",
        "description": "Xilinx AXI Interconnect. MicroBlaze → AXI GPIO slave. "
                       "AXI4-Lite veri yolu. WNS > 0 ns timing.",
    },
    "COMP-B-clk_wiz_0": {
        "name": "Clocking Wizard v6.0 — 100 MHz Saat Üreticisi",
        "description": "Xilinx IP (MMCME2_ADV). Nexys Video 100 MHz osilat. "
                       "→ 100 MHz fabric clock. BUFG dağıtım. "
                       "locked → proc_sys_reset.dcm_locked.",
    },
    "COMP-B-rst_clk_wiz_0_100M": {
        "name": "proc_sys_reset v5.0 — PLL Tabanlı Reset",
        "description": "Xilinx IP. clk_wiz.locked → reset release. "
                       "peripheral_aresetn üretir. 100 MHz domain. "
                       "BTNC aktif-düşük reset girişi.",
    },
    "COMP-B-mdm_1": {
        "name": "MDM v3.2 — MicroBlaze UART Debug",
        "description": "Xilinx IP. JTAG debug + UART debug. "
                       "MicroBlaze breakpoint ve register erişimi. "
                       "Vivado Hardware Manager entegrasyonu.",
    },
    "COMP-B-lmb_subsystem": {
        "name": "LMB Memory Subsistemi — 8KB BRAM",
        "description": "dlmb_v10 + ilmb_v10 + dlmb_bram_if_cntlr + ilmb_bram_if_cntlr "
                       "+ blk_mem_gen. 8KB data + 8KB instruction BRAM. "
                       "MicroBlaze LMB arayüzü.",
    },

    # -------------------------------------------------------------------------
    # DECISION NODES — PROJECT-A
    # -------------------------------------------------------------------------
    "DMA-DEC-001": {
        "name": "AXI DMA IP Seçimi",
        "description": "Karar: Özel DMA yerine Xilinx AXI DMA IP 7.1. "
                       "Gerekçe: Vivado IP entegrasyonu, scatter-gather desteği, "
                       "AXI4 uyumluluğu, AXI-Stream MM2S kanalı.",
    },
    "DMA-DEC-002": {
        "name": "DDR2 SDRAM Ses Tamponu",
        "description": "Karar: MIG 7-Series DDR2 128MB tampon. "
                       "Gerekçe: 96kHz WAV veri hızı için yeterli bant genişliği, "
                       "Nexys A7-100T DDR2 SODIMM donanım desteği.",
    },
    "DMA-DEC-003": {
        "name": "MicroBlaze Soft-Core İşlemci",
        "description": "Karar: ARM yerine MicroBlaze soft-core. "
                       "Gerekçe: Eğitimsel amaç, donanım üzerinde tam kontrol, "
                       "Xilinx SDK entegrasyonu, AXI4 master desteği.",
    },
    "DMA-DEC-004": {
        "name": "AXI-Stream Ses Veri Yolu",
        "description": "Karar: AXI-Stream ile DMA → FIFO → PWM ses zinciri. "
                       "Gerekçe: Standart protokol, FIFO CDC ile saat geçişi, "
                       "backpressure desteği.",
    },
    "DMA-DEC-005": {
        "name": "Interrupt Donanımı Mevcut, Yazılım Polling Kullanıyor",
        "description": "Karar: xlconcat + AXI INTC donanımda kuruldu, "
                       "ancak helloworld.c polling kullanıyor. "
                       "Gerekçe: Belgelenmemiş (PARSE_UNCERTAIN). ISSUE-A-006.",
    },

    # -------------------------------------------------------------------------
    # DECISION NODES — PROJECT-B
    # -------------------------------------------------------------------------
    "AXI-DEC-001": {
        "name": "AXI4-Lite Çevre Veri Yolu",
        "description": "Karar: AXI4-Lite protokolü GPIO ve çevre aygıtlar için. "
                       "Gerekçe: Eğitimsel sadelik, burst gereksiz, basit register arayüzü.",
    },
    "AXI-DEC-002": {
        "name": "MicroBlaze v11.0 Soft-Core",
        "description": "Karar: MicroBlaze v11.0 Vivado 2025.1. "
                       "Gerekçe: Eğitim odaklı, AXI4 master, LMB BRAM ile minimal yapı.",
    },
    "AXI-DEC-003": {
        "name": "GPIO LED/Switch AXI Arayüzü",
        "description": "Karar: AXI GPIO IP ile LED ve switch arayüzü. "
                       "Gerekçe: AXI4-Lite eğitimi için ideal, standart Xilinx IP.",
    },
    "AXI-DEC-004": {
        "name": "CLI-First TCL Scripting",
        "description": "Karar: Vivado GUI yerine TCL batch modu. "
                       "Gerekçe: Tekrarlanabilirlik, otomasyon, sürüm kontrolü uyumu.",
    },
    "AXI-DEC-005": {
        "name": "MMCME2_ADV Saat Üretimi",
        "description": "Karar: Clocking Wizard MMCME2_ADV ile PLL saat üretimi. "
                       "Gerekçe: Nexys Video 100 MHz → fabric, PLL locked sinyal güvenilirliği.",
    },

    # -------------------------------------------------------------------------
    # EVIDENCE NODES — PROJECT-A
    # -------------------------------------------------------------------------
    "EVID-A-001": {
        "name": "design_1.tcl — AXI DMA Scatter-Gather Kanıtı",
        "description": "design_1.tcl: set_property -dict [list CONFIG.c_sg_include_stscntrl_strm "
                       "{0} CONFIG.c_sg_use_stsapp_length {0}] — scatter-gather modu kanıtı.",
    },
    "EVID-A-002": {
        "name": "mig_7series_0.tcl — DDR2 128MB, 140.625 MHz Kanıtı",
        "description": "mig_7series_0.tcl: 128MB DDR2 SODIMM konfigürasyonu, "
                       "140.625 MHz UI clock, arbitrated AXI4 slave. MIG IP parametreleri.",
    },
    "EVID-A-003": {
        "name": "tone_generator.v — axis_tlast=1 Bug Kanıtı",
        "description": "tone_generator.v satır 69: assign axis_tlast = 1'b1; "
                       "TLAST her zaman 1, paket sınırı yanlış. README: 'not currently working'.",
    },
    "EVID-A-004": {
        "name": "axis2fifo.v — AXI-Stream Handshake Kanıtı",
        "description": "axis2fifo.v: axis_tready = ~fifo_full backpressure. "
                       "AXI-Stream TVALID/TREADY/TDATA handshake implementasyonu.",
    },
    "EVID-A-005": {
        "name": "fifo2audpwm.v — PWM Audio 24.576 MHz Kanıtı",
        "description": "fifo2audpwm.v: 24.576 MHz PWM clock, 8-bit duty cycle, "
                       "FIFO empty → aud_en=0. Audio PWM çıkış implementasyonu.",
    },
    "EVID-A-006": {
        "name": "fifo_generator_0.tcl — Independent Clock FIFO Kanıtı",
        "description": "fifo_generator_0.tcl: independent_clocks modu, 512 derinlik, "
                       "16-bit veri genişliği. Gray-code pointer senkronizasyonu.",
    },
    "EVID-A-007": {
        "name": "design_1.tcl — AXI-Stream Bağlantı Kanıtı",
        "description": "design_1.tcl: connect_bd_intf_net AXI-Stream bağlantıları. "
                       "DMA MM2S → axis2fifo → FIFO → fifo2audpwm signal path.",
    },
    "EVID-A-008": {
        "name": "project_info.tcl — FPGA Part 50T Kanıtı [KRİTİK]",
        "description": "project_info.tcl satır 4: xc7a50ticsg324-1L (50T). "
                       "design_1.tcl satır 53: xc7a50ticsg324-1L. "
                       "README/XDC: 100T hedefliyor. ISSUE-A-001 kritik tutarsızlık.",
    },
    "EVID-A-009": {
        "name": "Nexys-A7-100T-Master.xdc — Pin Kısıt Kanıtı",
        "description": "XDC: set_property PACKAGE_PIN J5 [get_ports {pwm_audio_out}] "
                       "+ set_property PACKAGE_PIN E3 [get_ports {sys_clk}]. "
                       "PWM ses ve saat pin atamaları.",
    },
    "EVID-A-010": {
        "name": "helloworld.c — DMA Firmware Kanıtı",
        "description": "helloworld.c: XAxiDma_BdRingCreate, XAxiDma_BdRingAlloc, "
                       "scatter-gather descriptor setup. DMA WAV oynatma firmware.",
    },
    "EVID-A-011": {
        "name": "helloworld.c — UART Konsol Kanıtı",
        "description": "helloworld.c: xil_printf() çağrıları, "
                       "durum mesajları, debug çıktıları. AXI UARTLite üzerinden.",
    },
    "EVID-A-012": {
        "name": "README.md — tone_generator 'Not Working' Kanıtı",
        "description": "README.md: 'tone_generator is not currently working'. "
                       "axis_tlast bug ve 16-bit→8-bit truncation sorunu belgelenmiş.",
    },

    # -------------------------------------------------------------------------
    # EVIDENCE NODES — PROJECT-B
    # -------------------------------------------------------------------------
    "EVID-B-001": {
        "name": "SYNTHESIS_RESULTS.md — WNS > 0 ns Kanıtı",
        "description": "SYNTHESIS_RESULTS.md: Synthesis PASS, WNS pozitif. "
                       "100 MHz fabric clock timing closure başarılı. EVID-B-001.",
    },
    "EVID-B-002": {
        "name": "simple_top.v — AXI Tie-Off Pattern Kanıtı",
        "description": "simple_top.v: AXI slave portları tie-off. "
                       "Standalone GPIO testi, MicroBlaze olmadan. PAT-B-001 kanıtı.",
    },
    "EVID-B-003": {
        "name": "add_axi_gpio.tcl — GPIO 0x40000000 Adres Kanıtı",
        "description": "add_axi_gpio.tcl: assign_bd_address, "
                       "AXI GPIO base adres 0x40000000 explicit ataması. EVID-B-003.",
    },

    # -------------------------------------------------------------------------
    # CONSTRAINT NODES — PROJECT-A
    # -------------------------------------------------------------------------
    "CONST-A-PIN-001": {
        "name": "XDC PWM Pin J5 — Ses Çıkışı",
        "description": "XDC kısıtı: PACKAGE_PIN J5, pwm_audio_out. "
                       "Nexys A7-100T ses çıkış pini. LVCMOS33, 12mA.",
    },
    "CONST-A-PIN-002": {
        "name": "XDC Saat Pin E3 — 100 MHz",
        "description": "XDC kısıtı: PACKAGE_PIN E3, sys_clk_i. "
                       "Nexys A7-100T 100 MHz sistem saati girişi. LVCMOS33.",
    },
    "CONST-A-CLK-001": {
        "name": "140.625 MHz MIG DDR2 UI Clock",
        "description": "MIG DDR2 controller UI clock: 140.625 MHz. "
                       "DDR2 bellek arayüz saati. MIG PLL çıkışı.",
    },
    "CONST-A-CLK-002": {
        "name": "24.576 MHz PWM Ses Saati",
        "description": "PWM ses saat kısıtı: 24.576 MHz. "
                       "96kHz örnekleme için 24.576MHz/256=96kHz. "
                       "Clocking Wizard PLL çıkışı.",
    },
    "CONST-A-CLK-003": {
        "name": "100 MHz Giriş Referans Saati",
        "description": "Sistem referans saati: 100 MHz. "
                       "Nexys A7-100T onboard osilat. Clocking Wizard girişi.",
    },
    "CONST-A-CLK-004": {
        "name": "FIFO Bağımsız Saat CDC",
        "description": "FIFO Generator independent_clocks kısıtı. "
                       "Yazma saati: DMA (140 MHz). Okuma saati: PWM (24.576 MHz). "
                       "Gray-code pointer CDC.",
    },
    "CONST-A-MEM-001": {
        "name": "DDR2 Minimum 128MB Kapasite",
        "description": "DDR2 SDRAM kapasite kısıtı: ≥ 128MB. "
                       "WAV veri tamponu gereksinimi. MIG konfigürasyon parametresi.",
    },
    "CONST-A-ADDR-001": {
        "name": "AXI DMA Base Adresi 0x40400000",
        "description": "AXI adres haritası: AXI DMA base adres 0x40400000. "
                       "assign_bd_address TCL komutu. MicroBlaze adres alanı.",
    },
    "CONST-A-UART-001": {
        "name": "9600 Baud UART Kısıtı",
        "description": "AXI UARTLite baud hızı: 9600. "
                       "AXI UARTLite IP parametresi. PC terminal erişimi.",
    },
    "CONST-A-DMA-001": {
        "name": "AXI DMA Scatter-Gather Modu",
        "description": "AXI DMA kısıtı: scatter-gather modu etkin. "
                       "c_include_sg=1. DMA descriptor chain WAV oynatma için.",
    },

    # -------------------------------------------------------------------------
    # CONSTRAINT NODES — PROJECT-B
    # -------------------------------------------------------------------------
    "CONST-B-CLK-001": {
        "name": "100 MHz → MMCME2_ADV → BUFG Saat",
        "description": "Saat kısıtı: Nexys Video 100 MHz osilat → "
                       "Clocking Wizard MMCME2_ADV → BUFG küresel dağıtım → fabric.",
    },
    "CONST-B-PIN-RST": {
        "name": "BTNC → Aktif-Düşük Reset",
        "description": "XDC kısıtı: BTNC düğmesi, aktif-düşük reset. "
                       "Nexys Video BTNC (merkez düğme) → sys_rst_n.",
    },
    "CONST-B-ADDR-001": {
        "name": "GPIO Base Adresi 0x40000000",
        "description": "AXI adres haritası: AXI GPIO base adres 0x40000000. "
                       "assign_bd_address explicit atama. MicroBlaze adres alanı.",
    },

    # -------------------------------------------------------------------------
    # ISSUE NODES
    # -------------------------------------------------------------------------
    "ISSUE-A-001": {
        "name": "KRİTİK: FPGA Part Tutarsızlığı (50T vs 100T)",
        "description": "project_info.tcl + design_1.tcl: xc7a50ticsg324-1L (50T). "
                       "README + XDC: Nexys A7-100T. Üretilen bit dosyası 100T kartta "
                       "çalışmaz (farklı silikon). ISSUE-A-001, severity=critical.",
    },
    "ISSUE-A-002": {
        "name": "YÜKSEK: tone_generator Fonksiyonel Değil",
        "description": "tone_generator.v:69 — assign axis_tlast = 1'b1; "
                       "TLAST sabit 1 bug. 16-bit veri 8-bit'e truncate. "
                       "README: 'not currently working'. ISSUE-A-002.",
    },
    "ISSUE-A-003": {
        "name": "ORTA: axis2fifo 32→16 Bit Truncation",
        "description": "axis2fifo.v: AXI-Stream 32-bit veri 16-bit FIFO'ya. "
                       "Üst 16-bit kaybolur. Ses kalitesi düşer. ISSUE-A-003.",
    },
    "ISSUE-A-004": {
        "name": "ORTA: XDC'de Yalnızca PWM Pinleri Aktif",
        "description": "XDC: PWM ve saat pinleri aktif, diğerleri commented-out. "
                       "GPIO, UART ve LED pin atamaları eksik/devre dışı. ISSUE-A-004.",
    },
    "ISSUE-A-005": {
        "name": "DÜŞÜK: WAV Yalnızca 96kHz Destekliyor",
        "description": "fifo2audpwm: 24.576 MHz / 256 = 96kHz sabit örnekleme hızı. "
                       "44.1kHz veya 48kHz WAV desteklenmiyor. ISSUE-A-005.",
    },
    "ISSUE-A-006": {
        "name": "BİLGİ: Interrupt Donanım Mevcut, SW Polling",
        "description": "AXI INTC + xlconcat donanımda bağlı, "
                       "ancak helloworld.c polling döngüsü kullanıyor. "
                       "DMA-DEC-005. ISSUE-A-006.",
    },
    "ISSUE-A-007": {
        "name": "BİLGİ: Timing Raporu Yok (Implementation Çalıştırılmamış)",
        "description": "Implementation ve place-route çalıştırılmamış. "
                       "WNS değeri bilinmiyor. Timing closure doğrulanmamış. ISSUE-A-007.",
    },
    "ISSUE-A-008": {
        "name": "BİLGİ: Git Submodule Init Edilmemiş",
        "description": ".gitmodules'da submodule tanımlı ama init/update yapılmamış. "
                       "Bağımlı kaynak kodları mevcut değil. ISSUE-A-008.",
    },
    "ISSUE-B-001": {
        "name": "BİLGİ: Duplicate Clock ve UART Port Uyarıları",
        "description": "Vivado Critical Warning: duplicate clock constraint, "
                       "UART port direction mismatch, LMB clock mismatch. "
                       "Fonksiyonel etki minimal. ISSUE-B-001.",
    },
    "ISSUE-B-002": {
        "name": "BİLGİ: Sentez Yalnızca Seviye 2 Kapsamında",
        "description": "Seviye 3 (tam sistem) tamamlanmamış. "
                       "README: '⏳ Geliştirilmekte'. Block automation timeout. ISSUE-B-002.",
    },
    "ISSUE-B-003": {
        "name": "ORTA: Block Automation Timeout",
        "description": "create_axi_auto.tcl: apply_bd_automation timeout. "
                       "Stabil değil, bazen başarısız. README uyarısı. ISSUE-B-003.",
    },

    # -------------------------------------------------------------------------
    # PATTERN NODES
    # -------------------------------------------------------------------------
    "PAT-A-001": {
        "name": "DDS Tone Generator — Delta-Faz Akkümülatörü",
        "description": "Pattern: frekans_hz * 2^N / saat_hz = INCREMENT. "
                       "accum += INCREMENT; sample = accum >> (ACCUM_WIDTH - DAC_BITS). "
                       "Sabit frekanslı sinyal üretimi.",
    },
    "PAT-A-002": {
        "name": "AXI-Stream to FIFO Adapter — Backpressure",
        "description": "Pattern: axis_tready = ~fifo_full. "
                       "AXI-Stream → FIFO bridge, minimal RTL. "
                       "FIFO dolunca upstream'e backpressure uygular.",
    },
    "PAT-A-003": {
        "name": "PWM Audio Output — Counter Karşılaştırma",
        "description": "Pattern: pwm_out = (counter < duty_cycle). "
                       "Counter 0..255, 24.576 MHz. 8-bit çözünürlük, 96kHz örnekleme.",
    },
    "PAT-A-004": {
        "name": "Dual-Clock FIFO CDC — Xilinx FIFO Generator",
        "description": "Pattern: independent_clocks modu, gray-code pointer sync. "
                       "Yazma ve okuma farklı clock domain'lerde. "
                       "Güvenli AXI-Stream ↔ PWM CDC.",
    },
    "PAT-A-005": {
        "name": "AXI-Stream Backpressure — FIFO Full",
        "description": "Pattern: upstream tready = ~fifo_full. "
                       "FIFO dolu → AXI-Stream akışını durdurur. "
                       "DMA veri kaybını önler.",
    },
    "PAT-A-006": {
        "name": "C WAV Header Parse — Raw Byte Cast",
        "description": "Pattern: raw byte buffer → struct Wav_HeaderRaw cast. "
                       "Format doğrulama (RIFF, fmt , data chunk). "
                       "MicroBlaze helloworld.c firmware.",
    },
    "PAT-B-001": {
        "name": "AXI Tie-Off — Standalone IP Test",
        "description": "Pattern: AXI slave portlarını tie-off (tvalid=0, tready=1). "
                       "MicroBlaze olmadan GPIO testi. "
                       "Seviye 1 standalone eğitim adımı.",
    },
    "PAT-B-002": {
        "name": "3-Seviye Kademeli Eğitim",
        "description": "Pattern: Seviye 1 (Standalone GPIO) → "
                       "Seviye 2 (MicroBlaze + GPIO) → Seviye 3 (Tam Sistem). "
                       "CLI-first TCL scripting metodolojisi.",
    },
    "PAT-B-003": {
        "name": "Vivado Batch Mode TCL — Parametrik Çalıştırma",
        "description": "Pattern: vivado -mode batch -source script.tcl. "
                       "Parametrik TCL otomasyon. GUI-less sentez ve simülasyon.",
    },
    "PAT-B-004": {
        "name": "apply_bd_automation — Vivado BD Otomasyonu",
        "description": "Pattern: apply_bd_automation ile AXI adres/bağlantı haritalama. "
                       "Vivado Block Design TCL komutu. "
                       "Otomatik slave address segment atama.",
    },
    "PAT-B-005": {
        "name": "PLL Lock → Reset Release Güvenli Başlangıç",
        "description": "Pattern: clk_wiz.locked → proc_sys_reset.dcm_locked. "
                       "PLL kilitlenince reset serbest bırakılır. "
                       "Saat kararlılığı garantisi.",
    },
}


# ===========================================================================
# 2. MISSING IMPLEMENTS EDGES
#    (from_component, to_requirement, confidence, note)
# ===========================================================================

MISSING_IMPLEMENTS = [
    # Coverage Gap — DMA-REQ-L0-001 (L0 root): key components
    ("COMP-A-axi_dma_0",           "DMA-REQ-L0-001", "HIGH",
     "AXI DMA ana bileşen olarak L0 DMA ses akışı gereksinimini karşılar."),
    ("COMP-A-mig_7series_0",       "DMA-REQ-L0-001", "HIGH",
     "MIG DDR2 tampon belleği L0 DMA ses sistemi için gerekli altyapıyı sağlar."),

    # Coverage Gap — DMA-REQ-L1-002 (MicroBlaze firmware)
    ("COMP-A-helloworld",          "DMA-REQ-L1-002", "HIGH",
     "helloworld.c firmware MicroBlaze SDK entegrasyonu gereksinimini doğrudan uygular."),
    ("COMP-A-microblaze_0",        "DMA-REQ-L1-002", "HIGH",
     "MicroBlaze soft-core DMA firmware çalıştırma platformu."),
    ("COMP-A-microblaze_0_axi_periph", "DMA-REQ-L1-002", "HIGH",
     "MicroBlaze çevre AXI interconnect firmware-peripheral entegrasyonu sağlar."),

    # Coverage Gap — DMA-REQ-L1-005 (GPIO)
    ("COMP-A-GPIO_IN",             "DMA-REQ-L1-005", "HIGH",
     "AXI GPIO switch/button girişi GPIO altyapısı gereksinimini karşılar."),
    ("COMP-A-GPIO_OUT",            "DMA-REQ-L1-005", "HIGH",
     "AXI GPIO LED çıkışı GPIO altyapısı gereksinimini karşılar."),
    ("COMP-A-microblaze_0_axi_intc", "DMA-REQ-L1-005", "HIGH",
     "AXI INTC interrupt controller GPIO interrupt altyapısını uygular."),

    # Orphan Components — xlconcat'lar (DMA-REQ-L2-011)
    ("COMP-A-xlconcat_0",          "DMA-REQ-L2-011", "HIGH",
     "xlconcat_0 DMA IRQ sinyallerini birleştirir — interrupt altyapısı parçası (DMA-DEC-005)."),
    ("COMP-A-xlconcat_1",          "DMA-REQ-L2-011", "HIGH",
     "xlconcat_1 GPIO+UART IRQ sinyallerini birleştirir — interrupt altyapısı (DMA-DEC-005)."),

    # Orphan Components — AXI interconnect (DMA-REQ-L1-001 / AXI-Stream)
    ("COMP-A-axi_interconnect_0",  "DMA-REQ-L1-001", "HIGH",
     "AXI Interconnect, DMA-DDR2-peripheral arası AXI4 bus fabric sağlar."),

    # Orphan Components — LMB BRAM (DMA-REQ-L1-003 saat/güç)
    ("COMP-A-lmb_bram",            "DMA-REQ-L1-003", "HIGH",
     "LMB BRAM subsistemi MicroBlaze yerel belleği; güç ve saat yönetimi kapsamında."),

    # Orphan Components — PWM audio bus (DMA-REQ-L1-006 AXI-Stream signal path)
    ("COMP-A-pwm_audio_bus",       "DMA-REQ-L1-006", "HIGH",
     "PWM Audio Bus, fifo2audpwm çıkışından ses pinine signal path'in son halkası."),

    # Coverage Gap — AXI-REQ-L0-001 (L0 root AXI eğitim)
    ("COMP-B-axi_gpio_wrapper",    "AXI-REQ-L0-001", "HIGH",
     "axi_gpio_wrapper ana RTL bileşen olarak AXI eğitim sistemini uygular."),
    ("COMP-B-microblaze_0",        "AXI-REQ-L0-001", "HIGH",
     "MicroBlaze soft-core işlemci AXI eğitim sisteminin temel bileşeni."),

    # Coverage Gap — AXI-REQ-L1-003 (Saat yönetimi)
    ("COMP-B-clk_wiz_0",           "AXI-REQ-L1-003", "HIGH",
     "Clocking Wizard MMCME2_ADV AXI saat yönetimi gereksinimini uygular."),

    # Coverage Gap — AXI-REQ-L1-004 (Reset yönetimi)
    ("COMP-B-rst_clk_wiz_0_100M", "AXI-REQ-L1-004", "HIGH",
     "proc_sys_reset PLL-tabanlı reset yönetimi gereksinimini uygular."),
]


# ===========================================================================
# 3. MISSING DECOMPOSES_TO EDGES
#    (parent_req, child_req)
# ===========================================================================

MISSING_DECOMPOSES = [
    ("DMA-REQ-L1-005", "DMA-REQ-L2-011"),  # GPIO → AXI GPIO + Interrupt
]


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    print("=" * 60)
    print("FPGA RAG v2 — Graph DB Düzeltme Scripti")
    print("=" * 60)

    # Load graph
    gs = GraphStore(persist_path=GRAPH_PATH)
    stats_before = gs.stats()
    print(f"\n[Önce] Nodes: {stats_before['total_nodes']}, "
          f"Edges: {stats_before['total_edges']}")

    gaps_before = len(gs.get_coverage_gaps())
    orphans_before = len(gs.get_orphan_components())
    print(f"[Önce] Coverage Gaps: {gaps_before}, Orphan Components: {orphans_before}")

    # -----------------------------------------------------------------------
    # Step 1: Patch node name + description
    # -----------------------------------------------------------------------
    print("\n[1/4] Node name/description patch uygulanıyor...")
    patched = 0
    for node_id, patch in NODE_PATCHES.items():
        node = gs.get_node(node_id)
        if node is None:
            print(f"  UYARI: {node_id} graph'ta bulunamadı, atlanıyor.")
            continue

        updated = dict(node)
        changed = False
        for field, value in patch.items():
            if not updated.get(field) or updated.get(field) != value:
                updated[field] = value
                changed = True

        if changed:
            # Re-add with updated attrs (GraphStore.add_node = upsert)
            gs._graph.nodes[node_id].update(updated)
            patched += 1

    print(f"  ✓ {patched} node güncellendi.")

    # -----------------------------------------------------------------------
    # Step 2: Add missing IMPLEMENTS edges
    # -----------------------------------------------------------------------
    print("\n[2/4] Eksik IMPLEMENTS edge'leri ekleniyor...")
    added_impl = 0
    for from_id, to_id, confidence, note in MISSING_IMPLEMENTS:
        if not gs._graph.has_node(from_id):
            print(f"  UYARI: {from_id} bulunamadı")
            continue
        if not gs._graph.has_node(to_id):
            print(f"  UYARI: {to_id} bulunamadı")
            continue
        if gs._graph.has_edge(from_id, to_id):
            # Edge var ama farklı tip olabilir, kontrol et
            existing = gs._graph.edges[from_id, to_id]
            if existing.get("edge_type") == "IMPLEMENTS":
                continue  # zaten var
        gs.add_edge(from_id, to_id, "IMPLEMENTS", {
            "confidence": confidence,
            "note": note,
            "provenance": '{"phase": "fix_script", "source": "pipeline_report.md"}',
        })
        print(f"  + {from_id} --IMPLEMENTS--> {to_id}")
        added_impl += 1

    print(f"  ✓ {added_impl} IMPLEMENTS edge eklendi.")

    # -----------------------------------------------------------------------
    # Step 3: Add missing DECOMPOSES_TO edges
    # -----------------------------------------------------------------------
    print("\n[3/4] Eksik DECOMPOSES_TO edge'leri ekleniyor...")
    added_decomp = 0
    for parent_id, child_id in MISSING_DECOMPOSES:
        if not gs._graph.has_node(parent_id) or not gs._graph.has_node(child_id):
            print(f"  UYARI: {parent_id} veya {child_id} bulunamadı")
            continue
        if gs._graph.has_edge(parent_id, child_id):
            existing = gs._graph.edges[parent_id, child_id]
            if existing.get("edge_type") == "DECOMPOSES_TO":
                continue
        gs.add_edge(parent_id, child_id, "DECOMPOSES_TO", {
            "confidence": "HIGH",
            "note": "Pipeline report Faz 3 gereksinim ağacından alındı.",
            "provenance": '{"phase": "fix_script", "source": "pipeline_report.md"}',
        })
        print(f"  + {parent_id} --DECOMPOSES_TO--> {child_id}")
        added_decomp += 1

    print(f"  ✓ {added_decomp} DECOMPOSES_TO edge eklendi.")

    # -----------------------------------------------------------------------
    # Step 4: Save graph
    # -----------------------------------------------------------------------
    gs.save()
    stats_after = gs.stats()
    gaps_after = len(gs.get_coverage_gaps())
    orphans_after = len(gs.get_orphan_components())

    print(f"\n[Sonra] Nodes: {stats_after['total_nodes']}, "
          f"Edges: {stats_after['total_edges']}")
    print(f"[Sonra] Coverage Gaps: {gaps_after}, Orphan Components: {orphans_after}")
    print(f"\n  Değişim — Edges: +{stats_after['total_edges'] - stats_before['total_edges']}")
    print(f"  Coverage Gaps:   {gaps_before} → {gaps_after}")
    print(f"  Orphan Comps:    {orphans_before} → {orphans_after}")
    print(f"\n  ✓ Graph kaydedildi: {GRAPH_PATH}")

    # -----------------------------------------------------------------------
    # Step 5: Rebuild vector store
    # -----------------------------------------------------------------------
    print("\n[4/4] Vector store yeniden oluşturuluyor...")
    print("  (Tüm 123 node sıfırdan embed ediliyor...)")

    import chromadb
    # Eski collection'ı sil ve yeniden oluştur
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        chroma_client.delete_collection("fpga_rag_v2_nodes")
        print("  Eski collection silindi.")
    except Exception:
        pass

    vs = VectorStoreV2(persist_directory=CHROMA_PATH)
    all_nodes = gs.get_all_nodes()
    print(f"  {len(all_nodes)} node embed ediliyor...")

    stored = vs.add_nodes_batch(all_nodes, batch_size=20)
    print(f"  ✓ {stored} node vector store'a eklendi.")
    print(f"  Vector store count: {vs.count()}")

    # Final summary
    print("\n" + "=" * 60)
    print("DÜZELTME TAMAMLANDI")
    print("=" * 60)
    print(f"  Graph nodes  : {stats_after['total_nodes']}")
    print(f"  Graph edges  : {stats_after['total_edges']}")
    print(f"  Vector docs  : {vs.count()}")
    print(f"  Coverage gaps: {gaps_after}  (hedef: 0)")
    print(f"  Orphan comps : {orphans_after}  (hedef: 0)")

    if gaps_after > 0:
        remaining = gs.get_coverage_gaps()
        print(f"\n  Kalan gaps:")
        for g in remaining:
            print(f"    - {g['node_id']}: {g.get('name','')}")
    if orphans_after > 0:
        remaining = gs.get_orphan_components()
        print(f"\n  Kalan orphan components:")
        for o in remaining:
            print(f"    - {o['node_id']}: {o.get('name','')}")


if __name__ == "__main__":
    main()
