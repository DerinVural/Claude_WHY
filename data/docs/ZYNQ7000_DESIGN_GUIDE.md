# GC-RAG-VIVADO Zynq-7000 Tasarım Kılavuzu

## Zynq-7000 Platform Mimarisi

```
┌─────────────────────────────────────────────────┐
│         Zynq-7000 Processing System             │
├─────────────────────────────────────────────────┤
│  ┌──────────────────┐        ┌───────────────┐  │
│  │   Processing     │        │   AXI         │  │
│  │   System (PS)    │◄──────►│  Interconnect │  │
│  │                  │        │               │  │
│  │ • ARM Cortex-A9 │        │               │  │
│  │ • DDR3 Memory   │        │               │  │
│  │ • Peripherals   │        └───────────────┘  │
│  └──────────────────┘               ▲           │
│                                     │ AXI       │
│                                     ▼           │
│  ┌──────────────────┐        ┌───────────────┐  │
│  │ Programmable     │        │   User        │  │
│  │ Logic (PL)       │        │   IP Cores    │  │
│  │                  │        │               │  │
│  │ • LUT Arrays     │        │ • DSP blocks  │  │
│  │ • BlockRAMs      │        │ • Custom IP   │  │
│  │ • DSP slices     │        └───────────────┘  │
│  └──────────────────┘                           │
└─────────────────────────────────────────────────┘
```

## 1. Temel Zynq Konfigürasyonu

### Vivado ile Blok Diyagram Oluşturma

```tcl
# Create Zynq BD in Vivado
create_bd_design "system"

# Add Zynq Processing System
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0

# Connect AXI interfaces
connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] \
                     [get_bd_intf_pins axi_interconnect_0/S00_AXI]

# Create port connections
create_bd_port -type clk -dir O sys_clk
connect_bd_net [get_bd_ports sys_clk] [get_bd_pins processing_system7_0/FCLK_CLK0]
```

### Vivado GUI Adımları

1. **Block Design Oluştur**
   - File → New → Block Design
   - Name: `system`

2. **Zynq IP Ekle**
   - IP Catalog → ZYNQ7 Processing System
   - Double-click → Preset: `Zynq7 Processing System`

3. **AXI Interconnect Ekle**
   - Add IP → AXI Interconnect
   - S00_AXI: PS tarafından (Master)
   - M00_AXI: PL tarafından (Slave)

4. **Custom IP Ekle**
   - Add IP → Create IP
   - Interface: AXI-Lite Slave

## 2. DDR3 Bellek Konfigürasyonu

### PS-PL DDR3 Erişimi

```verilog
// Vivado MIG (Memory Interface Generator) ile DDR3 controller oluştur

// DDR3 parametreleri:
// - Data width: 64-bit (ECC disabled) / 72-bit (ECC enabled)
// - Speed: 1050 Mbps minimum
// - Latency: ~400 ns

// Blok Diyagramda:
// 1. MIG controller oluştur (DDR3 IP)
// 2. AXI to AXI Protocol Converter eklersen
// 3. AXI SmartConnect ile interconnect yap

module ddr3_write (
    input clk,
    input [31:0] addr,
    input [63:0] data_in,
    input we,
    output busy
);
    // Sadece PS yapacaksa burada kod gerekmez
    // PS HAL layer aracılığıyla erişir
endmodule
```

### C Kodu ile Erişim (PS Tarafından)

```c
#include "xil_types.h"
#include "xil_cache.h"

#define DDR3_BASE_ADDR 0x10000000
#define DDR3_SIZE      0x10000000  // 256 MB

// DDR3'e yazma
void write_ddr3(uint32_t offset, uint32_t data) {
    volatile uint32_t *ptr = (volatile uint32_t *)(DDR3_BASE_ADDR + offset);
    *ptr = data;
    Xil_DCacheFlush();
}

// DDR3'ten okuma
uint32_t read_ddr3(uint32_t offset) {
    volatile uint32_t *ptr = (volatile uint32_t *)(DDR3_BASE_ADDR + offset);
    Xil_DCacheInvalidate();
    return *ptr;
}
```

## 3. AXI Interface Tasarımı

### AXI4-Lite Protokolü

```verilog
module axi_lite_slave (
    // Global Signals
    input aclk,
    input aresetn,
    
    // Write Address Channel
    input [31:0] awaddr,
    input awvalid,
    output awready,
    
    // Write Data Channel
    input [31:0] wdata,
    input [3:0] wstrb,
    input wvalid,
    output wready,
    
    // Write Response Channel
    output [1:0] bresp,
    output bvalid,
    input bready,
    
    // Read Address Channel
    input [31:0] araddr,
    input arvalid,
    output arready,
    
    // Read Data Channel
    output [31:0] rdata,
    output [1:0] rresp,
    output rvalid,
    input rready
);

    // Register file: 4 x 32-bit registers
    reg [31:0] reg_file[0:3];
    
    // Write logic
    always @(posedge aclk) begin
        if (~aresetn) begin
            reg_file[0] <= 32'h0;
            reg_file[1] <= 32'h0;
            reg_file[2] <= 32'h0;
            reg_file[3] <= 32'h0;
        end else if (wvalid && wready) begin
            case (awaddr[3:2])
                2'b00: reg_file[0] <= wdata;
                2'b01: reg_file[1] <= wdata;
                2'b10: reg_file[2] <= wdata;
                2'b11: reg_file[3] <= wdata;
            endcase
        end
    end
    
    // Address ready: Always ready
    assign awready = 1'b1;
    assign arready = 1'b1;
    
    // Write ready
    assign wready = 1'b1;
    
    // Write response
    assign bresp = 2'b00;  // OKAY
    assign bvalid = wvalid;
    
    // Read data
    assign rdata = reg_file[araddr[3:2]];
    assign rresp = 2'b00;  // OKAY
    assign rvalid = arvalid;
    
endmodule
```

## 4. PL Tarafında HDMI Video Processing

### Zybo HDMI Pipeline

```verilog
module hdmi_pipeline (
    input clk,
    input [7:0] data_in,
    output [23:0] hdmi_out
);
    
    // Video timing generator
    wire vs, hs, de;
    
    video_timing_gen #(
        .H_ACTIVE(1280),
        .H_FRONT(110),
        .H_SYNC(40),
        .H_BACK(220),
        .V_ACTIVE(720),
        .V_FRONT(5),
        .V_SYNC(5),
        .V_BACK(20)
    ) vtg (
        .clk(clk),
        .vs(vs),
        .hs(hs),
        .de(de)
    );
    
    // Video data processing
    wire [7:0] r_out, g_out, b_out;
    
    // RGB colorbar generation
    color_pattern #(
        .PATTERN("COLORBAR")
    ) cp (
        .clk(clk),
        .de(de),
        .x_pos(x_pos),
        .y_pos(y_pos),
        .r_out(r_out),
        .g_out(g_out),
        .b_out(b_out)
    );
    
    // HDMI TX
    assign hdmi_out = {r_out, g_out, b_out};
    
endmodule
```

## 5. PetaLinux Device Driver Yazma

### Device Tree Entry

```dts
// system.dts
&amba {
    custom_ip@40000000 {
        compatible = "xlnx,custom-ip-1.0";
        reg = <0x40000000 0x1000>;
        interrupts = <0 29 4>;
        interrupt-parent = <&intc>;
    };
};
```

### Kernel Driver Örneği

```c
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/io-mapping.h>

struct custom_device {
    void __iomem *base;
    struct device *dev;
};

static int custom_probe(struct platform_device *pdev) {
    struct custom_device *dev;
    struct resource *res;
    
    dev = devm_kzalloc(&pdev->dev, sizeof(*dev), GFP_KERNEL);
    res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
    dev->base = devm_ioremap_resource(&pdev->dev, res);
    
    dev_info(dev->dev, "Custom IP initialized at 0x%llx\n", res->start);
    
    return 0;
}

static struct of_device_id custom_of_match[] = {
    { .compatible = "xlnx,custom-ip-1.0" },
    { }
};

static struct platform_driver custom_driver = {
    .probe = custom_probe,
    .driver = {
        .name = "custom-ip",
        .of_match_table = custom_of_match,
    }
};

module_platform_driver(custom_driver);
```

## 6. PYNQ ile Python Kullanımı

```python
from pynq import Bitstream, Overlay
from pynq import MMIO
import numpy as np

# Bitstream yükle
overlay = Overlay('/home/xilinx/jupyter_notebooks/custom.bit')

# IP kontrolcüsü oluştur
ip = overlay.custom_ip_0

# MMIO aracılığıyla register erişimi
mmio = MMIO(0x40000000, 0x1000)

# Yazma (offset, value)
mmio.write(0x0, 0xDEADBEEF)

# Okuma
data = mmio.read(0x0)
print(f"Read: 0x{data:08x}")
```

## 7. Vivado Simulation (Testbench)

```verilog
`timescale 1ns/1ps

module tb_system ();
    reg clk, rst;
    wire [31:0] data_out;
    
    // Clock generation
    initial begin
        clk = 0;
        forever #5 clk = ~clk;  // 100 MHz
    end
    
    // Reset sequence
    initial begin
        rst = 0;
        #20 rst = 1;
        #100 rst = 0;
    end
    
    // DUT
    system dut (
        .clk(clk),
        .rst(rst),
        .data_out(data_out)
    );
    
    // Testbench
    initial begin
        @(negedge rst);
        #100;
        $display("Simulation started");
        #1000;
        $finish;
    end
    
    // Waveform dumping
    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(0, tb_system);
    end
endmodule
```

## 8. İmplementasyon Kontrol Listesi

- [ ] Block Design tamamlandı
- [ ] Constraint dosyası (.xdc) hazır
- [ ] HDL simülasyonu başarılı
- [ ] Synthesis warnings kontrol edildi
- [ ] Place & Route timing closed
- [ ] Bitstream oluşturuldu
- [ ] Hardware exported (.hdf)
- [ ] PetaLinux/PYNQ kuruldu
- [ ] Device drivers yüklendi
- [ ] Fonksiyonel test başarılı

## İpuçları ve En İyi Pratikler

1. **AXI Protokolü**: Always AXI4-Lite basit IP'ler için
2. **Clock Frequency**: PS ve PL clk'ları senkronize et
3. **Reset Sequence**: Aktif HIGH reset kullan
4. **Simulation**: Formal verification öncesi simu yap
5. **Implementation**: Report gözle (timing, area, power)

---

**Kaynak**: Xilinx Zynq-7000 Design Guide
