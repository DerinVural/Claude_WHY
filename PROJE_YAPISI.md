# FPGA RAG v2 — Proje Yapısı Detaylı Dökümanı

**Tarih:** 2026-02-25
**Versiyon:** RAG v2
**Durum:** Aktif — Robustness 0.839/A · 20q Benchmark 0.796/A

---

## İçindekiler

1. [Genel Bakış](#1-genel-bakış)
2. [Kapsanan FPGA Projeleri](#2-kapsanan-fpga-projeleri)
3. [Knowledge Graph — Tam Node Kataloğu](#3-knowledge-graph--tam-node-kataloğu)
   - 3.1 PROJECT Nodes
   - 3.2 REQUIREMENT Nodes
   - 3.3 COMPONENT Nodes
   - 3.4 DECISION Nodes
   - 3.5 CONSTRAINT Nodes
   - 3.6 ISSUE Nodes
   - 3.7 PATTERN Nodes
   - 3.8 EVIDENCE Nodes
   - 3.9 SOURCE_DOC Nodes
4. [Knowledge Graph — Edge (İlişki) Kataloğu](#4-knowledge-graph--edge-ilişki-kataloğu)
5. [Source Chunk Store](#5-source-chunk-store)
6. [Sorgu Sistemi](#6-sorgu-sistemi)
7. [Anti-Hallüsinasyon Katmanları](#7-anti-hallüsinasyon-katmanları)
8. [LLM Sistem Promptu — 11 Kural](#8-llm-sistem-promptu--11-kural)
9. [Yazılım Modülleri](#9-yazılım-modülleri)
10. [Test Sistemi](#10-test-sistemi)
11. [Dosya ve Dizin Yapısı](#11-dosya-ve-dizin-yapısı)

---

## 1. Genel Bakış

FPGA RAG v2, iki FPGA tasarım projesine ait teknik bilgiyi yapılandırılmış bir knowledge graph'ta depolayan ve doğal dil soruları (Türkçe) yanıtlayan bir **Retrieval-Augmented Generation** sistemidir.

### Veritabanı Özeti

| Bileşen | Boyut | Teknoloji |
|---------|-------|-----------|
| Knowledge Graph | **155 node, 495 edge** | NetworkX + JSON |
| Node Vector DB | **155 döküman** | ChromaDB (`fpga_rag_v2_nodes`) |
| Source Chunk DB | **151 chunk** | ChromaDB (`source_chunks`) |
| Embedding Modeli | `all-MiniLM-L6-v2` | Sentence-Transformers |
| LLM (Birincil) | `claude-sonnet-4-6` | Anthropic API |
| LLM (Fallback) | `gpt-4o-mini` | OpenAI API |

### Node Tipi Dağılımı

```
REQUIREMENT  ████████████████████████████████  31
COMPONENT    ██████████████████████████████    30
EVIDENCE     █████████████████████             21
SOURCE_DOC   ████████████████████              20
ISSUE        ██████████████                    14
CONSTRAINT   █████████████                     13
PATTERN      ████████████                      12
DECISION     ████████████                      12
PROJECT      ██                                 2
─────────────────────────────────────────────────
TOPLAM                                        155
```

### Edge Tipi Dağılımı

```
VERIFIED_BY      ████████████████████████████████  155
IMPLEMENTS       ████████████████████████████████  149
CONSTRAINED_BY   ████████████████████████████      102
DECOMPOSES_TO    ███████                            30
DEPENDS_ON       █████                              19
REUSES_PATTERN   ████                               13
MOTIVATED_BY     ███                                11
ANALOGOUS_TO     ██                                  8
INFORMED_BY      ██                                  7
CONTRADICTS      █                                   1
─────────────────────────────────────────────────────
TOPLAM                                             495
```

---

## 2. Kapsanan FPGA Projeleri

### PROJECT-A: nexys_a7_dma_audio

| Özellik | Değer |
|---------|-------|
| **Kart** | Digilent Nexys A7-100T |
| **FPGA** | Xilinx Artix-7 xc7a100tcsg324-1 |
| **Amaç** | DMA tabanlı ses akışı demo uygulaması |
| **İşlemci** | MicroBlaze v10.0 soft-core |
| **Bellek** | 128MB DDR2 SDRAM (MIG 7-Series) |
| **Saatler** | 140.625 MHz (DDR2) + 24.576 MHz (PWM ses) |
| **Geliştirme Ortamı** | Vivado + Xilinx SDK (C firmware) |
| **Kayıt Yolu** | `data/code/Nexys-A7-100T-DMA-Audio/` |

**Mimari Özeti:**
```
MicroBlaze ──AXI4──> AXI Interconnect ──┬──> AXI DMA ──AXI-Stream──> axis2fifo
                                         ├──> MIG DDR2 (128MB)        │
                                         ├──> AXI GPIO (SW/BTN/LED)   ▼
                                         ├──> AXI UARTLite (9600bd)  FIFO Gen (512×16)
                                         └──> AXI INTC                │
                                                                       ▼
                                                               fifo2audpwm ──> PWM Ses
```

---

### PROJECT-B: axi_gpio_example

| Özellik | Değer |
|---------|-------|
| **Kart** | Digilent Nexys Video |
| **FPGA** | Xilinx Artix-7 xc7a200tsbg484-1 |
| **Amaç** | AXI bus mimarisi eğitim / validasyon test suite |
| **İşlemci** | MicroBlaze v11.0 soft-core |
| **Bellek** | 8KB LMB BRAM (cache yok — eğitimsel) |
| **Saat** | 100 MHz (MMCME2_ADV) |
| **Geliştirme Ortamı** | Vivado — TCL batch modu |
| **Kayıt Yolu** | `data/code/axi_gpio_example/` |

**3-Seviyeli Eğitim Yapısı:**
```
Seviye 1: simple_top.v ──> Standalone GPIO (AXI tie-off, MicroBlaze yok)
Seviye 2: MicroBlaze + AXI GPIO (minimal sistem)
Seviye 3: Tam sistem (⏳ geliştiriliyor)
```

---

## 3. Knowledge Graph — Tam Node Kataloğu

### 3.1 PROJECT Nodes (2 adet)

| Node ID | Ad | Açıklama |
|---------|----|----------|
| `PROJECT-A` | Nexys-A7-100T-DMA-Audio | Digilent Nexys A7-100T üzerinde DMA tabanlı ses akışı demo |
| `PROJECT-B` | axi_example | AXI bus mimarisi eğitim / validasyon test suite |

---

### 3.2 REQUIREMENT Nodes (31 adet)

Gereksinimler L0→L1→L2 hiyerarşisiyle `DECOMPOSES_TO` edge'leriyle bağlıdır.
**Tüm 31 gereksinim `IMPLEMENTS` edge'iyle en az bir component'a bağlıdır (Coverage Gap = 0).**

#### PROJECT-A — nexys_a7_dma_audio (18 Gereksinim)

| ID | Ad | Seviye | Confidence | Karşılayan Component |
|----|----|----|-----------|-------------------|
| `DMA-REQ-L0-001` | DMA Tabanlı Ses Akışı | L0 | HIGH | axi_dma_0, mig_7series_0 |
| `DMA-REQ-L1-001` | DDR2 Tamponlu Ses Akışı | L1 | HIGH | axi_dma_0, axi_interconnect_0 |
| `DMA-REQ-L1-002` | MicroBlaze Firmware + SDK Entegrasyonu | L1 | HIGH | microblaze_0, helloworld, periph |
| `DMA-REQ-L1-003` | Güç ve Saat Yönetimi | L1 | HIGH | microblaze_0, lmb_bram |
| `DMA-REQ-L1-004` | Debug Altyapısı (JTAG MDM) | L1 | HIGH | mig_7series_0 |
| `DMA-REQ-L1-005` | GPIO Altyapısı (Switch/Button/LED) | L1 | HIGH | microblaze_0_axi_intc, GPIO_IN, GPIO_OUT |
| `DMA-REQ-L1-006` | AXI-Stream Sinyal Yolu | L1 | HIGH | axis2fifo_0, fifo2audpwm_0, fifo_generator_0 |
| `DMA-REQ-L2-001` | FPGA Part Kısıtı (xc7a100t) | L2 | HIGH | mig_7series_0 |
| `DMA-REQ-L2-002` | DDR2 ≥128MB + MIG Arbitrasyon | L2 | HIGH | fifo2audpwm_0 |
| `DMA-REQ-L2-003` | Donanım Ton Üreticisi [PARSE_UNCERTAIN] | L2 | HIGH | tone_generator_0 |
| `DMA-REQ-L2-004` | Çift-Saat FIFO CDC (512×16) | L2 | HIGH | fifo_generator_0 |
| `DMA-REQ-L2-005` | DMA Scatter-Gather Modu | L2 | HIGH | axi_uartlite_0, helloworld |
| `DMA-REQ-L2-006` | WAV 96kHz Ses Oynatma | L2 | HIGH | GPIO_IN, GPIO_OUT |
| `DMA-REQ-L2-007` | UART Serial Konsol (9600 baud) | L2 | HIGH | helloworld |
| `DMA-REQ-L2-008` | Saat Mimarisi (140.625 + 24.576 MHz) | L2 | HIGH | clk_wiz_0 |
| `DMA-REQ-L2-009` | Reset Zinciri (MIG Tabanlı) | L2 | HIGH | rst_mig_7series_0_81M |
| `DMA-REQ-L2-010` | JTAG MDM Debug | L2 | HIGH | mdm_1 |
| `DMA-REQ-L2-011` | AXI GPIO + Interrupt Altyapısı | L2 | MEDIUM | microblaze_0_axi_intc, xlconcat_0, xlconcat_1 |

#### PROJECT-B — axi_gpio_example (13 Gereksinim)

| ID | Ad | Seviye | Confidence | Karşılayan Component |
|----|----|----|-----------|-------------------|
| `AXI-REQ-L0-001` | AXI Bus Eğitim/Validasyon Test Suite | L0 | HIGH | axi_gpio_wrapper, microblaze_0 |
| `AXI-REQ-L1-001` | GPIO Kontrolü — LED/Switch I/O | L1 | HIGH | axi_gpio_0 |
| `AXI-REQ-L1-002` | MicroBlaze Soft-Core İşlemci | L1 | HIGH | microblaze_0 |
| `AXI-REQ-L1-003` | Saat Yönetimi (Clocking Wizard) | L1 | HIGH | clk_wiz_0 |
| `AXI-REQ-L1-004` | Reset Yönetimi (proc_sys_reset) | L1 | HIGH | rst_clk_wiz_0_100M |
| `AXI-REQ-L1-005` | AXI-Lite Sinyal Yolu | L1 | HIGH | axi_gpio_wrapper, rst_clk_wiz_0_100M |
| `AXI-REQ-L2-001` | GPIO Base Adresi = 0x40000000 | L2 | HIGH | axi_gpio_wrapper |
| `AXI-REQ-L2-002` | 8KB LMB BRAM, Cache Yok | L2 | HIGH | simple_top |
| `AXI-REQ-L2-003` | 100 MHz → MMCME2_ADV → Fabric | L2 | HIGH | clk_wiz_0 |
| `AXI-REQ-L2-004` | WNS > 0 ns (Synthesis Verify) | L2 | HIGH | lmb_subsystem |
| `AXI-REQ-L2-005` | WNS > 0 ns ile Synthesis PASS | L2 | HIGH | microblaze_0_axi_periph |
| `AXI-REQ-L2-006` | PLL Lock → Reset Release | L2 | HIGH | rst_clk_wiz_0_100M |
| `AXI-REQ-L2-007` | 3 Seviyeli Kademeli İlerleme | L2 | HIGH | mdm_1 |

---

### 3.3 COMPONENT Nodes (30 adet)

#### PROJECT-A Componentleri (21 adet)

| Node ID | Ad | IP/Modül | Açıklama |
|---------|----|----------|----------|
| `COMP-A-microblaze_0` | MicroBlaze v10.0 | Xilinx IP | Soft-core işlemci. AXI4 master. LMB BRAM. DMA/WAV kontrol firmware'ı çalıştırır |
| `COMP-A-mig_7series_0` | MIG 7-Series DDR2 | Xilinx IP | 128MB DDR2 SDRAM controller. 140.625 MHz UI clock. AXI4 slave port |
| `COMP-A-axi_dma_0` | AXI DMA 7.1 | Xilinx IP | **NOT:** Node'da Simple mode yazıyor, key_logic'te SG mode. Scatter-Gather desteği. MM2S kanalı |
| `COMP-A-axi_interconnect_0` | AXI Interconnect | Xilinx IP | MicroBlaze AXI4 master → DMA, MIG, GPIO, UART, INTC slave'lerine bağlar |
| `COMP-A-microblaze_0_axi_periph` | AXI Periph Interconnect | Xilinx IP | Çevre aygıt AXI veri yolu |
| `COMP-A-microblaze_0_axi_intc` | AXI INTC v4.1 | Xilinx IP | Interrupt controller. DMA MM2S/S2MM + GPIO + UART IRQ toplar |
| `COMP-A-clk_wiz_0` | Clocking Wizard v6.0 | Xilinx IP | MMCME2_ADV. 100 MHz → 140.625 MHz (DDR2) + 24.576 MHz (PWM) |
| `COMP-A-rst_mig_7series_0_81M` | proc_sys_reset v5.0 | Xilinx IP | MIG DDR2 init_calib_complete → reset release zinciri |
| `COMP-A-mdm_1` | MDM v3.2 | Xilinx IP | MicroBlaze JTAG debug modülü |
| `COMP-A-fifo_generator_0` | FIFO Generator v13.2 | Xilinx IP | Independent_clocks CDC FIFO. 512 derinlik × 16 bit. Gray-code sync |
| `COMP-A-axi_uartlite_0` | AXI UARTLite v2.0 | Xilinx IP | 9600 baud serial konsol |
| `COMP-A-lmb_bram` | LMB BRAM | Xilinx IP | 64KB instruction + data BRAM. MicroBlaze yerel belleği |
| `COMP-A-xlconcat_0` | xlconcat v2.1 | Xilinx Utility | DMA mm2s_introut + s2mm_introut → INTC |
| `COMP-A-xlconcat_1` | xlconcat v2.1 | Xilinx Utility | GPIO_IN + UARTLite interrupt → INTC |
| `COMP-A-GPIO_IN` | AXI GPIO (Çift Kanal) | Xilinx IP | Switch + button girişi. WAV oynatma tetikleyici |
| `COMP-A-GPIO_OUT` | AXI GPIO | Xilinx IP | LED çıkışı. Oynatma durum göstergesi |
| `COMP-A-axis2fifo_0` | axis2fifo | RTL (Verilog) | AXI-Stream TVALID/TREADY → FIFO yazma adaptörü. 32→16 bit truncation |
| `COMP-A-fifo2audpwm_0` | fifo2audpwm | RTL (Verilog) | FIFO → 8-bit PWM ses çıkışı. 24.576 MHz / 256 = 96 kHz |
| `COMP-A-tone_generator_0` | tone_generator **[BUG]** | RTL (Verilog) | DDS tabanlı ton üretici. **BOZUK:** axis_tlast=1 sabit, 16→8 bit truncation |
| `COMP-A-pwm_audio_bus` | PWM Audio Bus | Özel sinyal yolu | pwm_out + aud_en → Nexys A7 ses çıkışı |
| `COMP-A-helloworld` | helloworld.c | C Firmware | MicroBlaze yazılımı. DMA SG setup, WAV oynatma, UART konsol, GPIO izleme |

#### PROJECT-B Componentleri (9 adet)

| Node ID | Ad | IP/Modül | Açıklama |
|---------|----|----------|----------|
| `COMP-B-microblaze_0` | MicroBlaze v11.0 | Xilinx IP | Soft-core işlemci. 8KB LMB BRAM. Cache yok. AXI4 master |
| `COMP-B-axi_gpio_0` | AXI GPIO v2.0 | Xilinx IP | LED çıkışı + switch girişi. Base adres 0x40000000. AXI-Lite slave |
| `COMP-B-axi_gpio_wrapper` | axi_gpio_wrapper | RTL (Verilog) | AXI GPIO IP'yi saran wrapper. PAT-B-001 AXI tie-off pattern |
| `COMP-B-clk_wiz_0` | Clocking Wizard v6.0 | Xilinx IP | MMCME2_ADV. Nexys Video 100 MHz → 100 MHz fabric |
| `COMP-B-rst_clk_wiz_0_100M` | proc_sys_reset v5.0 | Xilinx IP | clk_wiz.locked → reset release. 100 MHz domain |
| `COMP-B-microblaze_0_axi_periph` | AXI Interconnect | Xilinx IP | MicroBlaze → AXI GPIO slave. AXI4-Lite veri yolu |
| `COMP-B-lmb_subsystem` | LMB Memory Subsistemi | Xilinx IP | dlmb + ilmb + bram_if_cntlr + blk_mem_gen. 8KB BRAM |
| `COMP-B-mdm_1` | MDM v3.2 | Xilinx IP | JTAG debug + UART debug. MicroBlaze breakpoint |
| `COMP-B-simple_top` | simple_top | RTL (Verilog) | Seviye 1 standalone GPIO testi. AXI tie-off pattern |

---

### 3.4 DECISION Nodes (12 adet)

Tasarım sürecinde alınan teknik kararlar. Tümü HIGH confidence.

#### PROJECT-A Kararları (7 adet)

| ID | Karar | Gerekçe |
|----|-------|---------|
| `DMA-DEC-001` | Xilinx AXI DMA IP 7.1 | Vivado IP entegrasyonu, SG desteği |
| `DMA-DEC-002` | MIG 7-Series DDR2 128MB tamponu | 96kHz WAV için yeterli bant genişliği |
| `DMA-DEC-003` | MicroBlaze soft-core (ARM yerine) | Eğitimsel amaç, tam donanım kontrolü |
| `DMA-DEC-004` | AXI-Stream ses veri yolu | Standart protokol, CDC FIFO ile saat geçişi |
| `DMA-DEC-005` | Interrupt donanımda var, SW polling kullanıyor *(MEDIUM)* | Prototip aşamasında sadelik |
| `DEC-A-bitstream-001` | Bitstream + ELF gömme (updatemem) | İki aşamalı dağıtım süreci |
| `DEC-A-interrupt-001` | AXI INTC hazır ama kullanılmıyor | Polling → interrupt geçiş yol haritası |

#### PROJECT-B Kararları (5 adet)

| ID | Karar | Gerekçe |
|----|-------|---------|
| `AXI-DEC-001` | AXI4-Lite çevre veri yolu | Eğitimsel sadelik, burst gereksiz |
| `AXI-DEC-002` | MicroBlaze v11.0 Vivado 2025.1 | AXI4 master, LMB BRAM minimal kurulum |
| `AXI-DEC-003` | AXI GPIO IP ile LED/switch | AXI4-Lite eğitimi için ideal |
| `AXI-DEC-004` | CLI-First TCL scripting | Tekrarlanabilirlik, versiyon kontrolü |
| `AXI-DEC-005` | MMCME2_ADV saat üretimi | Nexys Video 100 MHz → fabric clock |

---

### 3.5 CONSTRAINT Nodes (13 adet)

#### PROJECT-A Kısıtları (10 adet)

| ID | Kısıt | Değer |
|----|-------|-------|
| `CONST-A-CLK-001` | MIG DDR2 UI Clock | **140.625 MHz** |
| `CONST-A-CLK-002` | PWM Ses Saati | **24.576 MHz** → 96kHz örnekleme |
| `CONST-A-CLK-003` | Referans Saati | **100 MHz** (onboard osilat) |
| `CONST-A-CLK-004` | FIFO Bağımsız Saat CDC | Yazma: 140 MHz / Okuma: 24.576 MHz |
| `CONST-A-ADDR-001` | AXI DMA Base Adres | **0x40400000** |
| `CONST-A-DMA-001` | DMA Modu | Simple modu (c_include_sg=0) |
| `CONST-A-MEM-001` | DDR2 Minimum Kapasite | **≥128MB** |
| `CONST-A-PIN-001` | PWM Ses Çıkış Pini | **PACKAGE_PIN J5** · LVCMOS33 · 12mA |
| `CONST-A-PIN-002` | Sistem Saat Girişi | **PACKAGE_PIN E3** · LVCMOS33 |
| `CONST-A-UART-001` | UART Baud Hızı | **9600 baud** |

#### PROJECT-B Kısıtları (3 adet)

| ID | Kısıt | Değer |
|----|-------|-------|
| `CONST-B-ADDR-001` | GPIO Base Adres | **0x40000000** |
| `CONST-B-CLK-001` | Fabric Clock | 100 MHz → MMCME2_ADV → BUFG |
| `CONST-B-PIN-RST` | Reset Düğmesi | **BTNC** → aktif-düşük reset |

---

### 3.6 ISSUE Nodes (14 adet)

Bilinen sorunlar. Tümü HIGH confidence ile kayıtlı.

#### PROJECT-A Sorunları (10 adet)

| ID | Önem | Sorun |
|----|------|-------|
| `ISSUE-A-001` | **KRİTİK** | FPGA Part Tutarsızlığı: proje_info.tcl 50T yazıyor, README 100T diyor |
| `ISSUE-A-002` | **YÜKSEK** | tone_generator.v çalışmıyor: `axis_tlast = 1'b1` sabit atanmış (satır 69) |
| `ISSUE-A-003` | ORTA | axis2fifo 32→16 bit truncation: üst 16-bit ses verisi kaybolur |
| `ISSUE-A-004` | ORTA | XDC'de yalnızca PWM ve saat pinleri aktif; GPIO/UART/LED commentted-out |
| `ISSUE-A-005` | DÜŞÜK | WAV yalnızca 96kHz destekliyor (44.1kHz/48kHz desteksiz) |
| `ISSUE-A-006` | BİLGİ | Interrupt donanımı hazır ancak firmware polling kullanıyor |
| `ISSUE-A-007` | BİLGİ | Timing raporu yok — implementation çalıştırılmamış, WNS bilinmiyor |
| `ISSUE-A-008` | BİLGİ | Git submodule init edilmemiş, bağımlı kaynak kodları eksik |
| `ISSUE-A-drc-002` | — | Vivado DRC uyarıları: MIG sys_rst aktif-yüksek/düşük uyumsuzluğu |
| `ISSUE-A-timeout-001` | — | helloworld.c'de DMA polling döngüsünde timeout mekanizması yok |

#### PROJECT-B Sorunları (4 adet)

| ID | Önem | Sorun |
|----|------|-------|
| `ISSUE-B-001` | BİLGİ | Vivado Critical Warning: duplicate clock constraint, UART port direction mismatch |
| `ISSUE-B-002` | BİLGİ | Seviye 3 (tam sistem) tamamlanmamış — geliştirme devam ediyor |
| `ISSUE-B-003` | ORTA | `apply_bd_automation` timeout: create_axi_auto.tcl bazen başarısız |
| `ISSUE-B-drc-001` | — | DRC: NSTD-1 tanımsız I/O standard uyarıları |

---

### 3.7 PATTERN Nodes (12 adet)

Yeniden kullanılabilir tasarım desenleri.

#### PROJECT-A Desenleri (6 adet)

| ID | Desen Adı | Özet |
|----|-----------|------|
| `PAT-A-001` | DDS Tone Generator — Delta-Faz Akkümülatörü | `INCREMENT = freq * 2^N / clk`. Faz akümülatörü tabanlı ton üretimi |
| `PAT-A-002` | AXI-Stream to FIFO Adapter — Backpressure | `axis_tready = ~fifo_full`. Minimal RTL köprü |
| `PAT-A-003` | PWM Audio Output — Counter Karşılaştırma | `pwm_out = (counter < duty_cycle)`. 0-255 sayaç, 24.576 MHz |
| `PAT-A-004` | Dual-Clock FIFO CDC — Xilinx FIFO Generator | Independent_clocks, gray-code pointer senkronizasyonu |
| `PAT-A-005` | AXI-Stream Backpressure — FIFO Full | Upstream `tready = ~fifo_full`. Veri kaybını önler |
| `PAT-A-006` | C WAV Header Parse — Raw Byte Cast | `raw byte buffer → struct Wav_HeaderRaw cast`. Format doğrulama |

#### PROJECT-B Desenleri (6 adet)

| ID | Desen Adı | Özet |
|----|-----------|------|
| `PAT-B-001` | AXI Tie-Off — Standalone IP Test | AXI slave portları tie-off (`tvalid=0, tready=1`). MicroBlaze'siz GPIO testi |
| `PAT-B-002` | 3-Seviye Kademeli Eğitim | Standalone → MicroBlaze+GPIO → Tam sistem ilerleme metodolojisi |
| `PAT-B-003` | Vivado Batch Mode TCL | `vivado -mode batch -source script.tcl`. GUI'siz sentez |
| `PAT-B-004` | apply_bd_automation — Vivado BD Otomasyonu | AXI adres/bağlantı haritalama otomasyonu |
| `PAT-B-005` | PLL Lock → Reset Release | `clk_wiz.locked → proc_sys_reset.dcm_locked`. Güvenli başlangıç |
| `PAT-B-toplevel-001` | Top-Level Port Analizi | Diferansiyel clock + GPIO portlarından mimari çıkarımı |

---

### 3.8 EVIDENCE Nodes (21 adet)

Her node için kaynak belge kanıtları. Tüm node'lar `VERIFIED_BY` edge'iyle en az bir evidence'a bağlı.

#### PROJECT-A Evidence (16 adet)

| ID | Kaynak | Kanıtlanan |
|----|--------|-----------|
| `EVID-A-001` | axis2fifo.v satır 35 | `assign fifo_wr_data = axis_tdata[15:0]` — 32→16 bit truncation |
| `EVID-A-002` | mig_7series_0.tcl | 128MB DDR2 + 140.625 MHz UI clock |
| `EVID-A-003` | tone_generator.v satır 69 | `assign axis_tlast = 1'b1` — tlast bug |
| `EVID-A-004` | axis2fifo.v | AXI-Stream TVALID/TREADY/TDATA handshake |
| `EVID-A-005` | fifo2audpwm.v | 24.576 MHz PWM, 8-bit duty cycle, FIFO empty → aud_en=0 |
| `EVID-A-006` | fifo_generator_0.tcl | independent_clocks, 512 derinlik, 16-bit |
| `EVID-A-007` | design_1.tcl | AXI-Stream bağlantı zinciri (DMA→axis2fifo→FIFO→fifo2audpwm) |
| `EVID-A-008` | project_info.tcl satır 4 | `xc7a50ticsg324-1L` — **KRİTİK: 50T part number** |
| `EVID-A-009` | Nexys-A7-100T-Master.xdc | `PACKAGE_PIN J5` (PWM ses) + `PACKAGE_PIN E3` (100 MHz) |
| `EVID-A-010` | helloworld.c | `XAxiDma_BdRingCreate`, scatter-gather descriptor setup |
| `EVID-A-011` | helloworld.c | `xil_printf()` çağrıları — UART debug |
| `EVID-A-012` | README.md | "tone_generator is not currently working" |
| `EVID-A-dds-calc-001` | Formül kanıtı | DDS INCREMENT = `freq × 2^N / clk_hz` |
| `EVID-A-sim-001` | Testbench tasarımı | fifo2audpwm simülasyon senaryoları |
| `EVID-A-sim-002` | Testbench tasarımı | axis2fifo backpressure test senaryoları |
| `EVID-A-utilization-002` | Kaynak kullanım tahmini | xc7a50t üzerinde LUT/FF tahminleri |

#### PROJECT-B Evidence (5 adet)

| ID | Kaynak | Kanıtlanan |
|----|--------|-----------|
| `EVID-B-001` | SYNTHESIS_RESULTS.md | WNS > 0 ns — Synthesis PASS |
| `EVID-B-002` | simple_top.v | AXI tie-off pattern, standalone GPIO |
| `EVID-B-003` | add_axi_gpio.tcl | GPIO base adres 0x40000000 |
| `EVID-B-ipcat-001` | IP katalog | Xilinx IP versiyonları (Clocking Wizard, GPIO vb.) |
| `EVID-B-util-001` | Kaynak kullanım tahmini | xc7a200t üzerinde LUT/FF tahminleri |

---

### 3.9 SOURCE_DOC Nodes (20 adet)

Knowledge graph'taki kaynak belgelerin referansları.

#### PROJECT-A (9 adet)

| ID | Dosya | Tip | Satır |
|----|-------|-----|-------|
| `SDOC-A-001` | axis2fifo.v | Verilog RTL | 37 |
| `SDOC-A-002` | fifo2audpwm.v | Verilog RTL | 39 |
| `SDOC-A-003` | tone_generator.v | Verilog RTL | 73 |
| `SDOC-A-004` | helloworld.c | C Firmware | 395 |
| `SDOC-A-005` | design_1.tcl | TCL Script | 745 |
| `SDOC-A-006` | Nexys-A7-100T-Master.xdc | XDC Constraint | 212 |
| `SDOC-A-007` | project_info.tcl | TCL Script | — |
| `SDOC-A-008` | README.md (DMA-Audio) | Döküman | — |
| `SDOC-A-009` | pwm_audio_rtl.xml | IP Tanımı | — |

#### PROJECT-B (11 adet)

| ID | Dosya | Tip | Satır |
|----|-------|-----|-------|
| `SDOC-B-001` | axi_gpio_wrapper.v | Verilog RTL | 37 |
| `SDOC-B-002` | simple_top.v | Verilog RTL | 12 |
| `SDOC-B-003` | axi_gpio_bd.bd | Block Design | — |
| `SDOC-B-004` | nexys_video.xdc | XDC Constraint | 30 |
| `SDOC-B-005` | create_axi_simple_gpio.tcl | TCL Script | 132 |
| `SDOC-B-006` | create_minimal_microblaze.tcl | TCL Script | 162 |
| `SDOC-B-007` | add_axi_gpio.tcl | TCL Script | 157 |
| `SDOC-B-008` | run_synthesis.tcl | TCL Script | 82 |
| `SDOC-B-009` | SYNTHESIS_RESULTS.md | Döküman | — |
| `SDOC-B-010` | utilization_summary.txt | Rapor | — |
| `SDOC-B-011` | README.md (axi_example) | Döküman | — |

---

## 4. Knowledge Graph — Edge (İlişki) Kataloğu

### Edge Tipleri ve Anlamları

| Edge Tipi | Sayı | Yön | Anlam |
|-----------|------|-----|-------|
| `VERIFIED_BY` | 155 | Node → Evidence | Her node'un kaynak kanıtı |
| `IMPLEMENTS` | 149 | Component → Requirement | Hangi component hangi isteği karşılıyor |
| `CONSTRAINED_BY` | 102 | Node → Constraint | Teknik kısıt bağlantısı |
| `DECOMPOSES_TO` | 30 | L0→L1, L1→L2 | Gereksinim hiyerarşisi |
| `DEPENDS_ON` | 19 | Component → Component | Bağımlılık ilişkisi |
| `REUSES_PATTERN` | 13 | Component → Pattern | Hangi component hangi deseni kullanıyor |
| `MOTIVATED_BY` | 11 | Decision → Requirement | Kararın arkasındaki gereksinim |
| `ANALOGOUS_TO` | 8 | ProjectA → ProjectB | Çapraz proje benzerlik |
| `INFORMED_BY` | 7 | Node → Project | Bağlam bilgisi |
| `CONTRADICTS` | 1 | MicroBlaze-B → MicroBlaze-A | Versiyon çelişkisi (v11.0 vs v10.0) |

### Çapraz Proje (Cross-Project) Edge'leri

```
PROJECT-B ──────────────────────[INFORMED_BY]──────────────> PROJECT-A
                                 (B projesi A'dan öğrenilmiştir)

COMP-A-clk_wiz_0 ──────────────[ANALOGOUS_TO]──────────────> COMP-B-clk_wiz_0
COMP-A-rst_mig_7series_0_81M ──[ANALOGOUS_TO]──────────────> COMP-B-rst_clk_wiz_0_100M
COMP-A-microblaze_0 ───────────[ANALOGOUS_TO]──────────────> COMP-B-microblaze_0
COMP-A-mdm_1 ──────────────────[ANALOGOUS_TO]──────────────> COMP-B-mdm_1
COMP-A-GPIO_IN ────────────────[ANALOGOUS_TO]──────────────> COMP-B-axi_gpio_0
COMP-A-GPIO_OUT ───────────────[ANALOGOUS_TO]──────────────> COMP-B-axi_gpio_0
COMP-A-axi_interconnect_0 ─────[ANALOGOUS_TO]──────────────> COMP-B-microblaze_0_axi_periph
COMP-A-microblaze_0_axi_periph ─[ANALOGOUS_TO]─────────────> COMP-B-microblaze_0_axi_periph

COMP-B-microblaze_0 ───────────[CONTRADICTS]───────────────> COMP-A-microblaze_0
                                 (MicroBlaze v11.0 vs v10.0 — farklı versiyon)
```

---

## 5. Source Chunk Store

Gerçek kaynak dosyaların ChromaDB'de indekslenmiş halleri. Sorgularda context olarak kullanılır.

### Genel İstatistikler

| Metrik | Değer |
|--------|-------|
| Toplam chunk | **151** |
| Collection adı | `source_chunks` |
| Yol | `db/chroma_source_chunks/` |

### Dosya Tipi Dağılımı

| Tip | Chunk Sayısı | Açıklama |
|-----|-------------|----------|
| `tcl` | 90 (%60) | Vivado TCL scriptleri — IP kurulum, sentez |
| `c` | 29 (%19) | C firmware (helloworld.c, platform.c) |
| `xdc` | 26 (%17) | Pin constraint dosyaları |
| `verilog` | 4 (%3) | RTL modülleri |
| `header` | 2 (%1) | C header dosyaları |

### Dosya Bazında Chunk Dağılımı

| Dosya | Chunk | Proje | Neden Bu Kadar? |
|-------|-------|-------|-----------------|
| `design_1.tcl` | **39** | PROJECT-A | Ana block design — her IP bloğu ayrı chunk |
| `Nexys-A7-100T-Master.xdc` | **25** | PROJECT-A | Her pin grubu ayrı XDC bölümü |
| `helloworld.c` | **23** | PROJECT-A | 395 satır C kodu — fonksiyon bazlı bölme |
| `add_axi_gpio.tcl` | 13 | PROJECT-B | AXI GPIO kurulum adımları |
| `create_axi_with_xdc.tcl` | 10 | PROJECT-B | XDC dahil AXI kurulum |
| `create_minimal_microblaze.tcl` | 9 | PROJECT-B | MicroBlaze minimum kurulum |
| `create_axi_auto.tcl` | 7 | PROJECT-B | BD automation scriptleri |
| `platform.c` | 6 | PROJECT-A | Platform başlangıç kodu |
| `create_axi_simple.tcl` | 6 | PROJECT-B | Basit AXI örneği |
| `create_axi_simple_gpio.tcl` | 4 | PROJECT-B | GPIO'lu AXI örneği |
| Diğer (9 dosya) | 9 | Her iki | Tekil chunk'lar |

### Chunk Bölme Stratejileri

| Dosya Tipi | Bölme Yöntemi | Örnek |
|------------|---------------|-------|
| `.tcl` (block design) | `proc` tanımları + `# Create instance:` IP blokları | Her IP kendi chunk'ı |
| `.xdc` | `##` bölüm başlıkları (`##\s*` regex — boşluksuz da çalışır) | `##Clock Signals` |
| `.c` | `/* --- */` yorum bölümleri | DMA init, WAV oynatma |
| `.v` | `module` tanımları | Tek chunk (küçük dosyalar) |
| `.md` | `##` başlıkları | Bölüm bazlı |

---

## 6. Sorgu Sistemi

### 6.1 Sorgu Tipleri (QueryType)

| Tip | Türkçe Sinyal Kelimeleri | Örnek Soru |
|-----|--------------------------|-----------|
| `WHAT` | ne, nedir, neler, hangi, kaç | "AXI DMA base adresi nedir?" |
| `HOW` | nasıl, nasıl çalışır, bağlantı | "DMA ses akışı nasıl çalışıyor?" |
| `WHY` | neden, niye, gerekçe, karar | "Neden MicroBlaze seçildi?" |
| `TRACE` | takip, iz, yol, akış, zincir | "Ses verisi hangi yolu izliyor?" |
| `CROSSREF` | karşılaştır, fark, benzer, çapraz | "İki projede clock nasıl farklı?" |

### 6.2 Proje Tespiti

Sorgu aşağıdaki öncelik sırasıyla bir projeye yönlendirilir:

```
1. Text Sinyalleri (en yüksek öncelik):
   "nexys video" / "axi_gpio" / "axi gpio" → PROJECT-B
   "nexys a7" / "dma audio" / "axis2fifo"  → PROJECT-A
   "design_1.tcl" / "helloworld"           → PROJECT-A

2. Vector Voting (threshold ≥ 0.70):
   En çok hit alan proje seçilir

3. Varsayılan: PROJECT-A
```

### 6.3 TR→EN Query Augmentation

Türkçe teknik terimler İngilizce karşılıklarıyla zenginleştirilir:

```python
"zamanlama"   → "timing constraint period clock setup hold"
"ddr3"        → "ddr2 mig_7series MIG DDR SDRAM ui_clk"
"icache"      → "C_USE_ICACHE C_USE_DCACHE CONFIG microblaze cache"
"ses"         → "audio pwm fifo2audpwm aud_pwm sample pcm"
"kesme"       → "interrupt irq intc xlconcat"
"bellek"      → "BRAM DDR2 SDRAM MIG LMB memory bram_if_cntlr"
"adres"       → "address base_addr assign_bd_address offset"
...
```

### 6.4 4-Store Federated Query Akışı

```
Soru → [QueryRouter]
         ├── [GraphStore]     : Node + edge sorgusu (NetworkX)
         ├── [VectorStoreV2]  : Semantik benzerlik (ChromaDB, all-MiniLM-L6-v2)
         ├── [SourceChunkStore]: Gerçek kaynak kod chunk'ları (ChromaDB)
         └── [RequirementTree]: Gereksinim hiyerarşisi traversal
              ↓
         [QueryResult] → all_nodes() birleşik sonuç
```

---

## 7. Anti-Hallüsinasyon Katmanları

Tüm sorgularda 6 katman sırayla çalışır:

```
Layer 5 (Stale Filter)   → SUPERSEDES edge'li eski node'ları filtrele
Layer 1 (Evidence Gate)  → REQ/DEC/COMP için EVIDENCE bağlantısı zorunlu
Layer 2 (Confidence Prop)→ Zincirdeki en düşük confidence = toplam
Layer 3 (Coverage Gap)   → IMPLEMENTS edge'siz REQUIREMENT'ları işaretle
Layer 4 (ParseUncertain) → PARSE_UNCERTAIN node'ları için uyarı üret
Layer 6 (Contradicts)    → CONTRADICTS edge'li DECISION çiftlerini uyar
                           (COMPONENT-COMPONENT atlanır — yanlış pozitif önlemi)
```

**Mevcut durum:** 31 gereksinimin tamamı implement edilmiş → Coverage Gap = 0

---

## 8. LLM Sistem Promptu — 11 Kural

LLM'e her sorguda verilen sabit kurallar (`FPGA_RAG_SYSTEM_PROMPT`):

| # | Kural | Kategori |
|---|-------|---------|
| 1 | Sadece verilen context'i kullan, asla tahmin üretme | Temel |
| 2 | KAYNAK DOSYA bölümündeki değerleri doğrudan kullan | Kaynak |
| 3 | Graph metadata + kaynak dosyaları birleştir | Entegrasyon |
| 4 | Her iddia için kaynak belirt (node_id veya dosya:satır) | İzlenebilirlik |
| 5 | PARSE_UNCERTAIN bilgileri "belirsiz" olarak işaretle | Güven |
| 6 | Coverage Gap varsa "bulunamadı" de; ama kaynak dosyada varsa kullan | Coverage |
| 7 | CONTRADICTS uyarısı varsa her iki görüşü de sun | Çelişki |
| 8 | Yanıtı Türkçe ver, teknik terimler orijinal haliyle | Dil |
| 9 | **KRİTİK:** Proje listesi sorularında sadece PROJECT node'ları listele | Proje |
| 10 | **KRİTİK:** RTL parametresi context'te literal yoksa uydurma | RTL |
| 11 | **KRİTİK:** Bilinmeyen arayüz/özellik için "projede yok" de | Arayüz |

---

## 9. Yazılım Modülleri

### `src/rag_v2/` — Çekirdek Modüller

| Modül | Satır | Görev |
|-------|-------|-------|
| `query_router.py` | ~800 | Sorgu sınıflandırma, proje tespiti, 4-store yönlendirme |
| `hallucination_gate.py` | ~350 | 6-layer anti-hallüsinasyon filtresi |
| `response_builder.py` | ~290 | LLM context paketi + sistem promptu |
| `graph_store.py` | ~400 | NetworkX graph CRUD, komşu sorgu, stale tespit |
| `vector_store_v2.py` | ~200 | ChromaDB node embedding, benzerlik arama |
| `source_chunk_store.py` | ~300 | Kaynak dosya indeksleme + chunk arama |
| `grounding_checker.py` | ~150 | LLM yanıt doğrulama (context cross-check) |
| `matching_engine.py` | ~200 | Graph semantik eşleştirme, benzerlik skoru |
| `cross_reference_detector.py` | ~400 | M1-M4 otomatik proje arası ilişki tespiti |
| `loader.py` | ~150 | `pipeline_graph.json` → GraphStore yükleyici |

### `src/rag/` — LLM Adaptörleri

| Modül | LLM | Model |
|-------|-----|-------|
| `claude_generator.py` | Anthropic Claude | claude-sonnet-4-6 (varsayılan) |
| `openai_generator.py` | OpenAI | gpt-4o-mini (fallback) |
| `gemini_generator.py` | Google Gemini | gemini-1.5-flash |

### `scripts/` — Yönetim ve Test Araçları

| Script | Görev |
|--------|-------|
| `test_v2_20q.py` | 20 soruluk benchmark testi |
| `test_robustness.py` | 5-kategori adversarial robustness testi |
| `index_source_files.py` | Kaynak dosyaları SourceChunkStore'a indeksler |
| `build_graph_db.py` | pipeline_graph.json → GraphStore + VectorStore |
| `add_new_knowledge_nodes.py` | Yeni node ekleme scripti |
| `fix_graph_db.py` | Node patch + IMPLEMENTS edge düzeltme |
| `fix_architecture_gaps.py` | SOURCE_DOC node + VERIFIED_BY edge ekleme |
| `run_cross_reference.py` | CrossReferenceDetector çalıştır |
| `run_matching.py` | MatchingEngine çalıştır |
| `show_stats.py` | Graph istatistikleri |
| `chat.py` | Terminal chat arayüzü |
| `query_v2.py` | Tek sorgu CLI |
| `scenarios_v2.py` | Örnek senaryo testleri |

---

## 10. Test Sistemi

### 10.1 20 Soru Benchmark — Son Sonuçlar (0.796/A)

| Proje | Skor | Not |
|-------|------|-----|
| axi_gpio_example (A-Q01..10) | 0.815/A | 10 soru |
| nexys_a7_dma_audio (B-Q01..10) | 0.776/B | 10 soru |
| **GENEL** | **0.796/A** | GPT-4o-mini ile |

### 10.2 Robustness Test Suite — Son Sonuçlar (0.839/A)

| Test | Ağırlık | Skor | Not |
|------|---------|------|-----|
| A — Held-Out Dosya (design_1.tcl) | %25 | **1.000/A** |
| B — Fabrication/Recall (4 tuzak + 4 gerçek) | %30 | **0.758/B** |
| C — Multi-Hop Graph Traversal (2-3 hop) | %20 | **0.778/B** |
| D — Cross-Project Reasoning | %15 | **0.706/B** |
| E — Contradiction Detection | %10 | **1.000/A** |
| **AĞIRLIKLI TOPLAM** | | **0.839/A** | |

---

## 11. Dosya ve Dizin Yapısı

```
GC-RAG-VIVADO-2/
│
├── app_v2.py                        # Streamlit web arayüzü (ana giriş)
├── .env                             # API anahtarları (Anthropic, OpenAI, Google)
├── PROJE_YAPISI.md                  # Bu döküman
├── PROJECT_DOCUMENTATION.md         # Teknik mimari dökümanı
├── evaluation_v2_20q.json           # Son 20q test sonuçları
├── robustness_report.json           # Son robustness test sonuçları
│
├── src/
│   ├── rag_v2/                      # RAG v2 çekirdek modülleri
│   │   ├── query_router.py          ← ANA MODÜL — sorgu motoru
│   │   ├── hallucination_gate.py    ← 6-katman anti-hallüsinasyon
│   │   ├── response_builder.py      ← LLM context + sistem promptu
│   │   ├── graph_store.py           ← NetworkX knowledge graph
│   │   ├── vector_store_v2.py       ← ChromaDB vektör arama
│   │   ├── source_chunk_store.py    ← Kaynak dosya chunk indeksi
│   │   ├── grounding_checker.py     ← LLM yanıt doğrulama
│   │   ├── matching_engine.py       ← Semantik eşleştirme
│   │   ├── cross_reference_detector.py ← Proje arası ilişki M1-M4
│   │   ├── loader.py                ← pipeline_graph.json yükleyici
│   │   └── __init__.py
│   └── rag/                         # LLM adaptörleri
│       ├── claude_generator.py      ← Anthropic Claude API
│       ├── openai_generator.py      ← OpenAI API (fallback)
│       └── gemini_generator.py      ← Google Gemini API
│
├── scripts/
│   ├── test_v2_20q.py               ← 20 soru benchmark
│   ├── test_robustness.py           ← Adversarial robustness testi
│   ├── index_source_files.py        ← Kaynak dosya indeksleme
│   ├── build_graph_db.py            ← Graph + Vector DB oluşturma
│   ├── add_new_knowledge_nodes.py   ← Node ekleme
│   ├── fix_graph_db.py              ← Node/edge düzeltme
│   ├── fix_architecture_gaps.py     ← Mimari boşluk kapatma
│   ├── run_cross_reference.py       ← CrossRef çalıştırma
│   ├── run_matching.py              ← Matching çalıştırma
│   ├── show_stats.py                ← İstatistik görüntüleme
│   ├── chat.py                      ← Terminal chat
│   ├── query_v2.py                  ← Tek sorgu CLI
│   └── scenarios_v2.py              ← Senaryo testleri
│
├── db/
│   ├── graph/
│   │   └── fpga_rag_v2_graph.json   # Knowledge graph (155 node, 495 edge)
│   ├── chroma_graph_nodes/          # Node embedding DB (collection: fpga_rag_v2_nodes)
│   └── chroma_source_chunks/        # Kaynak chunk DB (collection: source_chunks, 151 chunk)
│
└── .venv/                           # Python sanal ortamı (activate önce!)
```

---

*Döküman tarihi: 2026-02-25 | Son skor: Robustness 0.839/A · 20q 0.796/A*
