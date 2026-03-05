# IP Konfigürasyon Tablosu — PROJECT-A & PROJECT-B

**Kaynak:** FPGA RAG v2 Graph Store + design_1.tcl / build script'ler doğrulaması
**Tarih:** 2026-03-02 (güncellendi)

---

## PROJECT-A — Nexys A7-100T DMA Audio

| IP / Modül | Versiyon | Temel Parametreler |
|---|---|---|
| **MicroBlaze** | v10.0 | C_USE_DCACHE=1, C_USE_ICACHE=1, C_DCACHE_ADDR_TAG=14, C_DEBUG_ENABLED=1, C_D_AXI=1, LMB arayüzü |
| **AXI DMA** | 7.1 | c_include_sg=0 (SG kapalı), c_mm2s_burst_size=256, c_s2mm_burst_size=256, c_include_mm2s_dre=1, c_include_s2mm_dre=1, c_sg_length_width=24 |
| **FIFO Generator** | v13.2 | Fifo_Implementation=Independent_Clocks_Block_RAM, Input_Depth=4096, Output_Depth=4096, Input_Data_Width=32, Full_Threshold_Assert_Value=4093, Full_Threshold_Negate_Value=4092, Reset_Pin=false |
| **MIG 7-Series** | v4.1 | BOARD_MIG_PARAM=ddr2_sdram, XML_INPUT_FILE=mig_b.prj, sys_clk=140.625 MHz, ui_clk≈81 MHz |
| **Clocking Wizard** | v6.0 | NUM_OUT_CLKS=2, CLKOUT1=140.625 MHz (MIG), CLKOUT2=24.576 MHz (PWM ses), MMCM_CLKFBOUT_MULT_F=7.125, RESET_TYPE=ACTIVE_LOW |
| **AXI INTC** | v4.1 | C_HAS_FAST=1 |
| **AXI GPIO (GPIO_IN)** | v2.0 | C_INTERRUPT_PRESENT=1, GPIO_BOARD_INTERFACE=push_buttons_5bits, GPIO2_BOARD_INTERFACE=dip_switches_16bits, USE_BOARD_FLOW=true |
| **AXI GPIO (GPIO_OUT)** | v2.0 | C_INTERRUPT_PRESENT=1, GPIO_BOARD_INTERFACE=rgb_led, GPIO2_BOARD_INTERFACE=led_16bits, USE_BOARD_FLOW=true |
| **AXI UARTLite** | v2.0 | C_BAUDRATE=230400, UARTLITE_BOARD_INTERFACE=usb_uart |
| **AXI Interconnect (main)** | v2.1 | NUM_SI=4, NUM_MI=1 |
| **AXI Interconnect (periph)** | v2.1 | NUM_MI=5 |
| **proc_sys_reset** | v5.0 | MIG init_calib_complete → reset zinciri, 81 MHz domain |
| **MDM** | v3.2 | JTAG debug, Hardware Manager (varsayılan config) |
| **LMB BRAM** | — | dlmb_bram_if_cntlr (lmb_bram_if_cntlr:4.0), dlmb_v10 (lmb_v10:3.0), ilmb_bram_if_cntlr (lmb_bram_if_cntlr:4.0), ilmb_v10 (lmb_v10:3.0), lmb_bram (blk_mem_gen:8.4) |
| **xlconcat_0** | v2.1 | NUM_PORTS=2 (DMA mm2s_introut + s2mm_introut) |
| **xlconcat_1** | v2.1 | NUM_PORTS=3 (GPIO_IN + UARTLite + ek sinyal) |
| **axis2fifo** | RTL | AXI-Stream → FIFO, 16-bit, backpressure destekli |
| **fifo2audpwm** | RTL | FIFO → PWM ses, 24.576 MHz clock, 96 kHz örnekleme |
| **tone_generator** | RTL | DDS tabanlı, AXIS_CLK_DOMAIN=/processing_system/clk_wiz_0_clk_out1, axis_tlast=(packet_count==PACKET_SIZE-1) |
| **helloworld.c** | SDK | DMA WAV oynatma, UART konsol, GPIO switch, interrupt handler, DMA_RESET_TIMEOUT_CNT=1000000, DMA_BUSY_TIMEOUT_CNT=2000000 |

### PWM Pin Atamaları (aktif XDC)

| Sinyal | PACKAGE_PIN | IOSTANDARD |
|---|---|---|
| PWM_AUDIO_0_pwm | A11 | LVCMOS33 |
| PWM_AUDIO_0_en | D12 | LVCMOS33 |

---

## PROJECT-B — Nexys Video AXI GPIO

| IP / Modül | Versiyon | Temel Parametreler |
|---|---|---|
| **MicroBlaze** | v11.0 | local_mem=32KB, cache=None, debug_module=Debug Only, axi_periph=Enabled, axi_intc=0, clk=/clk_wiz_0/clk_out1 (100 MHz) |
| **AXI GPIO** | v2.0 | C_GPIO_WIDTH=8, C_ALL_OUTPUTS=1 (LED), C_IS_DUAL=1, C_GPIO2_WIDTH=8, C_ALL_INPUTS_2=1 (switch), GPIO→leds_8bits, GPIO2→switches_8bits, base adres 0x40000000 |
| **AXI BRAM Controller** | v4.1 | Varsayılan config, connection automation ile MicroBlaze axi_periph'e bağlı |
| **Clocking Wizard** | v6.0 | 100 MHz osilat → 100 MHz fabric clock, BUFG dağıtım (automation) |
| **proc_sys_reset** | v5.0 | clk_wiz.locked → reset zinciri, BTNC aktif-düşük reset, 100 MHz (automation) |
| **AXI Interconnect** | — | MicroBlaze → AXI GPIO slave, AXI4-Lite (automation) |
| **MDM** | v3.2 | JTAG debug + UART debug, Hardware Manager (automation) |
| **LMB Subsystem** | — | 32KB local memory: dlmb_v10 + ilmb_v10 + dlmb_bram_if_cntlr + ilmb_bram_if_cntlr + blk_mem_gen (automation) |
| **axi_gpio_wrapper** | RTL | AXI GPIO sarmalayıcı, AXI tie-off pattern (PAT-B-001) |
| **simple_top** | RTL | Standalone GPIO testi, MicroBlaze olmadan |

---

## Proje Karşılaştırması

| Özellik | PROJECT-A (DMA Audio) | PROJECT-B (GPIO) |
|---|---|---|
| FPGA | xc7a100tcsg324-1 (Nexys A7-100T) | xc7a200tsbg484-1 (Nexys Video) |
| MicroBlaze | v10.0 | v11.0 |
| MicroBlaze Cache | D-cache + I-cache AKTİF | Yok (cache=None) |
| Local Bellek | 64 KB BRAM | 32 KB BRAM |
| DDR | 128 MB DDR2 (MIG) | Yok |
| Saat | 140.625 MHz (MIG) + 24.576 MHz (PWM) | 100 MHz (tek) |
| DMA | AXI DMA 7.1, burst=256 | Yok |
| UART | AXI UARTLite, 230400 baud | Yok |
| GPIO | GPIO_IN (push_btn+switch) + GPIO_OUT (LED+RGB) | AXI GPIO dual (8-bit LED + 8-bit switch) |
| BRAM Ctrl | Yok | AXI BRAM Controller v4.1 |
| Interrupt | INTC (C_HAS_FAST=1) + xlconcat×2 | Yok |
| Kaynak dosyası | design_1.tcl + helloworld.c | create_axi_simple.tcl |
