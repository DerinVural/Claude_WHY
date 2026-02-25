# FPGA RAG v2 Pipeline Raporu
**Oluşturulma:** 2026-02-23
**Pipeline Versiyonu:** 2.0
**Mimari Referans:** `fpga_rag_architecture_v2.md`
**ISTER Dokümanı:** `FPGA_RAG_ISTER_DOKUMANI_v2.txt`
**Tamamlanan Fazlar:** 1 → 2 → 3 → 4 → 5 → 6 ✅

---

## Projeler

| Alan | PROJECT-A | PROJECT-B |
|------|-----------|-----------|
| **İsim** | Nexys-A7-100T-DMA-Audio | axi_example |
| **Kart** | Digilent Nexys A7-100T | Digilent Nexys Video |
| **Hedef Part (İstenen)** | xc7a100tcsg324-1 | xc7a200tsbg484-1 |
| **Gerçek TCL Part** | **xc7a50ticsg324-1L** ⚠️ | xc7a200tsbg484-1 ✅ |
| **Araç** | Vivado 2018.2 + Xilinx SDK | Vivado 2025.1 |
| **Tip** | Uygulama | Eğitim |
| **Dil** | Verilog + C | Verilog |

---

## Faz 1–2: Dosya ve Bileşen Özeti

### PROJECT-A Bileşenleri (22 node)

| Node ID | İsim | Tip | Güven |
|---------|------|-----|-------|
| COMP-A-axis2fifo_0 | axis2fifo | RTL_Module | HIGH |
| COMP-A-fifo2audpwm_0 | fifo2audpwm | RTL_Module | HIGH |
| COMP-A-tone_generator_0 | tone_generator | RTL_Module | HIGH |
| COMP-A-microblaze_0 | MicroBlaze v10.0 | IP_Core | HIGH |
| COMP-A-axi_dma_0 | AXI DMA 7.1 | IP_Core | HIGH |
| COMP-A-mig_7series_0 | MIG 7-Series DDR2 | IP_Core | HIGH |
| COMP-A-clk_wiz_0 | Clocking Wizard v6.0 | IP_Core | HIGH |
| COMP-A-rst_mig_7series_0_81M | proc_sys_reset v5.0 | IP_Core | HIGH |
| COMP-A-fifo_generator_0 | FIFO Generator v13.2 | IP_Core | HIGH |
| COMP-A-axi_intc_0 | AXI INTC v4.1 | IP_Core | HIGH |
| COMP-A-xlconcat_0 | xlconcat v2.1 | IP_Core | HIGH |
| COMP-A-xlconcat_1 | xlconcat v2.1 | IP_Core | HIGH |
| COMP-A-axi_uartlite_0 | AXI UARTLite | IP_Core | HIGH |
| COMP-A-GPIO_IN | AXI GPIO (dual-ch) | IP_Core | HIGH |
| COMP-A-mdm_1 | MDM v3.2 | IP_Core | HIGH |
| COMP-A-helloworld_c | helloworld.c | SW_Application | HIGH |
| COMP-A-pwm_audio_bus | PWM Audio Bus Interface | Custom_Interface | HIGH |
| + 5 LMB/BRAM/Memory IPs | | | HIGH |

### PROJECT-B Bileşenleri (14 node)

| Node ID | İsim | Tip | Güven |
|---------|------|-----|-------|
| COMP-B-microblaze_0 | MicroBlaze v11.0 | IP_Core | HIGH |
| COMP-B-axi_gpio_0 | AXI GPIO v2.0 | IP_Core | HIGH |
| COMP-B-clk_wiz_0 | Clocking Wizard v6.0 | IP_Core | HIGH |
| COMP-B-rst_clk_wiz_0_100M | proc_sys_reset v5.0 | IP_Core | HIGH |
| COMP-B-mdm_1 | MDM v3.2 (UART) | IP_Core | HIGH |
| COMP-B-microblaze_0_axi_periph | AXI Interconnect | IP_Core | HIGH |
| COMP-B-axi_gpio_wrapper | axi_gpio_wrapper | RTL_Module | HIGH |
| + 6 LMB/BRAM/Memory IPs | | | HIGH |

---

## Faz 3: Gereksinim Ağacı

### PROJECT-A Gereksinimleri

```
DMA-REQ-L0-001 (L0): Nexys A7-100T üzerinde DMA tabanlı ses akışı
├── DMA-REQ-L1-001 (L1): DDR2 tabanlı tamponlu ses akışı
│   ├── DMA-REQ-L2-001: FPGA part = xc7a100tcsg324-1
│   ├── DMA-REQ-L2-002: DDR2 kapasitesi ≥ 128 MB, MIG arbitrasyonu
│   ├── DMA-REQ-L2-003: HW tone generator [PARSE_UNCERTAIN_WHY_DISABLED]
│   └── DMA-REQ-L2-004: Dual-clock FIFO CDC
├── DMA-REQ-L1-002 (L1): MicroBlaze firmware + SDK entegrasyonu
│   ├── DMA-REQ-L2-005: DMA scatter-gather modu
│   ├── DMA-REQ-L2-006: WAV 96kHz destekli ses oynatma
│   ├── DMA-REQ-L2-007: UART serial console
│   └── DMA-REQ-L2-008: UART + UART Lite seçimi [PARSE_UNCERTAIN]
├── DMA-REQ-L1-003 (L1): Güç ve saat yönetimi
│   ├── DMA-REQ-L2-008: Saat mimarisi (140.625 + 24.576 MHz)
│   └── DMA-REQ-L2-009: Reset zinciri (MIG-tabanlı)
├── DMA-REQ-L1-004 (L1): Debug
│   └── DMA-REQ-L2-010: JTAG MDM debug
├── DMA-REQ-L1-005 (L1): GPIO
│   └── DMA-REQ-L2-011: AXI GPIO + Interrupt infrastructure
└── DMA-REQ-L1-006 (L1): AXI-Stream signal path
    └── (axis2fifo + fifo2audpwm tüm AXI-S handshake)
```

### PROJECT-B Gereksinimleri

```
AXI-REQ-L0-001 (L0): AXI bus eğitim/validasyon test suite
├── AXI-REQ-L1-001 (L1): GPIO kontrolü — LED/switch I/O
│   └── AXI-REQ-L2-001: GPIO base adresi = 0x40000000
├── AXI-REQ-L1-002 (L1): MicroBlaze soft-core işlemci
│   └── AXI-REQ-L2-002: 8KB LMB BRAM, cache yok
├── AXI-REQ-L1-003 (L1): Saat yönetimi
│   └── AXI-REQ-L2-003: 100 MHz → MMCME2_ADV → fabric
├── AXI-REQ-L1-004 (L1): Reset yönetimi
│   ├── AXI-REQ-L2-004: WNS > 0 ns (synthesis verify)
│   └── AXI-REQ-L2-006: PLL lock → reset release
├── AXI-REQ-L1-005 (L1): AXI-Lite sinyal yolu
│   └── AXI-REQ-L2-005: WNS > 0 ns ile synthesis PASS
└── AXI-REQ-L1-006 (L1): Eğitim metodolojisi (CLI-first TCL)
    └── AXI-REQ-L2-006: 3 seviyeli kademeli ilerleme
```

---

## Faz 4: Eşleştirme Özeti

**Toplam IMPLEMENTS kenarı:** ~80 (M-001 … M-111)
**Toplam CONSTRAINED_BY kenarı:** ~20 (CB-001 … CB-005)
**Uygulanan Stratejiler:** 5/5

| Strateji | Uygulama |
|----------|----------|
| 1. Exact/Fuzzy name | Tüm IP/RTL isim eşleştirmeleri |
| 2. Semantic embedding | tone_generator ↔ HW tone req, audio path ↔ signal req |
| 3. Structural traversal | BD TCL IP listesi → L2 requirement tree traversal |
| 4. Evidence binding | EVID-A-001..015 → ilgili requirement node'ları |
| 5. Constraint binding | XDC pin/timing → COMPONENT → REQUIREMENT |

---

## Faz 5: Özel Analizler (SA-001 … SA-005)

### SA-001: FPGA Part Tutarsızlığı — KRİTİK ONAYLANDI ✅

**Durum:** CONFLICT-A-001 doğrulandı.

| Dosya | Okunan Part | Kart |
|-------|-------------|------|
| project_info.tcl | `xc7a50ticsg324-1L` **(50T)** | Nexys A7-50T |
| design_1.tcl satır 53 | `xc7a50ticsg324-1L` **(50T)** | — |
| XDC dosyası adı | `Nexys-A7-100T-Master.xdc` | 100T |
| README.md | Nexys A7-**100T** | 100T |
| ISTER istenen | `xc7a100tcsg324-1` | 100T |

**Etki:** Sentez ve place-route **50T** hedefiyle yapılıyor. 50T'nin 50K LUT'u 100T'nin 100K LUT'una kıyasla yeterli olabilir (mevcut kullanım düşük) — ancak bit dosyası 100T kartta **çalışmaz** (farklı silikon). Bu kritik bir konfigürasyon hatasıdır.

**Aksiyon:** `project_info.tcl` ve `design_1.tcl`'de part `xc7a100tcsg324-1` olarak düzeltilmeli.

---

### SA-002: tone_generator PARSE_UNCERTAIN Değerlendirmesi ✅

**v2 Mimari Kuralına Göre:** PARSE_UNCERTAIN yalnızca "mühendis rationale'ini belgelememişse" uygulanır — bilinmeyen olgular için değil.

| Soru | Güven | Kaynak |
|------|-------|--------|
| tone_generator çalışıyor mu? | HIGH — HAYIR | README "not currently working" |
| axis_tlast bug var mı? | HIGH — EVET | `assign axis_tlast = 1'b1` (satır 69) |
| Neden düzeltilmedi? | **PARSE_UNCERTAIN** | Mühendis belgesi yok |

**Kararı:** PARSE_UNCERTAIN'ın kapsamı sadece "WHY disabled" sorusuna uygulanır. Fonksiyonel uyumsuzluk ISSUE-A-002 (HIGH, severity=high) olarak ayrı saklanır.

---

### SA-003: Interrupt Altyapısı — DECISION, Coverage Gap Değil ✅

**Sınıflandırma:** **DECISION (DMA-DEC-005)**

| Faktör | Değerlendirme |
|--------|---------------|
| Hardware mevcut mu? | EVET — xlconcat + INTC donanımda var |
| Requirement DMA-REQ-L2-011 | "Interrupt infrastructure donanımı" — SATISFIED (HW) |
| SW kullanıyor mu? | HAYIR — polling |
| Coverage Gap mı? | **HAYIR** — bileşen var, kullanım tercihi belgelenmiş |

**v2 Prensibi:** Coverage Gap = bileşen yok. Burada bileşen var, davranış DMA-DEC-005 (PARSE_UNCERTAIN motivation) ile belgelenmiş. ISSUE-A-006 pratik sonuçları kaydediyor.

---

### SA-004: axi_example Educational Pattern Yeterliliği ✅

**Mevcut 5 Pattern:**

| ID | Pattern | Değer |
|----|---------|-------|
| PAT-B-001 | AXI Tie-Off (Standalone GPIO) | HIGH |
| PAT-B-002 | AXI4-Lite Minimal Master | HIGH |
| PAT-B-003 | MicroBlaze Minimal Config | HIGH |
| PAT-B-004 | 3-Seviye Kademeli Eğitim | HIGH |
| PAT-B-005 | PLL Lock → Reset Release | HIGH |

**Verdict:** Mevcut 5 pattern eğitimsel olarak yeterli.

**Önerilen 2 Ek Pattern:**

| ID | Pattern | Kaynak |
|----|---------|--------|
| PAT-B-006 (önerilen) | AXI Address Map Explicit Assignment (`assign_bd_address`) | `add_axi_gpio.tcl` |
| PAT-B-007 (önerilen) | Out-of-Context Synthesis Modu | `run_synthesis.tcl` + SYNTHESIS_RESULTS.md |

---

### SA-005: Signal Path Ekseni Kapsam Analizi ✅

#### PROJECT-A: SUBSTANTIALLY_COVERED

| Signal Path Noktası | Durum | Kanıt |
|---------------------|-------|-------|
| Clock dağıtımı (100→140.625+24.576 MHz) | ✅ COVERED | COMP-A-clk_wiz_0 |
| Reset zinciri (MIG sync_rst → periph_aresetn) | ✅ COVERED | COMP-A-rst_mig_7series_0_81M |
| AXI-Stream handshake (tvalid/tready/tlast) | ✅ COVERED | COMP-A-axis2fifo_0 |
| FIFO CDC gray-code pointer sync | ✅ COVERED | COMP-A-fifo_generator_0 |
| FIFO backpressure (full→tready, empty→aud_en) | ✅ COVERED | EVID-A-006, EVID-A-007 |
| Interrupt routing (HW) | ✅ COVERED_HW_ONLY | DMA-DEC-005 |
| Timing doğrulama (WNS) | ❌ NOT_COVERED | Implementation çalıştırılmamış |

#### PROJECT-B: WELL_COVERED

| Signal Path Noktası | Durum | Kanıt |
|---------------------|-------|-------|
| Clock dağıtımı (100 MHz → MMCME2_ADV → BUFG) | ✅ COVERED | EVID-B-001 |
| Reset zinciri (PLL locked → proc_sys_reset) | ✅ COVERED | COMP-B-rst_clk_wiz_0_100M |
| AXI-Lite handshake (master → periph → slave) | ✅ COVERED | COMP-B-microblaze_0_axi_periph |
| AXI tie-off pattern (standalone) | ✅ COVERED | PAT-B-001, EVID-B-002 |
| GPIO output path (register → LED pin) | ✅ COVERED | CONST-B-PIN-LED0..7 |
| Timing doğrulama (WNS > 0) | ✅ COVERED | EVID-B-001 (synthesis confirmed) |
| Interrupt path | — NOT_PRESENT | Kapsam dışı (eğitim tasarımı) |

---

## Faz 5: Coverage Gap Raporu

| Gap ID | Proje | Severity | Açıklama |
|--------|-------|----------|----------|
| GAP-A-001 | PROJECT-A | **high** | tone_generator bileşen var ama fonksiyonel değil (axis_tlast bug + bit genişliği uyumsuzluğu). DMA-REQ-L2-003 karşılanmıyor. |
| GAP-B-001 | PROJECT-B | info | Seviye 3 örnek (tam sistem) henüz tamamlanmamış (README'de ⏳). |

---

## Faz 5: Orphan Component Raporu

| Orphan ID | Proje | Bileşen | Formal Orphan? |
|-----------|-------|---------|----------------|
| ORP-A-001 | PROJECT-A | xlconcat_0 (DMA interrupt concat) | **HAYIR** — DMA-DEC-005 kapsamında |
| ORP-A-002 | PROJECT-A | xlconcat_1 (GPIO+UART interrupt) | **HAYIR** — DMA-DEC-005 kapsamında |

---

## Faz 5: Issue Listesi

### PROJECT-A Issues

| ID | Severity | Başlık |
|----|----------|--------|
| ISSUE-A-001 | **critical** | FPGA part tutarsızlığı: TCL=50T, kart=100T |
| ISSUE-A-002 | **high** | tone_generator fonksiyonel değil (axis_tlast=1 bug) |
| ISSUE-A-003 | **medium** | axis2fifo: 32→16 bit truncation, üst 16-bit kaybolur |
| ISSUE-A-004 | **medium** | XDC'de yalnızca PWM pinleri aktif; diğerleri commented-out |
| ISSUE-A-005 | **low** | WAV yalnızca 96 kHz destekliyor (örnekleme hızı kısıtı) |
| ISSUE-A-006 | **info** | Interrupt infrastructure donanımda var, SW polling kullanıyor |
| ISSUE-A-007 | **info** | Timing raporu yok (implementation çalıştırılmamış) |

### PROJECT-B Issues

| ID | Severity | Başlık |
|----|----------|--------|
| ISSUE-B-001 | **info** | 3 Critical Warning (duplicate clock, UART ports, LMB clock mismatch) |
| ISSUE-B-002 | **info** | Sentez yalnızca Seviye 2'yi kapsıyor (Seviye 3 tamamlanmamış) |
| ISSUE-B-003 | **medium** | Block automation timeout — create_axi_auto.tcl stabil değil |

---

## Faz 5: Çapraz Proje Kenarları (ANALOGOUS_TO)

| Edge | From | To | Açıklama |
|------|------|----|----------|
| XP-001 | COMP-A-clk_wiz_0 | COMP-B-clk_wiz_0 | Her iki proje Clocking Wizard v6.0 kullanıyor |
| XP-002 | COMP-A-rst_mig_7series_0_81M | COMP-B-rst_clk_wiz_0_100M | Her iki proje proc_sys_reset v5.0 kullanıyor |
| XP-003 | COMP-A-mdm_1 | COMP-B-mdm_1 | Her ikisi MDM v3.2, PROJECT-B UART ekliyor |
| XP-004 | COMP-A-microblaze_0 | COMP-B-microblaze_0 | Her ikisi MicroBlaze (v10 vs v11, cache/no-cache) |
| XP-005 | PAT-B-005 | PAT-A-004 | PLL Lock→Reset Release pattern yeniden kullanımı |
| XP-006 | COMP-A-GPIO_IN | COMP-B-axi_gpio_0 | Her ikisi AXI GPIO IP, farklı konfigürasyonlar |

---

## Faz 6: ISTER Dokümanı Güncellemeleri (v2.0 → v2.1)

| ID | Bölüm | Tip | Açıklama |
|----|-------|-----|----------|
| UPD-001 | PROJECT-A Metadata / FPGA Part | CORRECTION | `fpga_part_actual_tcl: xc7a50ticsg324-1L` ve `fpga_part_intended: xc7a100tcsg324-1` ayrımı netleştirildi. ISSUE-A-001 severity=critical doğrulandı. |
| UPD-002 | DMA-REQ-L2-003 / PARSE_UNCERTAIN kapsamı | CLARIFICATION | PARSE_UNCERTAIN yalnızca "WHY disabled" için. "Çalışmıyor" gerçeği HIGH confidence. parse_flag → `PARSE_UNCERTAIN_WHY_DISABLED`. |
| UPD-003 | DMA-DEC-005 / Interrupt sınıflandırma | CLASSIFICATION_CONFIRMED | DECISION (bileşen var, kullanım tercihi). Rationale eklendi. |
| UPD-004 | Section 5.4 PROJECT-B Patterns | ADDITION | PAT-B-006 (AXI Address Map) ve PAT-B-007 (OOC Synthesis) eklendi. |
| UPD-005 | Signal Path ekseni analizi | ADDITION | SA-005 bulguları — PROJECT-A timing evidence eksik, PROJECT-B WNS doğrulandı. |
| UPD-006 | SOURCE_DOC paths | CORRECTION | Windows pathler Linux pathlerle normalize edildi (`/home/test123/...`). |

---

## Çıktı Dosyaları

| Dosya | Konum | Açıklama |
|-------|-------|----------|
| `pipeline_graph.json` | `data/fpga_rag_v2_output/` | Tam 6-faz pipeline çıktısı (119 KB, 2255 satır) |
| `pipeline_report.md` | `data/fpga_rag_v2_output/` | Bu rapor — insan okunabilir özet |

---

*FPGA RAG v2 Pipeline — LLM yalnızca ayrıştırır, eşleştirir ve sunar. Rationale üretmez.*
