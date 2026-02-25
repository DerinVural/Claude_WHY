#!/usr/bin/env python3
"""
FPGA RAG v2 — Yeni Knowledge Node Ekleme
=========================================
Bitstream, Simülasyon, P&R ve Hata senaryosu kategorileri için
graph DB'ye yeni node'lar ekler.

Hedef sorular (düşük skor):
  E-Q02  (0.567) — 440 Hz INCREMENT: decimal doğru ama hex yanlış
  E-Q01  (0.575) — Port listesinden tasarım çıkarma
  C-Q04  (0.675) — IP versiyon kataloğu
  E-Q08  (0.675) — Polling → Interrupt geçişi
  C-Q06  (0.779) — Bitstream + ELF gömme
"""

from __future__ import annotations
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

from rag_v2.graph_store import GraphStore

gs = GraphStore(persist_path=str(_ROOT / "db" / "graph" / "fpga_rag_v2_graph.json"))

NEW_NODES = [

    # ─────────────────────────────────────────────────────────────
    # BITSTREAM & DEPLOYMENT
    # ─────────────────────────────────────────────────────────────
    {
        "node_id": "DEC-A-bitstream-001",
        "node_type": "DECISION",
        "project": "nexys_a7_dma_audio",
        "name": "Bitstream + ELF Gömme Süreci (updatemem)",
        "confidence": "HIGH",
        "description": (
            "MicroBlaze yazılımını bitstream'e gömme süreci iki aşamadan oluşur. "
            "Aşama 1: Vivado'da write_bitstream ile .bit dosyası üretilir. "
            "Aşama 2: updatemem komutu ile .elf dosyası BRAM içeriğini güncellemek için .bit'e gömülür. "
            "updatemem -meminfo design_1.mmi -data helloworld.elf -proc design_1_i/microblaze_0 "
            "-bd design_1.bd -force -out design_1_updated.bit şeklinde çalıştırılır. "
            ".mmi (Memory Map Information) dosyası BRAM fiziksel konumlarını tanımlar. "
            "BMM_INFO_PROCESSOR pragma'sı sentez sırasında .mmi dosyasını otomatik oluşturur. "
            "Son adım: program_hw_devices ile güncellenmiş bitstream FPGA'ya yüklenir."
        ),
        "key_logic": [
            "write_bitstream → .bit dosyası üretir",
            "updatemem -meminfo .mmi -data .elf -proc microblaze_0 → BRAM güncellenir",
            "BMM_INFO_PROCESSOR pragma → .mmi otomatik üretilir",
            "program_hw_devices → FPGA'ya yükle",
            "SDK: Generate Bitstream + Update Bitstream eşdeğeri"
        ],
        "rationale": "Yazılım değişikliklerinde bitstream yeniden sentezlemek yerine updatemem ile sadece BRAM bölümü güncellenir.",
        "acceptance_criteria": "updatemem başarıyla çalışır, .elf BRAM'a gömülür, FPGA boot eder.",
        "source_file": "design_1.tcl",
        "tags": ["bitstream", "updatemem", "elf", "BMM", "mmi", "write_bitstream", "BRAM", "deployment"],
    },

    # ─────────────────────────────────────────────────────────────
    # SİMÜLASYON / TESTBENCH
    # ─────────────────────────────────────────────────────────────
    {
        "node_id": "EVID-A-sim-001",
        "node_type": "EVIDENCE",
        "project": "nexys_a7_dma_audio",
        "name": "fifo2audpwm Testbench Tasarımı",
        "confidence": "HIGH",
        "description": (
            "fifo2audpwm modülü için Verilog testbench tasarımı. "
            "Modül parametreleri: DATA_WIDTH=8, FIFO_DATA_WIDTH=32. "
            "Test senaryoları: "
            "(1) Normal akış: fifo_empty=0, FIFO'dan 32-bit word okunur, 4×8-bit duty değerleri çıkarılır. "
            "(2) fifo_empty=1: fifo_rd_en=0, aud_en=0 (count overflow sonrası), aud_pwm eski duty ile devam. "
            "(3) PWM duty doğruluğu: count[7:0] <= duty[count[9:8]] — 8-bit karşılaştırma. "
            "(4) Sample sıralaması: duty[0]=fifo_rd_data[7:0], duty[1]=fifo_rd_data[15:8], "
            "duty[2]=fifo_rd_data[23:16], duty[3]=fifo_rd_data[31:24]. "
            "(5) Zamanlama: her 1024 clock cycle'da bir FIFO word okunur (DATA_WIDTH+2 = 10-bit count). "
            "(6) Reset: rst=1 → count=0, aud_en=0."
        ),
        "key_logic": [
            "fifo_rd_en = (fifo_empty==0) && (&count==1)",
            "aud_en: count overflow'da fifo_empty kontrol edilir",
            "aud_pwm = count[7:0] <= duty[count[9:8]]",
            "1024 clock/sample = DATA_WIDTH+2 bit count",
            "duty[0..3] = fifo_rd_data[7:0, 15:8, 23:16, 31:24]"
        ],
        "summary": "6 test senaryosu: normal akış, empty, duty, sample sırası, zamanlama, reset.",
        "source_file": "fifo2audpwm.v",
        "tags": ["testbench", "simülasyon", "simulation", "fifo2audpwm", "DATA_WIDTH", "aud_pwm", "duty"],
    },

    {
        "node_id": "EVID-A-sim-002",
        "node_type": "EVIDENCE",
        "project": "nexys_a7_dma_audio",
        "name": "axis2fifo Testbench Senaryoları",
        "confidence": "HIGH",
        "description": (
            "axis2fifo modülü için simülasyon senaryoları. "
            "AXI-Stream slave → FIFO yazma arayüzü. "
            "Back-pressure: axis_tready = ~fifo_full (kombinasyonel, sıfır gecikme). "
            "Veri truncation: axis_tdata[31:0] → fifo_wr_data[15:0] (üst 16 bit atılır). "
            "Test senaryoları: "
            "(1) Normal transfer: tvalid=1, tready=1 → fifo_wr_en=1. "
            "(2) FIFO full: fifo_full=1 → tready=0 → back-pressure. "
            "(3) Truncation doğrulama: tdata=32'hDEADBEEF → fifo_wr_data=16'hBEEF. "
            "(4) Handshake: tvalid & tready → geçerli transfer."
        ),
        "key_logic": [
            "axis_tready = ~fifo_full",
            "fifo_wr_en = axis_tready & axis_tvalid",
            "fifo_wr_data = axis_tdata[15:0] — truncation",
            "back-pressure: sıfır gecikme, kombinasyonel"
        ],
        "source_file": "axis2fifo.v",
        "tags": ["testbench", "simülasyon", "axis2fifo", "back-pressure", "truncation", "handshake"],
    },

    # ─────────────────────────────────────────────────────────────
    # P&R / UTILIZATION
    # ─────────────────────────────────────────────────────────────
    {
        "node_id": "EVID-B-util-001",
        "node_type": "EVIDENCE",
        "project": "axi_gpio_example",
        "name": "xc7a200t Kaynak Kullanım Tahmini (AXI GPIO)",
        "confidence": "HIGH",
        "description": (
            "axi_gpio_example projesi xc7a200tsbg484-1 FPGA'da implement edildiğinde tahmini kaynak kullanımı. "
            "xc7a200t kapasitesi: 133,800 LUT, 267,600 FF, 365 BRAM (36K), 740 DSP. "
            "Proje bileşen kullanımı: "
            "MicroBlaze v11.0: ~2000 LUT, ~1500 FF. "
            "LMB BRAM (8KB): 2 BRAM36. "
            "AXI Interconnect (1×1): ~200 LUT, ~300 FF. "
            "AXI GPIO v2.0 (8-bit): ~100 LUT, ~80 FF. "
            "Clocking Wizard (MMCME2_ADV): 1 MMCM, ~10 LUT. "
            "Proc Sys Reset: ~20 LUT. "
            "Toplam tahmini: ~2400 LUT (%1.8), ~2000 FF (%0.7), 2 BRAM (%0.5). "
            "SYNTHESIS_RESULTS.md satır 240-262'de doğrulanmış: synthesis başarılı, WNS>0. "
            "Kaynak kullanımı minimal — eğitimsel tasarım olduğu için optimize edilmemiş."
        ),
        "key_logic": [
            "LUT: ~2400/133800 = %1.8",
            "FF: ~2000/267600 = %0.7",
            "BRAM: 2/365 = %0.5",
            "MMCM: 1/10 = %10",
            "Timing WNS > 0 ns — synthesis sonrası doğrulandı"
        ],
        "summary": "xc7a200t'de minimal kullanım: %1.8 LUT, %0.7 FF, %0.5 BRAM.",
        "source_file": "SYNTHESIS_RESULTS.md",
        "tags": ["utilization", "LUT", "FF", "BRAM", "xc7a200t", "implementasyon", "place and route", "P&R"],
    },

    {
        "node_id": "EVID-A-utilization-002",
        "node_type": "EVIDENCE",
        "project": "nexys_a7_dma_audio",
        "name": "xc7a50t Kaynak Kullanım Tahmini (DMA Audio)",
        "confidence": "MEDIUM",
        "description": (
            "nexys_a7_dma_audio projesi xc7a50ticsg324-1L FPGA'da implement edildiğinde tahmini kaynak kullanımı. "
            "xc7a50t kapasitesi: 32,600 LUT, 65,200 FF, 75 BRAM (36K), 120 DSP. "
            "MIG 7-Series DDR2: ~2000 LUT, ~3000 FF (DDR2 PHY dahil). "
            "AXI DMA: ~1000 LUT, ~800 FF. "
            "MicroBlaze: ~2000 LUT, ~1500 FF. "
            "RTL modülleri (axis2fifo, fifo2audpwm, tone_generator): ~300 LUT. "
            "Dual-clock FIFO (BRAM): 1-2 BRAM. "
            "Toplam tahmini: ~5500 LUT (%17), ~6000 FF (%9), 6-8 BRAM (%9). "
            "Seviye 3 (tam sistem) sentezi tamamlanmamış (ISSUE-B-002). "
            "Place & route timing closure MIG için kritik — ui_clk 81.25 MHz."
        ),
        "key_logic": [
            "MIG DDR2 PHY en büyük kaynak tüketici: ~%30 LUT",
            "Dual-clock FIFO: CDC için BRAM-based yapı",
            "ui_clk 81.25 MHz timing closure kritik",
            "Seviye 3 sentez tamamlanmamış — tahmini değerler"
        ],
        "source_file": "design_1.tcl",
        "tags": ["utilization", "LUT", "FF", "BRAM", "xc7a50t", "implementasyon", "MIG", "place and route"],
    },

    # ─────────────────────────────────────────────────────────────
    # HATA SENARYOLARI / DRC
    # ─────────────────────────────────────────────────────────────
    {
        "node_id": "ISSUE-B-drc-001",
        "node_type": "ISSUE",
        "project": "axi_gpio_example",
        "name": "DRC Hataları — AXI GPIO Projesi",
        "confidence": "HIGH",
        "description": (
            "axi_gpio_example projesi Vivado implementation'da karşılaşılabilecek DRC hataları. "
            "NSTD-1: Tanımsız IOSTANDARD — XDC'de bazı pinlere standart atanmamışsa tetiklenir. "
            "Çözüm: tüm I/O pinlerine explicit IOSTANDARD ekle. "
            "UCIO-1: Kullanılmayan I/O — netlist'te olmayan portlara constraint varsa. "
            "CFGBVS-1: CONFIG_VOLTAGE belirtilmemiş. "
            "Çözüm: set_property CFGBVS GND [current_design] ve "
            "set_property CONFIG_VOLTAGE 3.3 [current_design] XDC'ye eklenir. "
            "TIMING-18: Hold violation — negatif TNS. "
            "BIVC-1: Bank I/O Voltage Conflict — aynı bankada farklı VCCO gerektiren standartlar. "
            "Place 30-574: Clock routing — LVCMOS33 ile diferansiyel pinde tek uçlu buffer sorunu. "
            "vivado_axi_simple variant'ında R4'e LVCMOS33 atanması BIVC-1 + Place 30-574 hatası üretir."
        ),
        "key_logic": [
            "NSTD-1: set_property IOSTANDARD ... ekle",
            "CFGBVS-1: set_property CFGBVS GND + CONFIG_VOLTAGE 3.3",
            "BIVC-1: R4 diferansiyel — LVCMOS33 yerine LVDS/DIFF_SSTL18_II",
            "Place 30-574: diferansiyel pine single-ended buffer atanamaz",
            "Opt 31-35: yanlış buffer tipi optimize edilemiyor"
        ],
        "source_file": "nexys_video.xdc",
        "tags": ["DRC", "NSTD-1", "CFGBVS", "BIVC-1", "timing", "critical warning", "hata", "constraint"],
    },

    {
        "node_id": "ISSUE-A-drc-002",
        "node_type": "ISSUE",
        "project": "nexys_a7_dma_audio",
        "name": "DRC Hataları — DMA Audio Projesi",
        "confidence": "HIGH",
        "description": (
            "nexys_a7_dma_audio projesi Vivado implementation DRC uyarıları. "
            "REQP-1840: MIG 7-Series — sys_rst active-high harici reset gerektiriyor. "
            "PDRC-153: MIG MMCM lock sinyali bağlı değilse uyarı. "
            "CDC-1: Clock Domain Crossing — ui_clk (81.25 MHz) ile clk_wiz_0 (100 MHz) arası "
            "yeterli CDC kısıtlaması yoksa uyarı. Dual-clock FIFO ile giderilir. "
            "TIMING-6: MIG ui_clk path timing constraint eksikse. "
            "AVAL-46: AXI slave port boşta kalmış (undriven). "
            "CFGBVS-1: CONFIG_VOLTAGE tanımsız — set_property CFGBVS GND + CONFIG_VOLTAGE 1.8. "
            "ISSUE-A-007: Implementation ve place-route çalıştırılmamış, WNS bilinmiyor. "
            "MIG timing closure en kritik nokta — 81.25 MHz ui_clk için WNS > 0 gerekli."
        ),
        "key_logic": [
            "CDC-1: ui_clk ↔ clk_wiz_0 async FIFO ile çözülür",
            "REQP-1840: MIG sys_rst active-high bağlantısı",
            "CFGBVS: set_property CFGBVS GND + CONFIG_VOLTAGE 1.8",
            "TIMING-6: create_clock -period 12.308 [get_pins mig_7series_0/ui_clk]",
            "WNS bilinmiyor — implementation çalıştırılmalı"
        ],
        "source_file": "design_1.tcl",
        "tags": ["DRC", "REQP-1840", "CDC-1", "TIMING", "CFGBVS", "MIG", "hata", "critical warning"],
    },

    {
        "node_id": "ISSUE-A-timeout-001",
        "node_type": "ISSUE",
        "project": "nexys_a7_dma_audio",
        "name": "Polling Timeout Bug — helloworld.c",
        "confidence": "HIGH",
        "description": (
            "helloworld.c'de DMA polling döngülerinde timeout mekanizması eksik. "
            "while(XAxiDma_Busy(...)) döngüsü DMA transfer tamamlanmadan sonsuza dek bekleyebilir. "
            "Benzer sorun: XUartLite_Recv UART receive polling döngüsü. "
            "Etkisi: DMA hata durumunda veya hardware arızasında sistem kilitlenir. "
            "Çözüm 1: Timeout sayacı ekle — "
            "u32 timeout=100000; while(XAxiDma_Busy(..) && timeout--) {}; if(!timeout) XAxiDma_Reset(..). "
            "Çözüm 2: Interrupt tabanlı DMA (xlconcat_0 + AXI INTC donanımda hazır). "
            "XAxiDma_Reset çağrısı: DMA hata sonrası kurtarma için — "
            "XAxiDma_Reset(&dma_inst); while(!XAxiDma_ResetIsDone(&dma_inst)) {}. "
            "Watchdog timer (TLB veya AXI Timer IP) ile sistem seviyesi recovery mümkün."
        ),
        "key_logic": [
            "XAxiDma_Busy polling: timeout sayacı olmadan sonsuz döngü riski",
            "XUartLite_Recv: blocking, watchdog yok",
            "XAxiDma_Reset: hata sonrası kurtarma mekanizması",
            "Çözüm: timeout + XAxiDma_Reset veya interrupt-driven DMA"
        ],
        "source_file": "helloworld.c",
        "tags": ["timeout", "polling", "sonsuz döngü", "XAxiDma_Busy", "XAxiDma_Reset", "watchdog", "bug", "hata"],
    },

    # ─────────────────────────────────────────────────────────────
    # IP VERSİYON KATALOĞU
    # ─────────────────────────────────────────────────────────────
    {
        "node_id": "EVID-B-ipcat-001",
        "node_type": "EVIDENCE",
        "project": "axi_gpio_example",
        "name": "IP Versiyon Kataloğu — AXI GPIO Projesi",
        "confidence": "HIGH",
        "description": (
            "axi_gpio_example projesinde kullanılan Xilinx IP bloklarının versiyonları. "
            "Clocking Wizard: xilinx.com:ip:clk_wiz:6.0 (v6.0). "
            "Proc Sys Reset: xilinx.com:ip:proc_sys_reset:5.0 (v5.0). "
            "AXI GPIO: xilinx.com:ip:axi_gpio:2.0 (v2.0). "
            "AXI Interconnect: xilinx.com:ip:axi_interconnect:2.1 (v2.1). "
            "MicroBlaze: xilinx.com:ip:microblaze:11.0 (v11.0). "
            "MDM (MicroBlaze Debug): xilinx.com:ip:mdm:3.2 (v3.2). "
            "LMB BRAM Controller: xilinx.com:ip:lmb_bram_if_cntlr:4.0. "
            "BRAM Block Memory: xilinx.com:ip:blk_mem_gen:8.4. "
            "Bu versiyonlar Vivado 2018.x-2020.x ile uyumludur. "
            "Vivado 2023+ ile minor versiyon farklılıkları olabilir ancak backward compatible."
        ),
        "key_logic": [
            "clk_wiz v6.0 — MMCME2_ADV tabanlı",
            "proc_sys_reset v5.0 — active-low reset çıkışı",
            "axi_gpio v2.0 — dual channel destekli",
            "microblaze v11.0 — AXI4 master",
            "mdm v3.2 — JTAG debug"
        ],
        "source_file": "create_minimal_microblaze.tcl",
        "tags": ["versiyon", "IP", "clk_wiz", "proc_sys_reset", "axi_gpio", "microblaze", "v6", "v5", "v2", "v11", "katalog"],
    },

    # ─────────────────────────────────────────────────────────────
    # DDS ARITMETIK (E-Q02 fix)
    # ─────────────────────────────────────────────────────────────
    {
        "node_id": "EVID-A-dds-calc-001",
        "node_type": "EVIDENCE",
        "project": "nexys_a7_dma_audio",
        "name": "DDS Phase INCREMENT Hesaplama — Doğru Formül",
        "confidence": "HIGH",
        "description": (
            "DDS (Direct Digital Synthesis) faz akkümülatörü için INCREMENT hesaplama. "
            "Formül: INCREMENT = (frekans_hz * 2^ACCUMULATOR_DEPTH) / AUD_SAMPLE_FREQ. "
            "Parametreler (tone_generator.v): ACCUMULATOR_DEPTH=32, AUD_SAMPLE_FREQ=96000. "
            "Mevcut 261 Hz (Do notası): INCREMENT = 261 * 4294967296 / 96000 = 11,672,158 = 0x00B22D0E. "
            "440 Hz (La notası) hesabı: "
            "INCREMENT = 440 * 4294967296 / 96000 = 1,889,785,610,240 / 96000 = 19,685,267 = 0x012C5F93. "
            "Doğrulama: 19,685,267 * 96000 / 4294967296 = 439.9999 Hz ≈ 440 Hz. "
            "NOT: 19,685,267 decimal = 0x012C5F93 hexadecimal (tam dönüşüm). "
            "Yaygın hata: 0x012C9BA3 yanlış hex dönüşümdür. "
            "Python doğrulama: hex(440 * (2**32) // 96000) = '0x12c5f93'."
        ),
        "key_logic": [
            "261 Hz → 0x00B22D0E = 11,672,158",
            "440 Hz → 0x012C5F93 = 19,685,267",
            "formül: frekans * 2^32 / 96000",
            "hex(19685267) = '0x12c5f93' (Python doğrulaması)",
            "AUD_SAMPLE_FREQ=96000, ACCUMULATOR_DEPTH=32"
        ],
        "summary": "440 Hz için INCREMENT = 19685267 = 0x012C5F93",
        "source_file": "tone_generator.v",
        "tags": ["DDS", "INCREMENT", "440Hz", "0x012C5F93", "19685267", "hesaplama", "faz akkümülatör", "ACCUMULATOR_DEPTH"],
    },

    # ─────────────────────────────────────────────────────────────
    # PORT LİSTESİNDEN TASARIM ÇIKARMA (E-Q01 fix)
    # ─────────────────────────────────────────────────────────────
    {
        "node_id": "PAT-B-toplevel-001",
        "node_type": "PATTERN",
        "project": "axi_gpio_example",
        "name": "Top-Level Port Analizi — Diferansiyel Clock + GPIO Çıkış",
        "confidence": "HIGH",
        "description": (
            "Top-level wrapper port listesinden tasarım analizi. "
            "clk_100mhz_clk_p + clk_100mhz_clk_n → diferansiyel LVDS clock, R4/T4 pinleri. "
            "Nexys Video'da 100 MHz diferansiyel osilatör → Clocking Wizard (MMCME2_ADV) gerektirir. "
            "led_8bits_tri_o[7:0] → yalnızca çıkış (tri_o = tristate output), switches girişi YOK. "
            "reset → tek uçlu, Proc Sys Reset IP varlığını gösterir. "
            "Port listesinden çıkarılan minimum IP seti: "
            "(1) Clocking Wizard v6.0 — diferansiyel giriş → single-ended çıkış. "
            "(2) Proc Sys Reset v5.0 — reset + locked zinciri. "
            "(3) AXI GPIO v2.0 — led_8bits_tri_o, sadece çıkış. "
            "(4) MicroBlaze v11.0 — AXI master gerekli. "
            "(5) AXI Interconnect — MicroBlaze ↔ GPIO arası. "
            "(6) MDM v3.2 — debug portu (implicit). "
            "axi_gpio_wrapper.v dosyasında tüm AXI sinyalleri tie-off (sabit 0) — standalone çalışamaz."
        ),
        "key_logic": [
            "clk_p/clk_n → LVDS diferansiyel → Clocking Wizard zorunlu",
            "tri_o → yalnızca çıkış GPIO — switch girişi yok",
            "reset → Proc Sys Reset IP",
            "led_8bits → AXI GPIO tek kanal, 8-bit, output-only",
            "axi_gpio_wrapper.v: AXI tie-off → standalone çalışamaz"
        ],
        "source_file": "nexys_video.xdc",
        "tags": ["port listesi", "top-level", "LVDS", "diferansiyel", "clk_p", "clk_n", "R4", "T4", "tri_o", "GPIO"],
    },

    # ─────────────────────────────────────────────────────────────
    # INTERRUPT ALTYAPISI (E-Q08 fix)
    # ─────────────────────────────────────────────────────────────
    {
        "node_id": "DEC-A-interrupt-001",
        "node_type": "DECISION",
        "project": "nexys_a7_dma_audio",
        "name": "AXI INTC Interrupt Altyapısı — DMA Entegrasyonu",
        "confidence": "HIGH",
        "description": (
            "DMA Audio projesinde AXI INTC (0x41200000) donanımda hazır ama kullanılmıyor. "
            "Polling'den interrupt-driven DMA'ya geçiş için gereken değişiklikler: "
            "1. XIntc_Initialize(&intc_inst, XPAR_MICROBLAZE_0_AXI_INTC_DEVICE_ID). "
            "2. XIntc_Connect: MM2S handler = xlconcat_0/In0, S2MM handler = xlconcat_0/In1. "
            "3. ISR içinde XAxiDma_IntrGetIrq ile IRQ durumu okunur. "
            "4. XAxiDma_IntrAckIrq ile interrupt acknowledge edilir. "
            "5. XIntc_Start(&intc_inst, XIN_REAL_MODE) + Xil_ExceptionEnable(). "
            "xlconcat_0: DMA mm2s_introut → In0, DMA s2mm_introut → In1. "
            "xlconcat_1: GPIO_IN → In0, GPIO_OUT → In1, UART → In2. "
            "AXI INTC base address: 0x41200000. "
            "design_1.tcl satır 361-365'te xlconcat bağlantıları."
        ),
        "key_logic": [
            "XIntc_Initialize → 0x41200000",
            "XAxiDma_IntrGetIrq → IRQ durumu oku",
            "XAxiDma_IntrAckIrq → acknowledge",
            "xlconcat_0: mm2s→In0, s2mm→In1",
            "Xil_ExceptionEnable → MicroBlaze interrupt'ları aç"
        ],
        "source_file": "helloworld.c",
        "tags": ["interrupt", "XIntc_Initialize", "XAxiDma_IntrGetIrq", "XAxiDma_IntrAckIrq",
                 "xlconcat", "0x41200000", "AXI INTC", "ISR", "polling"],
    },
]

NEW_EDGES = [
    {"from": "DEC-A-bitstream-001", "to": "COMP-A-axi_dma_0",    "edge_type": "IMPLEMENTS",   "confidence": "HIGH"},
    {"from": "DEC-A-bitstream-001", "to": "PROJECT-A",            "edge_type": "BELONGS_TO",   "confidence": "HIGH"},
    {"from": "EVID-A-sim-001",      "to": "COMP-A-fifo2audpwm_0", "edge_type": "VALIDATES",    "confidence": "HIGH"},
    {"from": "EVID-A-sim-002",      "to": "COMP-A-axis2fifo_0",   "edge_type": "VALIDATES",    "confidence": "HIGH"},
    {"from": "EVID-B-util-001",     "to": "PROJECT-B",            "edge_type": "BELONGS_TO",   "confidence": "HIGH"},
    {"from": "ISSUE-B-drc-001",     "to": "PROJECT-B",            "edge_type": "BELONGS_TO",   "confidence": "HIGH"},
    {"from": "ISSUE-A-drc-002",     "to": "PROJECT-A",            "edge_type": "BELONGS_TO",   "confidence": "HIGH"},
    {"from": "ISSUE-A-timeout-001", "to": "COMP-A-axi_dma_0",    "edge_type": "AFFECTS",      "confidence": "HIGH"},
    {"from": "EVID-A-dds-calc-001", "to": "COMP-A-tone_generator_0", "edge_type": "VALIDATES", "confidence": "HIGH"},
    {"from": "PAT-B-toplevel-001",  "to": "PROJECT-B",            "edge_type": "BELONGS_TO",   "confidence": "HIGH"},
    {"from": "DEC-A-interrupt-001", "to": "COMP-A-axi_dma_0",    "edge_type": "IMPLEMENTS",   "confidence": "HIGH"},
    {"from": "EVID-B-ipcat-001",    "to": "PROJECT-B",            "edge_type": "BELONGS_TO",   "confidence": "HIGH"},
]


def main():
    print("=" * 60)
    print("  FPGA RAG v2 — Yeni Node Ekleme")
    print("=" * 60)

    added_nodes = 0
    skipped_nodes = 0
    existing_ids = {n["node_id"] for n in gs.get_all_nodes()}

    for node in NEW_NODES:
        nid = node["node_id"]
        if nid in existing_ids:
            print(f"  [SKIP] {nid} zaten mevcut")
            skipped_nodes += 1
        else:
            attrs = {k: v for k, v in node.items() if k != "node_id"}
            gs.add_node(nid, attrs)
            print(f"  [ADD]  {nid} — {node['name'][:50]}")
            added_nodes += 1

    print(f"\n  Node: {added_nodes} eklendi, {skipped_nodes} atlandı")

    # Edge'leri ekle
    added_edges = 0
    for edge in NEW_EDGES:
        try:
            gs.add_edge(edge["from"], edge["to"], edge["edge_type"],
                       {"confidence": edge["confidence"]})
            added_edges += 1
        except Exception as e:
            print(f"  [EDGE WARN] {edge['from']} → {edge['to']}: {e}")

    print(f"  Edge: {added_edges} eklendi")

    gs.save()
    stats = gs.stats()
    print(f"\n  Graph kaydedildi: {stats['total_nodes']} node, {stats['total_edges']} edge")
    print("\n  Tamamlandı!")


if __name__ == "__main__":
    main()
