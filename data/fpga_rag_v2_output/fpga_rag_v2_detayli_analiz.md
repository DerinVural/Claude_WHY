# FPGA RAG v2 — Detaylı Analiz Dokümanı

**Versiyon:** 2.1
**Tarih:** 2026-02-23
**Pipeline Versiyonu:** 2.0 (6 Faz Tamamlandı)
**Kaynak Dosya:** `pipeline_graph.json` (119 KB, 2255 satır)
**Mimari Ref:** `fpga_rag_architecture_v2.md`
**ISTER Ref:** `FPGA_RAG_ISTER_DOKUMANI_v2.txt` (v2.1)

---

## İÇİNDEKİLER

1. [Proje Genel Bakış](#1-proje-genel-bakış)
2. [Faz 1 — Dosya Manifestosu](#2-faz-1--dosya-manifestosu)
3. [Faz 2 — Bileşen (COMPONENT) Node'ları](#3-faz-2--bileşen-component-nodları)
   - 3.1 PROJECT-A RTL Modülleri
   - 3.2 PROJECT-A IP Core'ları
   - 3.3 PROJECT-A Yazılım Bileşenleri
   - 3.4 PROJECT-B RTL Modülleri
   - 3.5 PROJECT-B IP Core'ları
4. [Faz 2 — CONSTRAINT Node'ları](#4-faz-2--constraint-nodları)
5. [Faz 2 — EVIDENCE Node'ları](#5-faz-2--evidence-nodları)
6. [Faz 2 — ISSUE Node'ları](#6-faz-2--issue-nodları)
7. [Faz 2 — PATTERN Node'ları](#7-faz-2--pattern-nodları)
8. [Faz 3 — Gereksinim Ağacı (REQUIREMENT)](#8-faz-3--gereksinim-ağacı-requirement)
   - 8.1 PROJECT-A Gereksinimleri
   - 8.2 PROJECT-B Gereksinimleri
9. [Faz 3 — DECISION Kayıtları](#9-faz-3--decision-kayıtları)
10. [Faz 4 — Eşleştirme Kenarları (IMPLEMENTS / VERIFIED_BY)](#10-faz-4--eşleştirme-kenarları)
11. [Faz 5 — Özel Analizler (SA-001 … SA-005)](#11-faz-5--özel-analizler)
12. [Faz 5 — Coverage Gap Raporu](#12-faz-5--coverage-gap-raporu)
13. [Faz 5 — Orphan Component Raporu](#13-faz-5--orphan-component-raporu)
14. [Faz 5 — Çapraz Proje Kenarları](#14-faz-5--çapraz-proje-kenarları)
15. [Faz 6 — ISTER Dokümanı Güncellemeleri](#15-faz-6--ister-dokümanı-güncellemeleri)
16. [Özet Sayısal Tablo](#16-özet-sayısal-tablo)

---

## 1. Proje Genel Bakış

### PROJECT-A: Nexys-A7-100T-DMA-Audio

```
Kart       : Digilent Nexys A7-100T
FPGA       : xc7a100tcsg324-1 (İSTENEN) ⚠️ TCL: xc7a50ticsg324-1L (GERÇEK — KRİTİK ÇATIŞMA)
Araç       : Vivado 2018.2 + Xilinx SDK
Dil        : Verilog (RTL) + C (SDK)
Tip        : Uygulama (DMA ses akışı demo)
Kök İster  : DMA-REQ-L0-001
Issue      : ISSUE-A-001 (critical)
```

**Sistem Mimarisi (Blok Düzeyi):**
```
[DDR2 128 MB]
     │ ui_clk (~81 MHz)
     ▼
[MIG 7-Series] ←→ [AXI Interconnect (4M:1S)] ←→ [AXI DMA 7.1]
                                                        │
                         ┌──────────────────────────────┤
                         │ MM2S (Memory→Stream)         │ S2MM (Stream→Memory)
                         ▼                              ▼
                   [axis2fifo]              [tone_generator] ← (BOZUK)
                         │
                  [FIFO Gen. 13.2] ← CDC (81→24.576 MHz)
                         │
                   [fifo2audpwm]
                         │
                   [PWM Audio Bus] → SSM2377 Amplifier → Hoparlör

[MicroBlaze v10.0] ─── I+D Cache ─── [LMB BRAM 64KB]
     │
     ├── [AXI GPIO IN]  ← Butonlar (5) + Switch (16)
     ├── [AXI GPIO OUT] → LED'ler
     ├── [AXI UARTLite] ↔ Serial Console (230400 baud)
     ├── [AXI DMA]      ← DMA kontrolü
     └── [AXI INTC]     ← xlconcat_0 (DMA) + xlconcat_1 (GPIO+UART)

[MDM v3.2] ← JTAG Debug
[Clk Wiz v6.0]: 100 MHz → 140.625 MHz (MIG) + 24.576 MHz (Audio)
```

### PROJECT-B: axi_example

```
Kart       : Digilent Nexys Video
FPGA       : xc7a200tsbg484-1 ✅ (TCL ile uyumlu)
Araç       : Vivado 2025.1
Dil        : Verilog (RTL)
Tip        : Eğitim / Validasyon
Kök İster  : AXI-REQ-L0-001
```

**3-Seviyeli Eğitim Yapısı:**
```
Seviye 1 ─ Standalone GPIO Wrapper
  └── axi_gpio_wrapper.v: AXI sinyallerini elle tie-off
      Öğrenim: AXI sinyal semantiği (tvalid/tready/tlast)

Seviye 2 ─ Minimal MicroBlaze + AXI GPIO (✅ TAMAMLANDI)
  └── microblaze_0 → AXI Interconnect → axi_gpio_0
      Sentez: 1412 LUT, 1285 FF, WNS > 0 ns

Seviye 3 ─ Tam Sistem: MicroBlaze + AXI BRAM + GPIO (⏳ GELİŞTİRİLİYOR)
  └── Block Automation timeout sorunu (5+ dakika stuck)
```

---

## 2. Faz 1 — Dosya Manifestosu

### PROJECT-A Kaynak Dosyaları

| Doc ID | Dosya | Tip | Satır | Açıklama |
|--------|-------|-----|-------|----------|
| SDOC-A-001 | `src/hdl/axis2fifo.v` | HDL (Verilog) | 37 | AXI-Stream → FIFO köprüsü |
| SDOC-A-002 | `src/hdl/fifo2audpwm.v` | HDL (Verilog) | 39 | FIFO → PWM ses çıkışı |
| SDOC-A-003 | `src/hdl/tone_generator.v` | HDL (Verilog) | 73 | Phase acc. ton üreteci (BOZUK) |
| SDOC-A-004 | `sdk/appsrc/helloworld.c` | SW (C) | 395 | MicroBlaze SDK uygulaması |
| SDOC-A-005 | `src/bd/design_1.tcl` | TCL Script | 745 | Vivado BD yeniden oluşturma |
| SDOC-A-006 | `src/constraints/Nexys-A7-100T-Master.xdc` | XDC | 212 | Pin + timing kısıtları |
| SDOC-A-007 | `project_info.tcl` | TCL Script | — | Proje konfigürasyonu (part tanımı) |
| SDOC-A-008 | `README.md` | Dokümantasyon | — | Bilinen sorunlar, kullanım |
| SDOC-A-009 | `repo/local/if/pwm_audio/pwm_audio_rtl.xml` | IP Tanımı | — | Custom PWM Audio bus |

**Gerçek Yol (Linux):** `/home/test123/GC-RAG-VIVADO-2/data/code/Nexys-A7-100T-DMA-Audio/`

### PROJECT-B Kaynak Dosyaları

| Doc ID | Dosya | Tip | Satır | Açıklama |
|--------|-------|-----|-------|----------|
| SDOC-B-001 | `vivado_axi_simple/axi_gpio_wrapper.v` | HDL (Verilog) | 37 | Standalone AXI GPIO wrapper |
| SDOC-B-002 | `simple_working/.../simple_top.v` | HDL (Verilog) | 12 | 4-bit counter (toolchain test) |
| SDOC-B-003 | `axi_example_build/.../axi_gpio_bd.bd` | Block Design | — | MicroBlaze + GPIO BD |
| SDOC-B-004 | `vivado_axi_simple/nexys_video.xdc` | XDC | 30 | Nexys Video pin kısıtları |
| SDOC-B-005 | `create_axi_simple_gpio.tcl` | TCL Script | 132 | Seviye 1 proje oluşturma |
| SDOC-B-006 | `create_minimal_microblaze.tcl` | TCL Script | 162 | Seviye 2 minimal MicroBlaze |
| SDOC-B-007 | `add_axi_gpio.tcl` | TCL Script | 157 | Mevcut BD'ye GPIO ekleme |
| SDOC-B-008 | `run_synthesis.tcl` | TCL Script | 82 | Sentez çalıştırma + rapor |
| SDOC-B-009 | `SYNTHESIS_RESULTS.md` | Dokümantasyon | — | Sentez sonuçları |
| SDOC-B-010 | `utilization_summary.txt` | Rapor | — | Vivado v2025.1 resmi kullanım raporu |
| SDOC-B-011 | `README.md` | Dokümantasyon | — | Proje dokümantasyonu |

**Gerçek Yol (Linux):** `/home/test123/Desktop/fpga_asist_dev-master/fpga_asist_dev-master/validation_test/axi_example/`

---

## 3. Faz 2 — Bileşen (COMPONENT) Node'ları

### 3.1 PROJECT-A RTL Modülleri

#### COMP-A-axis2fifo_0 — AXI-Stream → FIFO Köprüsü

```
Dosya          : src/hdl/axis2fifo.v (37 satır)
Clock Domain   : MIG ui_clk (~81 MHz)
Güven          : HIGH

Portlar:
  Giriş  : clk, axis_tdata[31:0], axis_tkeep[0], axis_tlast, axis_tvalid, fifo_full
  Çıkış  : axis_tready, fifo_wr_data[15:0], fifo_wr_en

Temel Mantık (Verilog):
  assign axis_tready = ~fifo_full;              // Satır 33 — geri baskı (backpressure)
  assign fifo_wr_en = axis_tready & axis_tvalid; // Satır 34 — AXI-S handshake
  assign fifo_wr_data = axis_tdata[15:0];        // Satır 35 — 32→16 bit truncation ⚠️

Notlar:
  ⚠️ 32-bit AXI-Stream'den sadece alt 16-bit alınıyor, üst 16-bit atılıyor.
  ✅ Backpressure doğru uygulanmış: FIFO dolunca DMA durdurulur.
  Bağlı İssue: ISSUE-A-003 (medium — truncation ses kalitesi etkisi)
```

#### COMP-A-fifo2audpwm_0 — FIFO → PWM Ses Çıkışı

```
Dosya          : src/hdl/fifo2audpwm.v (39 satır)
Clock Domain   : clk_wiz_0 Clk_Out2 (24.576 MHz)
Güven          : HIGH

Portlar:
  Giriş  : clk, fifo_rd_data[31:0], fifo_empty
  Çıkış  : aud_pwm, aud_en, fifo_rd_en

Parametreler:
  DATA_WIDTH      = 8   (8-bit ses örnekleri)
  FIFO_DATA_WIDTH = 32  (32-bit FIFO kelimesi başına 4 örnek)

Temel Mantık:
  // 256-level PWM karşılaştırıcı (satır 37):
  assign aud_pwm = count[DATA_WIDTH-1:0] <= duty[count[DATA_WIDTH+1:DATA_WIDTH]];

  // Akış kontrolü (satırlar 23-26):
  aud_en <= (fifo_empty == 0) ? 1'b1 : 1'b0;

  // Ses paketi düzeni (satırlar 29-32):
  duty[0] = fifo_rd_data[7:0]   // 1. örnek
  duty[1] = fifo_rd_data[15:8]  // 2. örnek
  duty[2] = fifo_rd_data[23:16] // 3. örnek
  duty[3] = fifo_rd_data[31:24] // 4. örnek

PWM Hesabı:
  f_pwm = 24.576 MHz / 256 = 96 kHz örnekleme hızı ✅
  8-bit çözünürlük → ~48 dB dinamik aralık
```

#### COMP-A-tone_generator_0 — Donanım Ton Üreteci (BOZUK)

```
Dosya          : src/hdl/tone_generator.v (73 satır)
Clock Domain   : MIG ui_clk (~81 MHz)
Güven          : HIGH
Parse Flag     : PARSE_UNCERTAIN_WHY_DISABLED

Portlar:
  Giriş  : clk, axis_tready
  Çıkış  : axis_tdata[31:0], axis_tvalid, axis_tlast, axis_tkeep[3:0]

Parametreler:
  INCREMENT        = 0x00B22D0E (261 Hz @ 96 kHz örnekleme → Orta C)
  TONE_FREQ        = 261 Hz
  AUD_SAMPLE_FREQ  = 96000 Hz
  PACKET_SIZE      = 256 örnek
  ACCUMULATOR_DEPTH= 32-bit

Phase Accumulator Algoritması:
  // Satır 49-58:
  always @(posedge clk) begin
    if (axis_tready)
      duty <= duty + INCREMENT;   // faz biriktiricisi artırımı
  end
  assign axis_tdata = {16'b0, duty[31:16]};  // 16-bit çıkış

KRİTİK BUG:
  assign axis_tvalid = 1;       // Satır 52 — her zaman geçerli (normal)
  assign axis_tlast  = 1'b1;   // Satır 69 — ⚠️ SABİT 1 → Her cycle TLAST!
                                // DMA her transfer'ı 1-beat paket görür
                                // Beklenen: axis_tlast = (packet_cnt == PACKET_SIZE-1)

TODO Comment:
  // Satır 72: "create AXI interface for configuration of INCREMENT and PACKET_SIZE params"
  // Bu interface hiç oluşturulmamış.

Neden Çalışmıyor:
  1) axis_tlast bug'ı → DMA paketi yanlış sınırlar
  2) 16-bit çıkış, 8-bit bekleyen fifo2audpwm ile uyumsuz
  3) SW'de DEMO_MODE_HW_TONE_GEN case sadece break yapıyor (helloworld.c:386)

PARSE_UNCERTAIN: Neden düzeltilmediği mühendis tarafından belgelenmemiş.
```

---

### 3.2 PROJECT-A IP Core'ları

#### COMP-A-axi_dma_0 — AXI DMA v7.1

```
VLNV         : xilinx.com:ip:axi_dma:7.1
Clock Domain : MIG ui_clk (~81 MHz)
Güven        : HIGH

Parametreler:
  c_include_sg             = 0    (Scatter-Gather devre dışı)
  c_sg_include_stscntrl_strm = 0
  burst_size               = 256  (256-byte DMA burst)
  addr_width               = 27   (27-bit adres genişliği)

Bağlantılar:
  M_AXIS_MM2S  → axis2fifo_0    (Bellek→Ses FIFO akışı)
  S_AXIS_S2MM  → tone_generator_0 (Ton Üreteci→Bellek)
  M_AXI_MM2S   → axi_interconnect_0
  M_AXI_S2MM   → axi_interconnect_0
  mm2s_introut → xlconcat_0/In0 (DMA interrupt)
  s2mm_introut → xlconcat_0/In1 (DMA interrupt)

Not: Simple DMA modu (SG=0). helloworld.c init_dma() fonksiyonu açıkça SG modunu
reddediyor (satır 50).
```

#### COMP-A-mig_7series_0 — DDR2 Bellek Arayüzü

```
VLNV     : xilinx.com:ip:mig_7series:4.1
Güven    : HIGH

Parametreler:
  memory_type  = DDR2
  base_address = 0x80000000
  size_MB      = 128 MB

Temel Çıkışlar:
  ui_clk       (~81 MHz) → MicroBlaze ve AXI fabric clock'u
  ui_clk_sync_rst        → rst_mig_7series_0_81M'e reset girişi
  mmcm_locked            → rst_mig_7series_0_81M'e DCM lock sinyali
  init_calib_complete    → DDR2 kalibrasyon tamamlanma sinyali

Not: MIG'in ui_clk frekansı, DDR2 konfigürasyonuna göre ~81 MHz'de
stabilize olur. Bu, MicroBlaze ve tüm AXI bileşenlerinin clock'udur.
```

#### COMP-A-clk_wiz_0 — Saat Üreteci

```
VLNV     : xilinx.com:ip:clk_wiz:6.0
Güven    : HIGH

Girişler:
  clk_in1  = 100 MHz (E3, LVCMOS33) — Nexys A7 osilatörü

Çıkışlar:
  clk_out1 = 140.625 MHz → mig_7series_0/sys_clk_i
             (DDR2 PHY reference clock — 140.625 × 7/5 = 196.875 MHz DDR data rate)
  clk_out2 = 24.576 MHz  → fifo2audpwm_0/clk + fifo_generator_0/rd_clk
             (96 kHz × 256 = 24.576 MHz — ses clock'u)
```

#### COMP-A-rst_mig_7series_0_81M — Reset Kontrolcüsü

```
VLNV     : xilinx.com:ip:proc_sys_reset:5.0
Güven    : HIGH

Bağlantılar:
  slowest_sync_clk   ← MIG ui_clk (~81 MHz)
  ext_reset_in       ← mig_7series_0/ui_clk_sync_rst  (DDR2 senkron reset)
  dcm_locked         ← mig_7series_0/mmcm_locked        (MMCM kilitleme sinyali)
  peripheral_aresetn → Tüm AXI çevresel birimlere (active-low reset)
  interconnect_aresetn → AXI Interconnect'lere

Reset Zinciri:
  DDR2 init_calib_complete → ui_clk_sync_rst deassert → proc_sys_reset
  → peripheral_aresetn tüm sisteme yayılır

Not: DDR2 kalibrasyonu tamamlanmadan sistem reset'ten çıkmaz.
```

#### COMP-A-fifo_generator_0 — Çift-Clock FIFO

```
VLNV     : xilinx.com:ip:fifo_generator:13.2
Güven    : HIGH

Parametreler:
  mode       = independent_clocks  (çift-clock — CDC için)
  FIFO_DEPTH = 4096
  DATA_WIDTH = 32

Bağlantılar:
  wr_clk ← MIG ui_clk (~81 MHz)       — yazma tarafı
  rd_clk ← clk_wiz_0 Clk_Out2 (24.576 MHz) — okuma tarafı
  din    ← axis2fifo_0/fifo_wr_data
  dout   → fifo2audpwm_0/fifo_rd_data
  full   → axis2fifo_0/fifo_full       (backpressure sinyali)
  empty  → fifo2audpwm_0/fifo_empty    (akış kontrolü)

CDC Notu: Gray-code pointer senkronizasyonu Xilinx IP tarafından otomatik
uygulanır. 81 MHz → 24.576 MHz geçişi güvenli.
```

#### COMP-A-microblaze_0 — MicroBlaze İşlemci

```
VLNV     : xilinx.com:ip:microblaze:10.0
Güven    : HIGH

Parametreler:
  C_USE_ICACHE = 1 (Instruction Cache etkin)
  C_USE_DCACHE = 1 (Data Cache etkin — DDR2 performansı için gerekli)

Bellek Mimarisi:
  LMB BRAM (64 KB) — boot kodu ve stack
  DDR2 (128 MB)    — WAV verisi tamponu, uygulama heap
```

#### COMP-A-microblaze_0_axi_intc — Interrupt Kontrolcüsü

```
VLNV           : xilinx.com:ip:axi_intc:4.1
Base Address   : 0x41200000
Güven          : HIGH

Durum: Donanımda kurulu ama yazılım polling kullanıyor.
Interrupt Kaynakları:
  xlconcat_0/dout → INTC → MicroBlaze INTERRUPT
    - In0: axi_dma_0/mm2s_introut (MM2S DMA tamamlandı)
    - In1: axi_dma_0/s2mm_introut (S2MM DMA tamamlandı)
  xlconcat_1/dout → INTC → MicroBlaze INTERRUPT
    - In0: GPIO_IN/ip2intc_irpt   (GPIO buton baskısı)
    - In1: GPIO_OUT/ip2intc_irpt  (GPIO çıkış)
    - In2: axi_uartlite_0/interrupt (UART RX)

Sınıflandırma: DECISION (DMA-DEC-005) — Coverage Gap değil.
```

#### COMP-A-GPIO_IN — AXI GPIO Giriş

```
VLNV         : xilinx.com:ip:axi_gpio:2.0
Base Address : 0x40000000
Güven        : HIGH

Parametreler:
  C_GPIO_WIDTH  = 5  (kanal 1: 5 buton)
  C_GPIO2_WIDTH = 16 (kanal 2: 16 switch)
  C_IS_DUAL     = 1  (çift kanal)

Bağlantılar:
  CH1 giriş ← 5 adet pushbutton
  CH2 giriş ← 16 adet DIP switch
  ip2intc_irpt → xlconcat_1/In0
```

#### COMP-A-GPIO_OUT — AXI GPIO Çıkış

```
VLNV         : xilinx.com:ip:axi_gpio:2.0
Base Address : 0x40010000
Güven        : HIGH

Parametreler:
  C_ALL_OUTPUTS = 1
  C_IS_DUAL     = 1

Bağlantılar:
  CH1 çıkış → RGB LED'ler
  CH2 çıkış → 16 adet LED
  ip2intc_irpt → xlconcat_1/In1
```

#### COMP-A-axi_uartlite_0 — UART

```
VLNV       : xilinx.com:ip:axi_uartlite:2.0
Baud Rate  : 230400 (8N1)
Base Addr  : 0x40600000
Güven      : HIGH

Kullanım: WAV dosyası UART üzerinden alınır (recv_wav fonksiyonu).
```

#### COMP-A-mdm_1 — MicroBlaze Debug Modülü

```
VLNV       : xilinx.com:ip:mdm:3.2
Güven      : HIGH

Parametreler:
  C_MB_DBG_PORTS = 1

Kullanım: JTAG üzerinden MicroBlaze software debug.
```

#### COMP-A AXI Interconnect'ler

```
axi_interconnect_0 (Bellek Yolu):
  NUM_SI = 4, NUM_MI = 1
  Masterlar: DMA MM2S, DMA S2MM, MB Data Cache, MB Inst Cache
  Slave   : MIG 7-Series DDR2

microblaze_0_axi_periph (Çevresel Yol):
  NUM_SI = 1, NUM_MI = 5
  Master : MicroBlaze M_AXI_DP
  Slavlar: GPIO_IN, GPIO_OUT, UARTLite, AXI DMA, INTC
```

#### COMP-A-lmb_bram — LMB Bellek Altsistemi

```
VLNV   : xilinx.com:ip:lmb_bram_if_cntlr:4.0
Boyut  : 64 KB
Güven  : HIGH

Bileşenler: lmb_bram_if_cntlr (x2) + lmb_v10 (x2) + blk_mem_gen
Kullanım: MicroBlaze instruction + data LMB belleği (boot kodu + stack)
```

#### COMP-A-pwm_audio_bus — Custom Bus Interface

```
Dosya   : repo/local/if/pwm_audio/pwm_audio_rtl.xml
Tip     : Custom_Interface
Güven   : HIGH

Portlar : pwm (out), en (out), gain (out)
Hedef   : SSM2377 ses amplifikatörü
Aktif XDC Pin'leri:
  PWM_AUDIO_0_pwm → A11 (LVCMOS33) ✅
  PWM_AUDIO_0_en  → D12 (LVCMOS33) ✅
```

---

### 3.3 PROJECT-A Yazılım Bileşenleri

#### COMP-A-helloworld — SDK Uygulaması

```
Dosya    : sdk/appsrc/helloworld.c (395 satır, Dil: C)
Güven    : HIGH

Ana Fonksiyonlar:
  main()              — Demo mod durum makinesi (state machine)
  dma_sw_tone_gen()   — Yazılım 261 Hz ton üretimi (satırlar 353-380)
                        Phase acc. HW ile aynı algoritma ama SW'de
  recv_wav()          — UART üzerinden WAV dosyası alma + DDR2 yazma
  play_wav()          — DMA MM2S ile WAV çalma
  init_dma()          — DMA başlatma (satır 50: Scatter-Gather açıkça reddedilmiş)

Demo Modları:
  DEMO_MODE_SW_TONE_GEN  → Yazılım ton üreteci (ÇALIŞIYOR)
  DEMO_MODE_HW_TONE_GEN  → HW ton üreteci (DEVRE DIŞI — sadece break)
  DEMO_MODE_RECV_WAV     → WAV al (UART'tan)
  DEMO_MODE_PLAY_WAV     → WAV çal (DDR2'den DMA ile)

Veri Dönüşümü (satır 287):
  (u8)((u16)(wav_data[i]+32768)>>8)
  → 16-bit signed WAV → 8-bit unsigned PWM duty cycle
  → +32768 ile offset → sağa kaydır → 0-255 aralığına dönüştür

Interrupt: Kullanılmıyor (polling tabanlı while(1) döngüsü)
```

---

### 3.4 PROJECT-B RTL Modülleri

#### COMP-B-axi_gpio_wrapper — Standalone AXI GPIO Wrapper

```
Dosya          : vivado_axi_simple/axi_gpio_wrapper.v (37 satır)
Güven          : HIGH
Eğitim Değeri : ÇOK YÜKSEK

Portlar:
  Giriş  : clk, resetn, switches[7:0]
  Çıkış  : leds[7:0]

AXI Tie-Off Mantığı (satırlar 13-31):
  // AXI Write channel — hiçbir yazma isteği gönderilmiyor:
  s_axi_awvalid(1'b0),   // Adres geçerli değil
  s_axi_wvalid (1'b0),   // Veri geçerli değil
  s_axi_arvalid(1'b0),   // Okuma adresi geçerli değil

  // AXI Response — her zaman hazır:
  s_axi_bready (1'b1),   // Yazma yanıtını her zaman kabul et
  s_axi_rready (1'b1),   // Okuma yanıtını her zaman kabul et

  // GPIO:
  gpio_io_i(switches),   // Switch'ler GPIO'ya bağlı
  gpio_io_o(leds)        // LED'ler GPIO çıkışından

Eğitimsel Amaç:
  AXI4-Lite sinyallerini signal-level anlama.
  Bu pattern, MicroBlaze olmadan GPIO IP'yi çalıştırabilir.
```

#### COMP-B-simple_top — Toolchain Doğrulama

```
Dosya  : simple_working/.../simple_top.v (12 satır)
Güven  : HIGH

Portlar:
  Giriş  : clk, reset
  Çıkış  : led[3:0]

Mantık: 4-bit senkron sayaç (reset active-high)
Amaç : Vivado toolchain'in çalışıp çalışmadığını doğrulama.
```

---

### 3.5 PROJECT-B IP Core'ları

#### COMP-B-microblaze_0 — MicroBlaze v11.0

```
VLNV              : xilinx.com:ip:microblaze:11.0
Güven             : HIGH
Sentez Doğrulandı : Evet (utilization_summary.txt)

Parametreler:
  C_USE_ICACHE = 0 (cache yok — 8KB BRAM yeterli)
  C_USE_DCACHE = 0
  C_D_AXI      = 1 (AXI Data Bus etkin)
  debug_enabled= true (MDM bağlantısı için)

Fark (PROJECT-A ile karşılaştırma):
  PROJECT-A v10.0 I+D cache var (DDR2 erişim performansı için)
  PROJECT-B v11.0 cache yok (8KB BRAM'ı verimli kullanıyor)
```

#### COMP-B-axi_gpio_0 — AXI GPIO

```
VLNV              : xilinx.com:ip:axi_gpio:2.0
Base Address      : 0x40000000
Güven             : HIGH
Sentez Doğrulandı : Evet

Parametreler:
  C_GPIO_WIDTH  = 8
  C_ALL_OUTPUTS = 1

Bağlantılar:
  gpio_io_o → LED[7:0] (T14-Y13 pinleri, LVCMOS25)
Sentez kanıtı: utilization_summary.txt — microblaze_bd_axi_gpio_0_0 instance
```

#### COMP-B-clk_wiz_0 — Saat Üreteci

```
VLNV              : xilinx.com:ip:clk_wiz:6.0
Güven             : HIGH
Sentez Doğrulandı : Evet

Parametreler:
  CLKOUT1_FREQ_HZ = 100.000.000 (100 MHz)
  CLKIN_FREQ_HZ   = 100.000.000 (Nexys Video osilatörü)

Sentez Primitifleri (utilization_summary.txt):
  1 × MMCME2_ADV
  3 × BUFGCTRL

Fark (PROJECT-A ile): Tek çıkış (100 MHz), PROJECT-A'da 2 çıkış (140.625 + 24.576 MHz)
```

#### COMP-B-rst_clk_wiz_0_100M — Reset Kontrolcüsü

```
VLNV              : xilinx.com:ip:proc_sys_reset:5.0
Güven             : HIGH
Sentez Doğrulandı : Evet

Bağlantılar:
  dcm_locked    ← clk_wiz_0/locked
  ext_reset_in  ← board reset G4 (active-low, LVCMOS15)
  peripheral_aresetn → axi_gpio_0 + interconnect
  mb_reset      → microblaze_0

Fark (PROJECT-A ile): PLL-lock tabanlı (PROJECT-A DDR2 kalibrasyon tabanlı)
```

#### COMP-B-mdm_1 — MicroBlaze Debug (UART'lı)

```
VLNV              : xilinx.com:ip:mdm:3.2
Güven             : HIGH
Sentez Doğrulandı : Evet

Parametreler:
  C_USE_UART = 1 (PROJECT-A'da UART ayrı IP, PROJECT-B'de MDM içinde)

Fark: PROJECT-B MDM'e UART entegre edilmiş → ayrı UARTLite IP gereksiz.
```

#### COMP-B-microblaze_0_axi_periph — AXI Interconnect

```
VLNV     : xilinx.com:ip:axi_interconnect:2.1
Güven    : HIGH

Parametreler:
  NUM_SI   = 1 (MicroBlaze M_AXI_DP)
  NUM_MI   = 1 (axi_gpio_0/s_axi)
  protocol = AXI4-Lite
```

#### COMP-B-lmb_subsystem — LMB Bellek Altsistemi

```
Güven             : HIGH
Sentez Doğrulandı : Evet

Bileşenler:
  dlmb_v10, ilmb_v10
  dlmb_bram_if_cntlr, ilmb_bram_if_cntlr
  lmb_bram_0

Boyut   : 8 KB (PROJECT-A'da 64 KB)
BRAM    : 2 × RAMB36E1 (utilization_summary.txt doğruladı)
```

---

## 4. Faz 2 — CONSTRAINT Node'ları

### PROJECT-A Kısıtları

| Constraint ID | Tip | Özellik | Aktif | Kaynak |
|--------------|-----|---------|-------|--------|
| CONST-A-PIN-001 | pin | `PWM_AUDIO_0_pwm → A11, LVCMOS33` | ✅ Aktif | XDC satır 179 |
| CONST-A-PIN-002 | pin | `PWM_AUDIO_0_en → D12, LVCMOS33` | ✅ Aktif | XDC satır 180 |
| CONST-A-CLK-001 | clock | `sys_clock: 100 MHz, E3, LVCMOS33` | ✅ | design_1.tcl |
| CONST-A-CLK-002 | clock | `clk_out1: 140.625 MHz → MIG sys_clk_i` | ✅ | design_1.tcl |
| CONST-A-CLK-003 | clock | `clk_out2: 24.576 MHz → fifo2audpwm + FIFO rd_clk` | ✅ | design_1.tcl |
| CONST-A-CLK-004 | clock | `MIG ui_clk: ~81 MHz → MB + AXI fabric` | MEDIUM ⚠️ | MIG config (türetilmiş) |
| CONST-A-MEM-001 | memory | `DDR2 128 MB @ 0x80000000, MIG v4.1` | ✅ | design_1.tcl |
| CONST-A-ADDR-001 | address | `GPIO_IN: 0x40000000` | ✅ | design_1.tcl |
| CONST-A-UART-001 | interface | `AXI UARTLite: 230400 baud, 8N1, polling` | ✅ | design_1.tcl |
| CONST-A-DMA-001 | bandwidth | `AXI DMA: 256-byte burst, 27-bit addr, simple mode` | ✅ | design_1.tcl |

**Not:** XDC dosyasında yalnızca 2 pin aktif (uncommented). Tüm diğer pinler (HDMI, switches, LEDs vb.) yorumlu durumda.

### PROJECT-B Kısıtları

| Constraint ID | Tip | Özellik | Aktif | Kaynak |
|--------------|-----|---------|-------|--------|
| CONST-B-CLK-001 | clock | `sys_clock: 100 MHz, R4, LVCMOS33, 10.000 ns` | ✅ | nexys_video.xdc satır 4-5 |
| CONST-B-PIN-RST | pin | `resetn → G4, LVCMOS15 (active-low)` | ✅ | nexys_video.xdc satır 8 |
| CONST-B-PIN-LED0..7 | pin | `LED[0:7] → T14..Y13, LVCMOS25` | ✅ | nexys_video.xdc |
| CONST-B-PIN-SW0..7 | pin | `SW[0:7] → E22..M17, LVCMOS12` | ✅ | nexys_video.xdc |
| CONST-B-ADDR-001 | address | `AXI GPIO: 0x40000000 - 0x4000FFFF (64 KB)` | ✅ | add_axi_gpio.tcl |

**CRITICAL WARNING (ISSUE-B-001):** nexys_video.xdc'de `sys_clk_pin` ile `sys_clock` ikili tanım. Vivado [Constraints 18-1056]: son tanım geçerli. Timing yine de geçiyor.

---

## 5. Faz 2 — EVIDENCE Node'ları

### PROJECT-A Kanıtları

| Evid. ID | Tip | İçerik | Dosya:Satır | Güven |
|----------|-----|--------|-------------|-------|
| EVID-A-001 | code | `assign fifo_wr_data = axis_tdata[15:0];` → 32→16 bit truncation | axis2fifo.v:35 | HIGH |
| EVID-A-002 | code | `assign aud_pwm = count[DATA_WIDTH-1:0] <= duty[...]` → 256-level PWM | fifo2audpwm.v:37 | HIGH |
| EVID-A-003 | code | `assign axis_tlast = 1'b1;` → **SABİT 1 BUG** | tone_generator.v:69 | HIGH |
| EVID-A-004 | code | `case DEMO_MODE_HW_TONE_GEN: break;` → HW ton devre dışı | helloworld.c:386 | HIGH |
| EVID-A-005 | code | `(u8)((u16)(wav_data[i]+32768)>>8)` → 16→8 bit dönüşüm | helloworld.c:287 | HIGH |
| EVID-A-006 | code | `assign axis_tready = ~fifo_full;` → backpressure | axis2fifo.v:33 | HIGH |
| EVID-A-007 | code | `aud_en <= (fifo_empty == 0)` → akış kontrolü | fifo2audpwm.v:23-26 | HIGH |
| EVID-A-008 | doc | `README: "Hardware Tone Generation functionality is not currently working."` | README.md | HIGH |
| EVID-A-009 | config | `set_property part xc7a50ticsg324-1L` → 50T (KRİTİK) | project_info.tcl:4 | HIGH |
| EVID-A-010 | config | `create_project project_1 myproj -part xc7a50ticsg324-1L` → 50T (CORROBORATION) | design_1.tcl:53 | HIGH |
| EVID-A-011 | code | `assign axis_tvalid = 1;` → her zaman geçerli | tone_generator.v:51 | HIGH |
| EVID-A-012 | code | `TODO: create AXI interface for INCREMENT and PACKET_SIZE` | tone_generator.v:72 | MEDIUM |

### PROJECT-B Kanıtları

| Evid. ID | Tip | İçerik | Dosya | Güven |
|----------|-----|--------|-------|-------|
| EVID-B-001 | report | Sentez PASS: 1412 LUT (1.05%), 1285 FF, 2 BRAM, WNS > 0 ns, 1 MMCME2_ADV, 3 BUFGCTRL | utilization_summary.txt | HIGH |
| EVID-B-002 | code | AXI tie-off: awvalid=0, wvalid=0, arvalid=0, bready=1, rready=1 | axi_gpio_wrapper.v:13-31 | HIGH |
| EVID-B-003 | doc | 3 CRITICAL WARNING: dup clock, UART ports, LMB clock mismatch (hepsi non-blocking) | SYNTHESIS_RESULTS.md | HIGH |

---

## 6. Faz 2 — ISSUE Node'ları

### PROJECT-A Issues (8 adet)

#### ISSUE-A-001 — FPGA Part Tutarsızlığı ★ KRİTİK

```
Severity : CRITICAL
Güven    : HIGH
Kanıtlar : EVID-A-009, EVID-A-010

Sorun:
  project_info.tcl satır 4 : set_property part xc7a50ticsg324-1L (50T)
  design_1.tcl satır 53    : create_project -part xc7a50ticsg324-1L (50T)
  XDC dosya adı             : Nexys-A7-100T-Master.xdc (100T)
  README.md                 : "Nexys A7 100T" (100T)

Etki:
  50T: 50K LUT, 100 DSP, 512 KB BRAM
  100T: 100K LUT, 240 DSP, 1800 KB BRAM
  → Yanlış FPGA için bit dosyası üretiliyor
  → 100T kartta ÇALIŞMAZ (farklı package, farklı silikon)
  → 140.625 MHz MIG clock: 50T DDR2 PHY timing farklı

Düzeltme:
  project_info.tcl  : set_property "part" "xc7a100tcsg324-1"
  project_info.tcl  : set_property "board_part" "digilentinc.com:nexys-a7-100t:part0:1.0"
  design_1.tcl:53   : create_project project_1 myproj -part xc7a100tcsg324-1
```

#### ISSUE-A-002 — HW Tone Generator Çalışmıyor ★ HIGH

```
Severity : HIGH
Güven    : HIGH
Parse    : PARSE_UNCERTAIN_WHY_DISABLED
Kanıtlar : EVID-A-003, EVID-A-004, EVID-A-008, EVID-A-011, EVID-A-012

Bug 1 — axis_tlast Sabiti (tone_generator.v:69):
  Mevcut : assign axis_tlast = 1'b1;   // Her cycle TLAST aktif
  Beklenen: assign axis_tlast = (packet_count == PACKET_SIZE - 1);

  Etki: DMA her beat'i ayrı paket sayar → DMA interrupt'ları saçılır
        Scatter-Gather olmasa da DMA transfer mantığı bozulur

Bug 2 — Genişlik Uyumsuzluğu:
  tone_generator çıkış : {16'b0, duty[31:16]} — 32-bit kelime, 16-bit audio
  fifo2audpwm giriş    : fifo_rd_data[7:0] — 8-bit okuma
  Uyumsuzluk           : Beklenen ses verisi yanlış byte'ı alır

Bug 3 — Yazılım Devre Dışı (helloworld.c:386):
  case DEMO_MODE_HW_TONE_GEN: break;  // Hiçbir şey yapılmıyor

Düzeltme Adımları:
  1) tone_generator.v: axis_tlast mantığını packet_count bazlı düzelt
  2) axis_tdata çıkışını 8-bit ile uyumlu hale getir
  3) helloworld.c: DEMO_MODE_HW_TONE_GEN case'ine dma_forward çağrısı ekle
```

#### ISSUE-A-003 — 32→16 Bit Truncation — MEDIUM

```
Severity : MEDIUM
Kanıtlar : EVID-A-001
axis2fifo.v:35 — assign fifo_wr_data = axis_tdata[15:0];
Etki: Üst 16-bit ses verisi kaybolur. DMA 32-bit transferde işaret biti
      dahil 16-bit audio'nun tamamını taşısa da sadece alt 16-bit FIFO'ya yazılır.
```

#### ISSUE-A-004 — 8-bit WAV Ses Kalitesi — MEDIUM

```
Severity : MEDIUM
Kanıtlar : EVID-A-005
16-bit WAV → 8-bit truncation → ~48 dB SNR (16-bit yerine ~8-bit SNR)
```

#### ISSUE-A-005 — Sadece 96 kHz WAV — LOW

```
Severity : LOW
PWM clock sabit (24.576 MHz / 256 = 96 kHz). Farklı sample rate WAV reddedilir.
```

#### ISSUE-A-006 — Interrupt Kullanılmıyor — LOW (DECISION)

```
Severity : LOW
INTC + xlconcat donanımda kurulu. Yazılım polling kullanıyor.
Sınıflandırma: DMA-DEC-005 (DECISION) — Coverage Gap DEĞİL
```

#### ISSUE-A-007 — Testbench Yok — INFO

```
Severity : INFO
Simülasyon testbench'i yok. Doğrulama sadece hardware üzerinde.
Signal Path timing analizi için WNS bilinmiyor.
```

#### ISSUE-A-008 — Git Submodule Init Edilmemiş — INFO

```
Severity : INFO
digilent-vivado-scripts submodule init edilmemiş.
TCL build automation çalışmaz (DMA-REQ-L1-005 etkisi).
```

### PROJECT-B Issues (3 adet)

#### ISSUE-B-001 — Duplicate Clock Constraint — LOW

```
Severity : LOW
nexys_video.xdc'de sys_clock ve sys_clk_pin ikili tanım.
Vivado [Constraints 18-1056] CRITICAL WARNING üretiyor.
Timing yine de geçiyor (WNS > 0). XDC temizlenmeli.
```

#### ISSUE-B-002 — XDC'de Tanımsız UART Portları — INFO

```
Severity : INFO
XDC'de usb_uart_rxd, usb_uart_txd tanımlı ama design'da UART yok.
Vivado [Common 17-55] CRITICAL WARNING üretiyor.
```

#### ISSUE-B-003 — Seviye 3 Tamamlanmamış — MEDIUM (GAP-B-001)

```
Severity : MEDIUM
Block Automation timeout: create_axi_auto.tcl ve create_axi_with_xdc.tcl stabil değil.
README: "⏳ Geliştirilmekte — Connection Automation stuck (5+ dakika)"
Düzeltme: Manuel BD connection script yaz (block automation bypass et)
```

---

## 7. Faz 2 — PATTERN Node'ları

### PROJECT-A Pattern'ları (6 adet)

| ID | Pattern | Örnek | Eğitim Değeri |
|----|---------|-------|---------------|
| PAT-A-001 | **Phase Accumulator Ton Üretimi** `duty += INC; out = duty >> N` | tone_generator.v + helloworld.c (SW) | YÜKSEK |
| PAT-A-002 | **AXI-Stream → FIFO Köprüsü** `tready = ~full; wr_en = tready & tvalid` | axis2fifo.v | YÜKSEK |
| PAT-A-003 | **Sayaç Tabanlı PWM** `pwm = (counter < duty_cycle)` | fifo2audpwm.v | YÜKSEK |
| PAT-A-004 | **Çift-Clock FIFO CDC** Bağımsız clock modu, gray-code pointer sync | fifo_generator_0 | YÜKSEK |
| PAT-A-005 | **FIFO Backpressure via Full Flag** `tready = ~fifo_full` → DMA durdurma | axis2fifo.v:33 | YÜKSEK |
| PAT-A-006 | **WAV Header Parsing via Struct Cast** `Wav_HeaderRaw* h = (Wav_HeaderRaw*)buf` | helloworld.c | ORTA |

### PROJECT-B Pattern'ları (7 adet)

| ID | Pattern | Örnek | Eğitim Değeri |
|----|---------|-------|---------------|
| PAT-B-001 | **AXI Slave Tie-off** awvalid=0, wvalid=0, arvalid=0, bready=1, rready=1 | axi_gpio_wrapper.v | ÇOK YÜKSEK |
| PAT-B-002 | **Block Automation** `apply_bd_automation -rule xilinx.com:bd_rule:microblaze` | create_minimal_microblaze.tcl | YÜKSEK |
| PAT-B-003 | **Iteratif BD Yapısı** Minimal BD → IP ekle → bağla → sentezle | TCL script chain | YÜKSEK |
| PAT-B-004 | **AXI Adres Ataması** `assign_bd_address` ile otomatik harita | add_axi_gpio.tcl | YÜKSEK |
| PAT-B-005 | **PLL Lock → Reset Release** `clk_wiz.locked → proc_sys_reset.dcm_locked` | create_minimal_microblaze.tcl | YÜKSEK |
| PAT-B-006 *(YENİ — UPD-004)* | **Explicit AXI Adres Haritası** `assign_bd_address [get_bd_addr_segs ...]` | add_axi_gpio.tcl | YÜKSEK |
| PAT-B-007 *(YENİ — UPD-004)* | **Out-of-Context (OOC) Synthesis** incremental sentez modu | run_synthesis.tcl | ORTA |

---

## 8. Faz 3 — Gereksinim Ağacı (REQUIREMENT)

### 8.1 PROJECT-A Gereksinimleri

```
DMA-REQ-L0-001 [must, L0]
  "Nexys A7-100T üzerinde DMA tabanlı ses akışı demo uygulaması"
  ├── Tüm L1 isterlerin köküdür
  │
  ├── DMA-REQ-L1-001 [must, L1] — DDR2 Tabanlı Tamponlu Ses Akışı
  │   ├── DMA-REQ-L2-001 [must]   FPGA part = xc7a100tcsg324-1
  │   │                            ⚠️ ISSUE-A-001 (critical) — TCL 50T kullanıyor
  │   ├── DMA-REQ-L2-002 [must]   DDR2 ≥128 MB, MIG 7-Series arbitrasyonu
  │   ├── DMA-REQ-L2-003 [should] HW Tone Generator (261 Hz, phase acc.)
  │   │                            ⚠️ PARSE_UNCERTAIN_WHY_DISABLED
  │   │                            ⚠️ ISSUE-A-002 (high) — axis_tlast bug
  │   └── DMA-REQ-L2-004 [must]   Dual-clock FIFO CDC (81 MHz → 24.576 MHz)
  │
  ├── DMA-REQ-L1-002 [must, L1] — MicroBlaze Firmware + SDK
  │   ├── DMA-REQ-L2-005 [must]   DMA simple mode, WAV 96kHz, ses oynatma
  │   │                            ⚠️ ISSUE-A-003 (16-bit trunc), ISSUE-A-004 (8-bit qual)
  │   ├── DMA-REQ-L2-006 [must]   GPIO buton/LED kontrolü
  │   ├── DMA-REQ-L2-007 [must]   UART serial console (230400 baud)
  │   └── DMA-REQ-L2-008 [could]  UART seçimi arasındaki fark
  │                                ⚠️ PARSE_UNCERTAIN
  │
  ├── DMA-REQ-L1-003 [must, L1] — Güç ve Saat Yönetimi
  │   ├── DMA-REQ-L2-008 [must]   Saat mimarisi: 100→140.625+24.576 MHz
  │   └── DMA-REQ-L2-009 [must]   Reset zinciri (MIG DDR2 kalibrasyon tabanlı)
  │
  ├── DMA-REQ-L1-004 [must, L1] — Debug Altyapısı
  │   └── DMA-REQ-L2-010 [could]  JTAG MDM debug (MicroBlaze MDM v3.2)
  │
  ├── DMA-REQ-L1-005 [could, L1] — Otomasyon/Build (TCL script tabanlı)
  │   ⚠️ ISSUE-A-008: Git submodule init edilmemiş
  │
  ├── DMA-REQ-L1-006 [must, L1] — Sinyal Yolu (Signal Path) ← SA-005
  │   Kapsamı: clock dağıtımı, reset zinciri, AXI-S handshake,
  │            CDC FIFO, backpressure, interrupt routing (HW)
  │   Eksik: timing verification (implementation çalıştırılmamış)
  │
  └── (DMA-REQ-L1-007) — AXI-Stream Ses Akışı (L1-006 kapsamında)
      ← axis2fifo + fifo2audpwm tüm handshake
```

**Acceptance Criteria Örneği (DMA-REQ-L2-001):**
```yaml
acceptance_criteria:
  - "project_info.tcl ve design_1.tcl xc7a100tcsg324-1 kullanmalı"
  - "board_part digilentinc.com:nexys-a7-100t:part0:1.0 olmalı"
  - "Sentez 100T hedefiyle başarılı tamamlanmalı"
```

---

### 8.2 PROJECT-B Gereksinimleri

```
AXI-REQ-L0-001 [must, L0]
  "AXI bus mimarisi eğitim ve validasyon test suite"
  ├── Kademeli 3-seviyeli ilerleme
  │
  ├── AXI-REQ-L1-001 [must, L1] — GPIO Kontrolü
  │   └── AXI-REQ-L2-001 [must]  GPIO base adresi = 0x40000000
  │
  ├── AXI-REQ-L1-002 [must, L1] — MicroBlaze Soft-Core İşlemci
  │   └── AXI-REQ-L2-002 [must]  8KB LMB BRAM, cache yok
  │
  ├── AXI-REQ-L1-003 [must, L1] — Saat Yönetimi
  │   └── AXI-REQ-L2-003 [must]  100 MHz → MMCME2_ADV → 3 BUFGCTRL → fabric
  │
  ├── AXI-REQ-L1-004 [must, L1] — Reset Yönetimi
  │   ├── AXI-REQ-L2-004 [must]  WNS > 0 ns (sentez doğrulaması)
  │   └── AXI-REQ-L2-006 [must]  PLL lock → reset release
  │
  ├── AXI-REQ-L1-005 [must, L1] — AXI-Lite Sinyal Yolu ← SA-005
  │   └── AXI-REQ-L2-005 [must]  WNS > 0 ns ile sentez PASS ✅
  │                                (EVID-B-001: 1.05% LUT, WNS > 0)
  │
  └── AXI-REQ-L1-006 [must, L1] — Eğitim Metodolojisi (CLI-First TCL)
      └── AXI-REQ-L2-006 [must]  3 seviyeli kademeli ilerleme
                                  ⚠️ Seviye 3 eksik (GAP-B-001)
```

---

## 9. Faz 3 — DECISION Kayıtları

### PROJECT-A Kararları

#### DMA-DEC-001 — Clocking Wizard ile Çoklu Clock Üretimi

```
Güven: HIGH
Karar: 100 MHz girişten 2 çıkış üretmek için Clocking Wizard kullanımı.

clk_out1 = 140.625 MHz: DDR2 PHY için MIG referans clock
clk_out2 = 24.576 MHz : Ses için (96 kHz × 256 = 24.576 MHz)

Neden bu değerler:
  140.625 MHz = en yakın MMCM-achievable DDR2 optimal frekansı
  24.576 MHz  = ses codec standart clock'u (8/48/96 kHz tamsayı çarpanı)
```

#### DMA-DEC-002 — DMA Simple Mode (Scatter-Gather Yok)

```
Güven: HIGH
Karar: AXI DMA Simple mode (c_include_sg=0)
Kanıt: helloworld.c:50 — SG modu açıkça reddedilmiş

Seçilme nedeni: Demo sadeliği. SG buffer descriptor yönetimi karmaşık.
Reddedilen alternatif: DMA Scatter-Gather modu
```

#### DMA-DEC-003 — Bağımsız Clock FIFO (CDC için)

```
Güven: HIGH
Karar: fifo_generator_0 independent_clocks modu (gray-code CDC)
Neden: 81 MHz MIG clock ve 24.576 MHz audio clock arasında güvenli geçiş
Reddedilen: Senkron FIFO (CDC uyumsuzluğu riski)
```

#### DMA-DEC-004 — 8-bit PWM Çözünürlüğü

```
Güven: HIGH
Hesap: f_pwm = 24.576 MHz / 2^8 = 96 kHz (duyulabilir bandı aşıyor ✅)
       f_pwm = 24.576 MHz / 2^12 = 6 kHz (duyulabilir banda giriyor ✗)
Karar: 8-bit maksimum çözünürlük bu clock frekansında mümkün
```

#### DMA-DEC-005 — Interrupt Donanımı Kuruldu, SW Polling Kullanıyor ★

```
Güven    : MEDIUM
Parse    : PARSE_UNCERTAIN (motivasyon belgelenmemiş)
Sınıf    : DECISION — Coverage Gap DEĞİL (UPD-003)

v2.1 Açıklaması:
  "Hardware requirement DMA-REQ-L2-011 SATISFIED.
   HW component (xlconcat + INTC) mevcut.
   SW polling is architectural choice, not a coverage gap."

Seçilen: Donanımda interrupt mevcut, yazılımda polling
Reddedilenler:
  A) Tam interrupt-driven: ISR karmaşıklığı (context, stack, race condition)
  B) INTC hiç koymamak: Gelecek geliştirme için esneklik kaybı

Sonuçlar:
  - CPU sürekli meşgul (while(1) döngüsü)
  - Buton basışları DMA transfer sırasında kaçırılabilir
  - INTC ve xlconcat donanım kaynağı kullanımda ama etkin değil
  - Gelecek interrupt-driven geçiş için altyapı hazır
```

### PROJECT-B Kararları

#### AXI-DEC-001 — CLI-First Vivado TCL Metodolojisi

```
Güven: HIGH
Karar: Tüm Vivado işlemleri TCL script ile (GUI değil)
Seçilen: vivado -mode batch -source script.tcl
Neden: Tekrarlanabilirlik, version control, CI/CD uyumu
Reddedilen: GUI-based proje oluşturma (manual, tekrarlanamaz)
```

#### AXI-DEC-002 — MicroBlaze Cache Yok (8KB BRAM)

```
Güven: HIGH
Karar: C_USE_ICACHE=0, C_USE_DCACHE=0
Neden: 8KB BRAM yeterli (eğitim kodu küçük). DDR2 yok → cache gereksiz.
Reddedilen: Cache etkin (DDR2 olmadan cache thrash riski)
```

---

## 10. Faz 4 — Eşleştirme Kenarları

### Uygulanan 5 Strateji

```
Strateji 1 — Exact/Fuzzy Name Match
  Örnek: "axis2fifo" → DMA-REQ-L2-004 (AXI-Stream interface)
  Güven: HIGH

Strateji 2 — Semantic Embedding
  Örnek: tone_generator ↔ "donanım ton üreteci" (DMA-REQ-L2-003)
  Güven: HIGH

Strateji 3 — Structural Traversal
  Örnek: design_1.tcl IP listesi → L2 gereksinim ağacı traversal
         MIG → DDR2 requirement (DMA-REQ-L2-002)
  Güven: HIGH

Strateji 4 — Evidence Binding
  Örnek: EVID-A-009 (project_info.tcl 50T) → ISSUE-A-001 → DMA-REQ-L2-001
  Güven: HIGH

Strateji 5 — Constraint Binding
  Örnek: CONST-A-PIN-001 (A11) → COMP-A-pwm_audio_bus → DMA-REQ-L1-002
  Güven: HIGH
```

### Seçilmiş IMPLEMENTS Kenarları (Örnekler)

| Match ID | Kaynak (Component) | Hedef (Requirement) | Strateji | Güven |
|----------|-------------------|---------------------|----------|-------|
| M-001 | COMP-A-mig_7series_0 | DMA-REQ-L2-002 | struct. traversal | HIGH |
| M-002 | COMP-A-axis2fifo_0 | DMA-REQ-L1-006 | semantic + evidence | HIGH |
| M-003 | COMP-A-fifo2audpwm_0 | DMA-REQ-L1-006 | semantic + evidence | HIGH |
| M-004 | COMP-A-tone_generator_0 | DMA-REQ-L2-003 | exact name | HIGH |
| M-005 | COMP-A-fifo_generator_0 | DMA-REQ-L2-004 | semantic | HIGH |
| M-006 | COMP-A-axi_dma_0 | DMA-REQ-L2-005 | exact name | HIGH |
| M-007 | COMP-A-helloworld | DMA-REQ-L2-005 | structural | HIGH |
| M-008 | COMP-A-GPIO_IN | DMA-REQ-L2-006 | exact name | HIGH |
| M-009 | COMP-A-GPIO_OUT | DMA-REQ-L2-006 | exact name | HIGH |
| M-010 | COMP-A-axi_uartlite_0 | DMA-REQ-L2-007 | exact name | HIGH |
| M-011 | COMP-A-clk_wiz_0 | DMA-REQ-L2-008 | exact name | HIGH |
| M-012 | COMP-A-rst_mig_7series_0_81M | DMA-REQ-L2-009 | semantic | HIGH |
| M-013 | COMP-A-mdm_1 | DMA-REQ-L2-010 | exact name | HIGH |
| M-014 | COMP-A-microblaze_0_axi_intc | DMA-REQ-L2-011 | exact name | HIGH |
| M-101 | COMP-B-axi_gpio_wrapper | AXI-REQ-L1-001 | semantic | HIGH |
| M-102 | COMP-B-axi_gpio_0 | AXI-REQ-L2-001 | constraint_binding | HIGH |
| M-103 | COMP-B-microblaze_0 | AXI-REQ-L1-002 | exact name | HIGH |
| M-104 | COMP-B-clk_wiz_0 | AXI-REQ-L2-003 | evidence_binding | HIGH |
| M-105 | COMP-B-rst_clk_wiz_0_100M | AXI-REQ-L2-006 | semantic | HIGH |
| M-106 | COMP-B-lmb_subsystem | AXI-REQ-L2-002 | semantic | HIGH |

### Seçilmiş CONSTRAINED_BY Kenarları

| Edge ID | Component | Constraint | Kanıt |
|---------|-----------|------------|-------|
| CB-001 | COMP-A-mig_7series_0 | CONST-A-CLK-002 | 140.625 MHz MIG ref clock |
| CB-002 | COMP-A-axi_dma_0 | CONST-A-DMA-001 | 256-byte burst constraint |
| CB-003 | COMP-A-pwm_audio_bus | CONST-A-PIN-001 | A11 aktif XDC pin |
| CB-004 | COMP-B-axi_gpio_0 | CONST-B-ADDR-001 | 0x40000000 base adres |
| CB-005 | COMP-B-clk_wiz_0 | CONST-B-CLK-001 | R4 pin, 100 MHz, 10 ns |

---

## 11. Faz 5 — Özel Analizler

### SA-001 — FPGA Part Tutarsızlığı Doğrulama ✅

```
Analiz: Çapraz kaynak doğrulama (4 kaynak)

Kaynak          │ FPGA Part              │ Kart
─────────────────┼────────────────────────┼───────────────────
project_info.tcl│ xc7a50ticsg324-1L (50T)│ digilentinc.com:nexys-a7-50t
design_1.tcl:53 │ xc7a50ticsg324-1L (50T)│ —
XDC dosya adı   │ —                      │ Nexys-A7-100T-Master.xdc
README.md       │ —                      │ "Nexys A7 100T"
ISTER (istenen) │ xc7a100tcsg324-1 (100T)│ Nexys A7-100T

KARAR: KRITIK TUTARSIZLIK DOĞRULANDI
  → TCL script 50T hedefliyor, kart 100T
  → Sentezlenen bit dosyası 100T kartta ÇALIŞMAZ
  → ISSUE-A-001 severity=critical korundu
  → Bak UPD-001 (ISTER güncelleme)
```

### SA-002 — tone_generator PARSE_UNCERTAIN Değerlendirmesi ✅

```
v2 Mimari Kuralı: PARSE_UNCERTAIN = "mühendis rationale belgelememişse"
                  Bilinmeyen OLGULAR için değil.

Soru                        │ Güven  │ Kaynak
────────────────────────────┼────────┼──────────────────────
"Çalışıyor mu?"             │ HIGH   │ README "not currently working"
"axis_tlast=1 bug var mı?"  │ HIGH   │ tone_generator.v:69 doğrudan
"16-bit/8-bit uyumsuzluk?"  │ HIGH   │ port tanımları doğrudan
"Neden düzeltilmedi?"       │ PARSE_UNCERTAIN │ Mühendis belgesi yok

KARAR:
  PARSE_UNCERTAIN scope = yalnızca "WHY disabled" sorusu
  Fonksiyonel uyumsuzluk = ISSUE-A-002 (HIGH confidence, high severity)
  parse_flag = PARSE_UNCERTAIN_WHY_DISABLED (UPD-002)
```

### SA-003 — Interrupt Altyapısı Sınıflandırması ✅

```
Faktör                       │ Değerlendirme
─────────────────────────────┼──────────────────────────────────────────
DMA-REQ-L2-011 ne istiyor?  │ "Interrupt infrastructure donanımı"
xlconcat_0/1 var mı?         │ EVET — design_1.tcl'de kurulu
INTC var mı?                 │ EVET — 0x41200000'da kurulu
SW interrupt kullanıyor mu?  │ HAYIR — polling (DMA-DEC-005)
Coverage Gap tanımı          │ "Requirement için hiçbir component yok"
Buradaki durum               │ Component VAR, kullanım tercihi yapılmış

KARAR: DECISION (DMA-DEC-005) — Coverage Gap DEĞİL
v2 Prensibi: "Coverage Gap = bileşen yok. Decision = bileşen var,
              kullanım tercihi belgelenmiş."
```

### SA-004 — axi_example Eğitim Pattern Yeterliliği ✅

```
Mevcut 5 Pattern Değerlendirmesi:
  PAT-B-001 (AXI Tie-Off)           → ÇOK YÜKSEK ✅ — AXI sinyal semantiği
  PAT-B-002 (Block Automation)      → YÜKSEK ✅ — Vivado automation workflow
  PAT-B-003 (Iteratif BD Yapısı)    → YÜKSEK ✅ — incremental development
  PAT-B-004 (AXI Adres Ataması)     → YÜKSEK ✅ — address mapping
  PAT-B-005 (PLL Lock → Reset)      → YÜKSEK ✅ — evrensel FPGA pattern

KARAR: YETERLI — 5 pattern eğitimsel hedeflere ulaşıyor.

Önerilen 2 Ek Pattern (UPD-004):
  PAT-B-006: AXI Address Map Explicit Assignment
    Kaynak: add_axi_gpio.tcl — assign_bd_address [get_bd_addr_segs ...]
    Değer: Çok-periferik sistemlerde overlap önleme — KRİTİK
    Eğitim: Implicit vs explicit adres ataması farkı

  PAT-B-007: Out-of-Context (OOC) Synthesis
    Kaynak: run_synthesis.tcl + SYNTHESIS_RESULTS.md
    Değer: Incremental synthesis için hız artışı
    Eğitim: Synthesis modu farkındalığı (OOC vs regular)
```

### SA-005 — Signal Path Ekseni Kapsam Analizi ✅

```
PROJECT-A: SUBSTANTIALLY_COVERED

Signal Path Noktası               │ Durum          │ Kanıt
──────────────────────────────────┼────────────────┼────────────────────
Clock dağıtımı (100→140.625+24.576)│ ✅ COVERED     │ COMP-A-clk_wiz_0
Reset zinciri (MIG sync_rst→periph)│ ✅ COVERED     │ COMP-A-rst_mig_*
AXI-S handshake (tvalid/tready/t..)│ ✅ COVERED     │ COMP-A-axis2fifo_0
FIFO CDC gray-code pointer sync    │ ✅ COVERED     │ COMP-A-fifo_gen_0
FIFO backpressure (full→tready)    │ ✅ COVERED     │ EVID-A-006
Akış kontrolü (empty→aud_en)       │ ✅ COVERED     │ EVID-A-007
Interrupt routing (HW)             │ ✅ HW_ONLY     │ DMA-DEC-005
Timing doğrulama (WNS)             │ ❌ NOT_COVERED │ Implementation yok

Eksik: Timing raporu — implementation çalıştırılmamış.
       ISSUE-A-007 ile ilişkilendirildi.

PROJECT-B: WELL_COVERED

Signal Path Noktası               │ Durum          │ Kanıt
──────────────────────────────────┼────────────────┼────────────────────
Clock dağıtımı (100 MHz PLL→BUFG) │ ✅ COVERED     │ EVID-B-001 (MMCME2_ADV)
Reset zinciri (PLL locked→periph)  │ ✅ COVERED     │ COMP-B-rst_*
AXI-Lite handshake (MB→periph→GPIO)│ ✅ COVERED     │ COMP-B-axi_periph
AXI tie-off (standalone modda)     │ ✅ COVERED     │ PAT-B-001, EVID-B-002
GPIO output (register→LED pin)     │ ✅ COVERED     │ CONST-B-PIN-LED0..7
Timing doğrulama (WNS > 0 ns)     │ ✅ COVERED     │ EVID-B-001 (synthesis)
Interrupt path                     │ — NOT_PRESENT  │ Kapsam dışı (eğitim)

Avantaj: Tek clock domain Signal Path analizini basitleştiriyor.
```

---

## 12. Faz 5 — Coverage Gap Raporu

### GAP-A-001 — tone_generator Fonksiyonel Uyumsuzluk

```
Proje      : PROJECT-A
Severity   : HIGH
Tip        : REQUIREMENT_PARTIAL_MATCH
Gereksinim : DMA-REQ-L2-003 (HW Ton Üreteci)

Durum:
  Bileşen VAR mı?              → EVET (tone_generator_0)
  Fonksiyonel uyumlu mu?       → HAYIR (axis_tlast bug + bit-width uyumsuzluk)
  "Should" ister karşılanıyor? → HAYIR

Neden tam Coverage Gap değil:
  Bileşen mevcut → implementasyon var ama çalışmıyor.
  Bu PARTIAL_MATCH (fonksiyonel uyumsuzluk).

Düzeltme:
  1) axis_tlast mantığı: packet_count == PACKET_SIZE-1 olarak düzelt
  2) Çıkış genişliği uyumu: fifo2audpwm 8-bit bekliyor
  3) helloworld.c: DEMO_MODE_HW_TONE_GEN aktifleştir
```

### GAP-B-001 — Seviye 3 Tam Sistem Tamamlanmamış

```
Proje      : PROJECT-B
Severity   : INFO
Tip        : PLANNED_NOT_IMPLEMENTED
Gereksinim : AXI-REQ-L0-001 (Seviye 3 kademeli ilerleme)

Durum:
  Bileşen VAR mı?    → HAYIR (Seviye 3 tamamlanmamış)
  Planlı mı?         → EVET (README'de ⏳ işareti)

Sorun: Block Automation + Connection Automation timeout (5+ dakika)
       create_axi_auto.tcl ve create_axi_with_xdc.tcl stabil değil

Düzeltme:
  Block automation bypass → Manuel BD connection script
  `connect_bd_intf_net [get_bd_intf_pins mb/M_AXI] [get_bd_intf_pins ic/S00_AXI]`
```

---

## 13. Faz 5 — Orphan Component Raporu

### ORP-A-001 — xlconcat_0 (DMA Interrupt Concat)

```
Proje         : PROJECT-A
Component     : COMP-A-xlconcat_0
Formal Orphan : HAYIR

Bağlantılar (donanımda):
  In0 ← axi_dma_0/mm2s_introut
  In1 ← axi_dma_0/s2mm_introut
  dout → microblaze_0_axi_intc

Yazılım kullanımı: YOK (DMA-DEC-005 kapsamında polling seçildi)

Sınıflandırma: Formal Orphan DEĞİL.
DMA-REQ-L2-011 kapsamında donanım implement edilmiş.
DMA-DEC-005 (DECISION) yazılım polling tercihini açıklıyor.
```

### ORP-A-002 — xlconcat_1 (GPIO+UART Interrupt Concat)

```
Proje         : PROJECT-A
Component     : COMP-A-xlconcat_1
Formal Orphan : HAYIR

Bağlantılar (donanımda):
  In0 ← GPIO_IN/ip2intc_irpt
  In1 ← GPIO_OUT/ip2intc_irpt
  In2 ← axi_uartlite_0/interrupt
  dout → microblaze_0_axi_intc

ORP-A-001 ile aynı sınıflandırma. DMA-DEC-005 kapsamında.
```

---

## 14. Faz 5 — Çapraz Proje Kenarları

### ANALOGOUS_TO Kenarları (6 adet)

| Edge ID | Kaynak (A) | Hedef (B) | Benzerlik | Fark |
|---------|------------|-----------|-----------|------|
| XP-001 | COMP-A-clk_wiz_0 | COMP-B-clk_wiz_0 | Her ikisi Clocking Wizard v6.0 | A: 2 çıkış (140.625+24.576); B: 1 çıkış (100 MHz) |
| XP-002 | COMP-A-rst_mig_7series_0_81M | COMP-B-rst_clk_wiz_0_100M | Her ikisi proc_sys_reset v5.0 | A: DDR2 calibration trigger; B: PLL-lock trigger |
| XP-003 | COMP-A-mdm_1 | COMP-B-mdm_1 | Her ikisi MDM v3.2, JTAG debug | B: C_USE_UART=1 (dahili UART); A: ayrı UARTLite IP |
| XP-004 | COMP-A-microblaze_0 | COMP-B-microblaze_0 | Her ikisi MicroBlaze soft-core | A: v10 + I+D cache (DDR2); B: v11 cache yok (8KB) |
| XP-005 (REUSES) | PAT-B-005 | PAT-A-004 | PLL Lock→Reset Release pattern | A: MIG ui_clk_sync_rst ek reset kaynağı |
| XP-006 | COMP-A-GPIO_IN | COMP-B-axi_gpio_0 | Her ikisi AXI GPIO v2.0 | A: Dual-ch, 5+16-bit I/O; B: 8-bit output only |

---

## 15. Faz 6 — ISTER Dokümanı Güncellemeleri

### Uygulanan 6 Güncelleme (v2.0 → v2.1)

#### UPD-001 — PROJECT-A FPGA Part Ayrımı (CORRECTION)

```
Bölüm: # 2. PROJECT Node Tanımları / PROJECT-A

Değişiklik:
  ÖNCE:  fpga_part: "xc7a100tcsg324-1"
  SONRA: fpga_part_intended: "xc7a100tcsg324-1"
         fpga_part_actual_tcl: "xc7a50ticsg324-1L"
         issue_refs: ["ISSUE-A-001"]

v2 Prensibi: Evidence-based fact — no speculation
Açıklama: project_info.tcl satır 4 ve design_1.tcl satır 53 doğrudan
          okunarak xc7a50ticsg324-1L'ın kullanıldığı kesin olarak doğrulandı.
```

#### UPD-002 — DMA-REQ-L2-003 PARSE_UNCERTAIN Kapsam Netleştirmesi (CLARIFICATION)

```
Bölüm: DMA-REQ-L2-003 (tone_generator isteği)

Değişiklik:
  ÖNCE:  # PARSE_UNCERTAIN: tone_generator'ın neden devre dışı bırakıldığına dair...
  SONRA: # parse_flag: PARSE_UNCERTAIN_WHY_DISABLED
         # "Çalışmıyor" gerçeği HIGH confidence (README + kod)
         # "Neden" PARSE_UNCERTAIN (mühendis belgesi yok)
         # gap_id: GAP-A-001

v2 Prensibi: PARSE_UNCERTAIN = engineer not documented rationale.
             Not = unknown facts.
```

#### UPD-003 — DMA-DEC-005 Sınıflandırma Rationale (CLASSIFICATION_CONFIRMED)

```
Bölüm: DMA-DEC-005 Decision Record

Değişiklik:
  # classification: DECISION — Coverage Gap DEĞİL
  # rationale: "Hardware requirement DMA-REQ-L2-011 SATISFIED.
  #             HW component mevcut. SW polling is architectural choice."
  # v2_principle: "Coverage Gap = bileşen yok."

v2 Prensibi: Coverage Gap = no component. Decision = component present,
             usage choice documented.
```

#### UPD-004 — PAT-B-005/006/007 Pattern Eklentisi (ADDITION)

```
Bölüm: 5.4.5 PATTERN Node'ları (PROJECT-B)

Değişiklik: Tablo'ya 3 satır eklendi:
  PAT-B-005 | PLL Lock → Reset Release | create_minimal_microblaze.tcl
  PAT-B-006 | AXI Address Map Explicit | add_axi_gpio.tcl
  PAT-B-007 | Out-of-Context Synthesis  | run_synthesis.tcl + SYNTHESIS_RESULTS.md

Not: PAT-B-005 mevcut ISTER'de yoktu (eksik).
     PAT-B-006 ve PAT-B-007 yeni keşfedildi.
```

#### UPD-005 — Signal Path Kapsam Analizi Referansı (ADDITION)

```
Etkilenen Bölümler:
  DMA-REQ-L1-006 (PROJECT-A Signal Path)
  AXI-REQ-L1-005 (PROJECT-B Signal Path)

Değişiklik (her ikisine eklendi):
  # [UPD-005] Signal Path Kapsam Analizi (SA-005):
  #   PROJECT-A: SUBSTANTIALLY_COVERED (timing raporu eksik)
  #   PROJECT-B: WELL_COVERED (WNS > 0 ns doğrulandı)

v2 Prensibi: Evidence binding — timing claims backed by actual tool reports.
```

#### UPD-006 — SOURCE_DOC Path Normalizasyonu (CORRECTION)

```
Bölüm: # 3. SOURCE_DOC Node Tanımları (tüm SDOC-A-001..009 ve SDOC-B-001..011)

Değişiklik (20 kayıt):
  ÖNCE:  path: "/home/testpc/fpga_asist_dev/validation_test/..."
  SONRA: path: "/home/test123/GC-RAG-VIVADO-2/data/code/..."        (PROJECT-A)
         path: "/home/test123/Desktop/fpga_asist_dev-master/..."    (PROJECT-B)
         path_legacy: "/home/testpc/..." (eski yol korundu)

v2 Prensibi: Provenance accuracy — paths must be resolvable.
```

---

## 16. Özet Sayısal Tablo

### Node Sayıları

| Node Tipi | PROJECT-A | PROJECT-B | Toplam |
|-----------|-----------|-----------|--------|
| PROJECT | 1 | 1 | **2** |
| SOURCE_DOC | 9 | 11 | **20** |
| COMPONENT (RTL) | 3 | 2 | **5** |
| COMPONENT (IP Core) | 14 | 7 | **21** |
| COMPONENT (SW/Interface) | 2 | 0 | **2** |
| CONSTRAINT | 10 | 5 | **15** |
| EVIDENCE | 12 | 3 | **15** |
| ISSUE | 8 | 3 | **11** |
| PATTERN | 6 | 7 | **13** |
| REQUIREMENT (L0) | 1 | 1 | **2** |
| REQUIREMENT (L1) | 6 | 6 | **12** |
| REQUIREMENT (L2) | 11 | 6 | **17** |
| DECISION | 5 | 2 | **7** |
| **TOPLAM** | **88** | **54** | **142** |

### Edge Sayıları

| Edge Tipi | Sayı |
|-----------|------|
| IMPLEMENTS | ~80 |
| VERIFIED_BY | ~15 |
| CONSTRAINED_BY | 5 |
| DECOMPOSES_TO | ~29 |
| MOTIVATED_BY | ~11 |
| ALTERNATIVE_TO | ~10 |
| DEPENDS_ON | ~15 |
| ANALOGOUS_TO | 5 |
| REUSES_PATTERN | 1 |
| **TOPLAM** | **~171** |

### Issue Dağılımı (Severity)

| Severity | PROJECT-A | PROJECT-B | Toplam |
|----------|-----------|-----------|--------|
| critical | 1 | 0 | **1** |
| high | 1 | 0 | **1** |
| medium | 2 | 1 | **3** |
| low | 2 | 1 | **3** |
| info | 2 | 1 | **3** |
| **Toplam** | **8** | **3** | **11** |

### Çıktı Dosyaları

| Dosya | Konum | Boyut | Açıklama |
|-------|-------|-------|----------|
| `pipeline_graph.json` | `data/fpga_rag_v2_output/` | 119 KB (2255 satır) | Tam 6-faz JSON çıktısı |
| `pipeline_report.md` | `data/fpga_rag_v2_output/` | 14 KB | Özet rapor |
| `fpga_rag_v2_detayli_analiz.md` | `data/fpga_rag_v2_output/` | Bu dosya | Detaylı analiz |
| `FPGA_RAG_ISTER_DOKUMANI_v2.txt` | `Downloads/` | ~2850 satır | v2.1 güncellenmiş ISTER |

---

## Kritik Aksiyon Listesi

### PROJECT-A — Acil Düzeltmeler

```
1. [CRITICAL] FPGA Part Düzeltmesi
   Dosya: project_info.tcl
   Değişiklik:
     set_property "part" "xc7a100tcsg324-1" $project_obj
     set_property "board_part" "digilentinc.com:nexys-a7-100t:part0:1.0" $project_obj

   Dosya: src/bd/design_1.tcl satır 53
   Değişiklik:
     create_project project_1 myproj -part xc7a100tcsg324-1

2. [HIGH] tone_generator.v axis_tlast Düzeltmesi
   Mevcut  : assign axis_tlast = 1'b1;
   Düzeltme: assign axis_tlast = (packet_count == PACKET_SIZE - 1);
   Ek      : packet_count sayaç registeri ekle (TVALID & TREADY ile sayım)

3. [MEDIUM] tone_generator.v Bit Genişliği Uyumu
   Mevcut  : axis_tdata = {16'b0, duty[31:16]}  (16-bit audio payload)
   Hedef   : fifo2audpwm 8-bit bekliyor
   Seçenek A: axis_tdata = {24'b0, duty[31:24]} (8-bit truncation)
   Seçenek B: fifo2audpwm'yi 16-bit okuyacak şekilde güncelle

4. [MEDIUM] helloworld.c HW Tone Gen Aktivasyonu
   Satır 386 mevcut  : case DEMO_MODE_HW_TONE_GEN: break;
   Satır 386 düzeltme: case DEMO_MODE_HW_TONE_GEN: dma_forward_tone(); break;
```

### PROJECT-B — Geliştirme

```
1. [MEDIUM] Seviye 3 Block Automation Timeout Çözümü
   create_axi_auto.tcl'de manual connection:
     connect_bd_intf_net [get_bd_intf_pins microblaze_0_axi_periph/S00_AXI] \
                         [get_bd_intf_pins microblaze_0/M_AXI_DP]
   Block automation (apply_bd_automation) bypass et

2. [LOW] XDC Temizleme
   nexys_video.xdc'den:
     - Duplicate clock tanımını sil (sys_clock vs sys_clk_pin)
     - Kullanılmayan UART port satırlarını sil
```

---

*FPGA RAG v2 — "Why-Aware" Engineering Memory*
*LLM yalnızca ayrıştırır, eşleştirir ve sunar. Rationale üretmez.*
*Versiyon: 2.1 | 2026-02-23 | 6/6 Faz Tamamlandı*
