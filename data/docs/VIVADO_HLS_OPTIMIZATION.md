# GC-RAG-VIVADO Vivado HLS Optimizasyon Rehberi

## Vivado HLS En İyi Pratikleri

### 1. Pipeline Optimizasyon

#### Pragma Direktifleri
```cpp
#pragma HLS PIPELINE II=1
#pragma HLS PIPELINE II=2 rewind
#pragma HLS PIPELINE enable_flush
```

#### Örnek
```cpp
void matrix_mult(int A[4][4], int B[4][4], int C[4][4]) {
    #pragma HLS PIPELINE II=1
    
    for(int i = 0; i < 4; i++) {
        for(int j = 0; j < 4; j++) {
            int sum = 0;
            #pragma HLS PIPELINE II=1
            for(int k = 0; k < 4; k++) {
                sum += A[i][k] * B[k][j];
            }
            C[i][j] = sum;
        }
    }
}
```

**Avantajlar:**
- Paralel işlem
- Throughput artışı
- Loop initiation interval (II) azalması

### 2. Loop Unrolling

```cpp
#pragma HLS UNROLL factor=4
#pragma HLS UNROLL skip_exit_check
```

#### Örnek
```cpp
void vector_add(int A[1024], int B[1024], int C[1024]) {
    loop_label: for(int i = 0; i < 1024; i++) {
        #pragma HLS UNROLL factor=8
        C[i] = A[i] + B[i];
    }
}
```

**Trade-offs:**
- ✅ Hız (8x hızlı)
- ❌ Alan (4x daha fazla area)
- ❌ Power consumption

### 3. Veri Tiplerinin Seçimi

```cpp
// Kötü: 32-bit double gerekli değil
double result = a + b;  // Too wide

// İyi: Precision yeterli ise 16-bit
ap_fixed<16, 8> result = a + b;  // Custom precision
```

### 4. Bellek Optimizasyonu

#### Array Partitioning
```cpp
#pragma HLS ARRAY_PARTITION variable=buffer type=block factor=4
#pragma HLS ARRAY_PARTITION variable=data type=cyclic factor=8
#pragma HLS ARRAY_PARTITION variable=cache type=complete dim=1
```

#### Resource Sharing
```cpp
#pragma HLS RESOURCE variable=multiplier core=Mul_LUT
#pragma HLS RESOURCE variable=divider core=DivnS instances=2
```

### 5. Loop Tiling (Blocking)

```cpp
void conv2d_optimized(int input[64][64], int kernel[3][3], int output[64][64]) {
    #pragma HLS DATAFLOW
    
    loop_y: for(int ty = 0; ty < 64; ty += 8) {  // Tile Y
        loop_x: for(int tx = 0; tx < 64; tx += 8) {  // Tile X
            #pragma HLS PIPELINE II=1
            loop_ky: for(int ky = 0; ky < 3; ky++) {
                loop_kx: for(int kx = 0; kx < 3; kx++) {
                    output[ty+ky][tx+kx] += input[ty+ky][tx+kx] * kernel[ky][kx];
                }
            }
        }
    }
}
```

### 6. Dataflow Optimization

```cpp
void dataflow_example(int input[100], int output[100]) {
    #pragma HLS DATAFLOW
    
    int buffer1[100], buffer2[100];
    
    // Aşama 1: Input işleme
    stage1(input, buffer1);
    
    // Aşama 2: Transformasyon
    stage2(buffer1, buffer2);
    
    // Aşama 3: Çıkış
    stage3(buffer2, output);
}
```

**Avantajları:**
- Aşamalar paralel çalışır
- Throughput önemli ölçüde artar
- Memory bandwidth kullanımı optimized

### 7. Interface Optimizasyonu

```cpp
#pragma HLS INTERFACE s_axilite port=return bundle=ctrl
#pragma HLS INTERFACE s_axilite port=data offset=0x0 bundle=ctrl
#pragma HLS INTERFACE m_axi port=mem offset=slave bundle=gmem depth=1024

void kernel(int* mem, int data) {
    #pragma HLS INTERFACE m_axi port=mem
    #pragma HLS INTERFACE s_axilite port=mem offset=0x00
    #pragma HLS INTERFACE s_axilite port=data offset=0x04
    #pragma HLS INTERFACE s_axilite port=return offset=0x08
}
```

### 8. Fixed-Point Aritmetiği

```cpp
#include "ap_fixed.h"

// Standart floating-point (32 bits)
void process_float(float in[100]) {
    for(int i = 0; i < 100; i++) {
        float result = sqrt(in[i]);
    }
}

// Fixed-point (16-bit: 8 integer + 8 fractional)
void process_fixed(ap_fixed<16,8> in[100]) {
    #pragma HLS PIPELINE II=1
    for(int i = 0; i < 100; i++) {
        ap_fixed<16,8> result = sqrt(in[i]);
    }
}
```

**Fixed-point Avantajları:**
- 10-50x daha hızlı
- Çok daha az area kullanır
- Daha az power consumption

### 9. Veri Tipi Genişliği Azaltma

```cpp
// Kötü: Tüm intermediate hesaplamalar 32-bit
int multiply_add(short a, short b, short c) {
    int result = (int)a * (int)b + (int)c;  // 32-bit ara sonuçlar
    return result;
}

// İyi: Minimal genişlik
ap_int<18> multiply_add_opt(ap_int<8> a, ap_int<8> b, ap_int<8> c) {
    ap_int<16> prod = a * b;  // 8+8=16 bit yeterli
    ap_int<18> result = prod + c;  // 16+8=18 bit yeterli
    return result;
}
```

### 10. Pragma Seçimi ve Kombinasyonu

```cpp
void optimized_kernel(int A[1024], int B[1024], int C[1024]) {
    #pragma HLS INTERFACE m_axi port=A
    #pragma HLS INTERFACE m_axi port=B
    #pragma HLS INTERFACE m_axi port=C
    #pragma HLS INTERFACE s_axilite port=return
    
    #pragma HLS DATAFLOW
    
    int buf_a[256], buf_b[256];
    
    // Stage 1: Load
    load_a: for(int i = 0; i < 1024; i += 256) {
        #pragma HLS PIPELINE II=1
        for(int j = 0; j < 256; j++) {
            buf_a[j] = A[i+j];
        }
    }
    
    // Stage 2: Process
    for(int i = 0; i < 1024; i++) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL factor=4
        C[i] = buf_a[i] + buf_b[i];
    }
}
```

## Performance Tuning Adımları

1. **Başlangıç**: Functionality test
   ```bash
   vivado_hls> open_project ./project
   vivado_hls> csynth_design
   ```

2. **Profiling**: Bottleneck belirleme
   ```bash
   vivado_hls> profile_design
   ```

3. **Optimization**: Directive ekleme
   - Pipeline
   - Unroll
   - Partition

4. **Validation**: Doğruluk kontrolü
   ```bash
   vivado_hls> cosim_design
   ```

5. **Resource Report**: Final metrikleri kontrol
   ```
   FPGA:     Slice LUTs/DSP blocks/BRAM
   Latency:  Cycle count
   II:       Initiation Interval
   ```

## Ortak Hatalar ve Çözümleri

| Problem | Neden | Çözüm |
|---------|-------|-------|
| Yüksek latency | Loop pipeline yok | `#pragma HLS PIPELINE` |
| Fazla area | Unroll factor çok yüksek | Factor düşür (8→4) |
| Düşük throughput | Dataflow yok | `#pragma HLS DATAFLOW` |
| Memory bottleneck | Single port RAM | `#pragma HLS ARRAY_PARTITION` |
| Timing fail | Complex operators | Fixed-point aritmetik |

## Vivado HLS Reporting

```
=== Solution: solution1 ===
Interface:
  - m_axi (128-bit, max latency 1024)
Timing: 10 ns (100 MHz)
Performance:
  - Latency: 1024 cycles
  - II: 1 cycle
Resources:
  - LUT: 2345 (15%)
  - DSP: 4 (10%)
  - BRAM: 8 (20%)
```

---

**Kaynak**: Xilinx Vivado HLS User Guide
**Güncelleme**: 2024
