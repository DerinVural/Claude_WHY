# FPGA RAG v2 — Proje Dokümantasyonu

**Proje:** GC-RAG-VIVADO-2
**Tarih:** 2026-02-25
**Durum:** Aktif — Robustness 0.839/A, 20q Benchmark 0.796/A

---

## İçindekiler

1. [Proje Genel Bakış](#1-proje-genel-bakış)
2. [Sistem Mimarisi](#2-sistem-mimarisi)
3. [Veri Modeli](#3-veri-modeli)
4. [Modül Açıklamaları](#4-modül-açıklamaları)
5. [Anti-Hallüsinasyon Katmanları](#5-anti-hallüsinasyon-katmanları)
6. [Sorgu Pipeline'ı](#6-sorgu-pipelineı)
7. [Geliştirme Süreci ve Yapılan Değişiklikler](#7-geliştirme-süreci-ve-yapılan-değişiklikler)
8. [Test Sistemi](#8-test-sistemi)
9. [Performans Sonuçları](#9-performans-sonuçları)
10. [Dosya Yapısı](#10-dosya-yapısı)
11. [Çalıştırma Kılavuzu](#11-çalıştırma-kılavuzu)
12. [Bilinen Sorunlar ve Gelecek Çalışmalar](#12-bilinen-sorunlar-ve-gelecek-çalışmalar)

---

## 1. Proje Genel Bakış

FPGA RAG v2, iki FPGA projesine ait teknik bilgiyi depolayan ve doğal dil soruları yanıtlayan bir **Retrieval-Augmented Generation** sistemidir.

### Hedef Projeler

| Proje ID | Proje Adı | Açıklama |
|----------|-----------|----------|
| **PROJECT-A** | `nexys_a7_dma_audio` | Nexys A7-100T kartı için DMA tabanlı ses işleme sistemi |
| **PROJECT-B** | `axi_gpio_example` | Nexys Video kartı için AXI GPIO örnek projesi |

### Temel Özellikler

- **4-Store Federated Mimari:** GraphStore + VectorStore + SourceChunkStore + RequirementTree
- **6-Layer Anti-Hallüsinasyon:** Yapısal doğrulama + confidence propagation + stale filtreleme
- **Cross-Project Reasoning:** İki proje arasındaki benzerlik ve çelişki tespiti
- **LLM Entegrasyonu:** Claude Sonnet 4.6 (birincil), GPT-4o-mini (fallback)
- **Türkçe Arayüz:** Tüm yanıtlar Türkçe, teknik terimler orijinal haliyle

---

## 2. Sistem Mimarisi

```
                        ┌─────────────────────────────────────────┐
                        │            KULLANICI SORUSU              │
                        └──────────────────┬──────────────────────┘
                                           │
                        ┌──────────────────▼──────────────────────┐
                        │           QUERY ROUTER                   │
                        │  • Sorgu sınıflandırma (7 tip)          │
                        │  • Proje tespiti (PROJECT-A / B)        │
                        │  • TR→EN augmentation                   │
                        └──────┬───────┬──────┬───────┬───────────┘
                               │       │      │       │
              ┌────────────────▼─┐ ┌───▼──┐ ┌▼─────┐ ┌▼──────────────┐
              │   GRAPH STORE    │ │VECTOR│ │SOURCE│ │ REQUIREMENT   │
              │  (NetworkX)      │ │STORE │ │CHUNK │ │    TREE       │
              │  155 node        │ │ v2   │ │STORE │ │               │
              │  495 edge        │ │(Chro │ │(Chro │ │               │
              │                  │ │maDB) │ │maDB) │ │               │
              └────────────────┬─┘ └───┬──┘ └┬─────┘ └┬──────────────┘
                               │       │     │         │
                        ┌──────▼───────▼─────▼─────────▼──────────┐
                        │         HALLUCINATION GATE (6 Layer)     │
                        │  L1:Evidence  L2:Confidence  L3:Coverage │
                        │  L4:ParseUncertain  L5:Stale  L6:Contra  │
                        └──────────────────┬──────────────────────┘
                                           │
                        ┌──────────────────▼──────────────────────┐
                        │         RESPONSE BUILDER                 │
                        │  • LLM context paketi                   │
                        │  • FPGA_RAG_SYSTEM_PROMPT (11 kural)    │
                        └──────────────────┬──────────────────────┘
                                           │
                        ┌──────────────────▼──────────────────────┐
                        │         LLM (Claude / GPT-4o-mini)      │
                        └──────────────────┬──────────────────────┘
                                           │
                        ┌──────────────────▼──────────────────────┐
                        │         GROUNDING CHECKER               │
                        │  • LLM cevabındaki değerleri doğrular   │
                        │  • Context'te olmayan değerleri işaret. │
                        └──────────────────┬──────────────────────┘
                                           │
                        ┌──────────────────▼──────────────────────┐
                        │         YAPILANDIRILMIŞ YANIT           │
                        │  Güven + Kaynaklar + Uyarılar + Açıklama│
                        └─────────────────────────────────────────┘
```

---

## 3. Veri Modeli

### 3.1 Node Tipleri (GraphStore)

| Node Tipi | Açıklama | Örnek |
|-----------|----------|-------|
| `PROJECT` | Kök proje düğümü | `PROJECT-A`, `PROJECT-B` |
| `DECISION` | Mimari kararlar | `DMA-DEC-001` (SG-DMA seçimi) |
| `REQUIREMENT` | Gereksinimler | `DMA-REQ-003` |
| `COMPONENT` | IP blokları / modüller | `COMP-A-microblaze_0`, `COMP-B-axi_gpio_0` |
| `EVIDENCE` | Kaynak kanıtlar | Referans belge linkleri |
| `CONSTRAINT` | Zamanlama kısıtları | XDC constraint bilgileri |
| `PATTERN` | Tasarım desenleri | `PATT-AXI-STREAM-001` |
| `ISSUE` | Bilinen sorunlar | `ISSUE-A-DMA-001` |
| `SOURCE_DOC` | Kaynak belgeler | TCL, XDC, V dosyaları |

### 3.2 Edge Tipleri

| Edge Tipi | Açıklama |
|-----------|----------|
| `IMPLEMENTS` | COMPONENT → REQUIREMENT bağlantısı |
| `VERIFIED_BY` | Node → EVIDENCE bağlantısı |
| `SUPERSEDES` | Yeni node → eski node (stale filter için) |
| `CONTRADICTS` | Çelişen kararlar arasında |
| `ANALOGOUS_TO` | İki projede benzer yapılar |
| `DEPENDS_ON` | Bağımlılık ilişkisi |
| `ALTERNATIVE_TO` | Alternatif tasarım seçenekleri |

### 3.3 Confidence Seviyeleri

```
PARSE_UNCERTAIN < MEDIUM < HIGH
```

- **HIGH:** Doğrulanmış, kaynak koddan çıkarılmış
- **MEDIUM:** Makul güvenilirlik, dokümantasyondan
- **PARSE_UNCERTAIN:** Otomatik parse sonucu, belirsiz

### 3.4 Veritabanı İstatistikleri

| Store | Boyut | Konum |
|-------|-------|-------|
| GraphStore | 155 node, 495 edge | `db/graph/fpga_rag_v2_graph.json` |
| VectorStore | 155 döküman | `db/chroma_graph_nodes/` |
| SourceChunkStore | 151 chunk | `db/chroma_source_chunks/` |
| RequirementTree | GraphStore içinde | — |

---

## 4. Modül Açıklamaları

### 4.1 `src/rag_v2/query_router.py`

Sorgulama motorunun kalbi. Soruyu analiz eder, uygun store'ları sorgular ve `QueryResult` döndürür.

**Sorgu Tipleri:**

| Tip | Açıklama | Route Metodu |
|-----|----------|--------------|
| `FACTUAL` | Teknik parametre soruları | `_route_factual()` |
| `COMPARATIVE` | İki şeyi karşılaştırma | `_route_comparative()` |
| `CROSSREF` | Projeler arası ilişkiler | `_route_crossref()` |
| `REQUIREMENT` | Gereksinim soruları | `_route_requirement()` |
| `DEBUG` | Hata ayıklama | `_route_debug()` |
| `TIMING` | Zamanlama kısıtları | `_route_timing()` |
| `GENERAL` | Genel sorular | `_route_general()` |

**Proje Tespiti (`_resolve_project`):**

```python
# 1. Text sinyalleri (en yüksek öncelik)
_TEXT_PROJECT_SIGNALS = [
    ("nexys video", "PROJECT-B"),
    ("axi_gpio", "PROJECT-B"),
    ("axi gpio", "PROJECT-B"),
    ("nexys a7", "PROJECT-A"),
    ("dma audio", "PROJECT-A"),
    ("axis2fifo", "PROJECT-A"),
    # ... vb.
]

# 2. Vector voting (threshold >= 0.70)
# 3. Varsayılan: PROJECT-A
```

**TR→EN Query Augmentation (`_TR_EN_TERMS`):**

Türkçe teknik terimler İngilizce karşılıklarıyla genişletilir:
```python
"ddr3": "ddr2 mig_7series MIG DDR SDRAM ui_clk mem_if_ddr2",
"icache": "C_USE_ICACHE C_USE_DCACHE CONFIG microblaze cache",
"zamanlama": "timing constraint period clock setup hold",
# ... vb.
```

### 4.2 `src/rag_v2/hallucination_gate.py`

6 katmanlı anti-hallüsinasyon filtresi. Detaylar için [Bölüm 5](#5-anti-hallüsinasyon-katmanları).

### 4.3 `src/rag_v2/response_builder.py`

LLM için context paketi oluşturur ve yapılandırılmış yanıt formatlar.

**`FPGA_RAG_SYSTEM_PROMPT` — 11 Kural:**

| # | Kural Özeti |
|---|-------------|
| 1 | Sadece verilen context kullan, asla tahmin üretme |
| 2 | KAYNAK DOSYA bölümündeki değerleri doğrudan kullan |
| 3 | Graph metadata + kaynak dosyaları birleştir |
| 4 | Her iddia için kaynak belirt (node_id veya dosya:satır) |
| 5 | PARSE_UNCERTAIN bilgileri "belirsiz" olarak işaretle |
| 6 | Coverage Gap varsa "bulunamadı" de, ama kaynak varsa onu kullan |
| 7 | CONTRADICTS varsa her iki görüşü sun |
| 8 | Türkçe yanıt ver, teknik terimler orijinal |
| 9 | **KRİTİK:** Proje listesi sorularında sadece PROJECT node'ları göster |
| 10 | **KRİTİK:** RTL parametresi context'te literal yoksa uydurma |
| 11 | **KRİTİK:** Bilinmeyen arayüz/özellik için "projede yok" de |

### 4.4 `src/rag_v2/source_chunk_store.py`

Gerçek kaynak dosyaları (TCL, XDC, Verilog, C) ChromaDB'ye indeksler.

**Chunk Stratejileri:**

| Dosya Tipi | Bölme Stratejisi |
|------------|------------------|
| `.tcl` | `proc` seviyesi + `# Create instance:` IP blokları |
| `.xdc` | `##` bölüm başlıkları (`##\s*` — boşluksuz da çalışır) |
| `.v` / `.sv` | `module` tanımları |
| `.c` / `.h` | `/* --- */` yorum bölümleri |
| `.md` | `##` başlıkları |

**XDC Chunker Kritik Fix:**
```python
# ÖNCE (bozuk): Boşluksuz başlıkları kaçırıyordu
r"##\s+"
# SONRA (doğru):
r"##\s*"  # "##Omnidirectional Microphone" gibi başlıkları da yakalar
```

### 4.5 `src/rag_v2/grounding_checker.py`

LLM yanıtındaki sayısal/parametrik değerleri context'e karşı doğrular.

**Çalışma Mantığı:**
1. LLM cevabından sayısal değerleri çıkar (regex)
2. Bu değerlerin source chunk'larda veya graph node'larında geçip geçmediğini kontrol et
3. Context'te olmayan değerler için uyarı üret: `[GroundingWarn] Değer 'X' context'te bulunamadı`

### 4.6 `src/rag_v2/cross_reference_detector.py`

İki proje arasındaki ilişkileri otomatik tespit eder.

**4 Tespit Modu:**

| Mod | Açıklama | Örnek |
|-----|----------|-------|
| M1: Structural | Benzer IP blokları → `ANALOGOUS_TO` | MicroBlaze-A ↔ MicroBlaze-B |
| M2: Problem Similarity | Benzer sorunlar → `ANALOGOUS_TO` | Aynı AXI hatası |
| M3: Pattern Reuse | Aynı tasarım deseni | AXI-Stream pipeline |
| M4: Contradictions | Zıt kararlar → `CONTRADICTS` | Cache açık/kapalı |

### 4.7 `src/rag_v2/matching_engine.py`

Graph üzerinde semantik eşleştirme yapar, node benzerlik skorları hesaplar.

### 4.8 `src/rag_v2/graph_store.py`

NetworkX tabanlı knowledge graph. CRUD operasyonları, komşu sorgulama, stale node tespiti.

### 4.9 `src/rag_v2/vector_store_v2.py`

ChromaDB tabanlı vektör arama. `all-MiniLM-L6-v2` embedding modeli.

---

## 5. Anti-Hallüsinasyon Katmanları

### Aktif Katmanlar (6/10)

#### Layer 1: Evidence Gate
- Her `REQUIREMENT`, `DECISION`, `COMPONENT` node'unun bir `EVIDENCE` node'una bağlı olması gerekir
- Bağlantı yoksa: `[Layer1-EvidenceGate] Node 'X' has no linked EVIDENCE node`

#### Layer 2: Confidence Propagation
- Zincirdeki en düşük confidence = toplam confidence (weakest link)
- Edge confidence'ları da node confidence'larını etkiler
- `PARSE_UNCERTAIN < MEDIUM < HIGH`

#### Layer 3: Coverage Gap
- `IMPLEMENTS` edge'i olmayan `REQUIREMENT` node'ları işaretlenir
- `[Layer3-CoverageGap] Requirement 'X' has no implementing component`

#### Layer 4: PARSE_UNCERTAIN
- `PARSE_UNCERTAIN` confidence'lı node'lar için uyarı üretilir
- Otomatik olarak `MEDIUM` gibi işlenir

#### Layer 5: SUPERSEDES (Stale Filter)
- `SUPERSEDES` edge'i ile işaretlenmiş eski node'lar sonuçlardan çıkarılır
- `[Layer5-Stale] Node 'X' has been SUPERSEDED by [Y]`

#### Layer 6: CONTRADICTS Check
- `CONTRADICTS` edge'i olan node çiftleri uyarılır
- **KRİTİK FIX:** Sadece `DECISION-DECISION` çiftleri için ateşlenir
- `COMPONENT-COMPONENT` çiftleri atlanır (CrossRef Mode 1 yapısal yanlış sınıflandırma)

```python
# Layer 6 son hali:
if u_type == "COMPONENT" or v_type == "COMPONENT":
    continue  # Yanlış pozitifi önle
```

### Pasif Katmanlar (4/10 — gelecek)
- Layer 7: Source Triangulation
- Layer 8: Schema Validation
- Layer 9: Temporal Consistency
- Layer 10: Cross-Project Validation

---

## 6. Sorgu Pipeline'ı

```
Kullanıcı Sorusu
    │
    ▼
[1] Sorgu Sınıflandırma
    router.classify(question) → QueryType

    │
    ▼
[2] Multi-Store Routing
    router.route(question, query_type) → QueryResult
    ├── GraphStore: node + edge sorgusu
    ├── VectorStore: semantik benzerlik arama
    ├── SourceChunkStore: kaynak dosya chunk'ları
    └── RequirementTree: gereksinim hiyerarşisi

    │
    ▼
[3] Hallucination Gate
    gate.check(nodes, edges) → GateResult
    └── 6 katman sırayla çalışır

    │
    ▼
[4] Context Paketi
    build_llm_context(query_result, gate_result) → str
    ├── Active node'lar (stale filtrelenmiş)
    ├── Graph edge'leri
    ├── Source chunk'lar (benzerlik skoruna göre sıralı)
    └── Gate uyarıları

    │
    ▼
[5] LLM Çağrısı
    llm.generate(query, [context], system_prompt) → str
    └── FPGA_RAG_SYSTEM_PROMPT (11 kural)

    │
    ▼
[6] Grounding Check
    GroundingChecker().check(answer, chunks, nodes) → warnings
    └── LLM cevabındaki değerleri context'e karşı doğrula

    │
    ▼
[7] Yapılandırılmış Yanıt
    build_structured_response() → Dict
    ├── answer: tam formatlanmış yanıt
    ├── confidence: HIGH / MEDIUM / PARSE_UNCERTAIN
    ├── sources: [node_id, ...]
    ├── warnings: [uyarı listesi]
    └── query_type, vector_hits, graph_nodes, ...
```

---

## 7. Geliştirme Süreci ve Yapılan Değişiklikler

### Faz 1: Temel RAG Sistemi (ChromaDB)
- ChromaDB ile 1.1M+ chunk embedding
- Basit vektör arama tabanlı soru-cevap
- **Skor:** ~0.503/C

### Faz 2: RAG v2 — 4-Store Mimarisi
- GraphStore (NetworkX knowledge graph) eklendi
- VectorStore v2 (node bazlı embedding)
- QueryRouter (7 tip sorgu sınıflandırma)
- HallucinationGate (6 katman)
- **Skor:** 0.658/B → 0.821/A

### Faz 3: MatchingEngine + CrossReferenceDetector
- İki proje arası ilişki tespiti (ANALOGOUS_TO, CONTRADICTS)
- 4 tespit modu (M1-M4)
- Test E (contradiction detection) altyapısı
- **Skor:** 0.821/A → 0.849/A

### Faz 4: Source Chunk Store İyileştirmeleri

**XDC Chunker Fix:**
```python
# Nexys-A7-100T-Master.xdc'deki boşluksuz bölüm başlıklarını yakalar
# A11 (PWM_AUDIO_0_pwm) ve D12 (PWM_AUDIO_0_en) artık indeksleniyor
r"##\s*"  # önceki: r"##\s+"
```

**TCL Chunker İyileştirmesi:**
```python
# Her IP bloğu kendi adlı chunk'ına ayrıldı
# design_1.tcl microblaze_0 chunk: similarity 0.314 → 0.546
# "proc" seviyesi + "# Create instance:" bölme stratejisi
```

**Index Temizliği:**
- PROJECT-A: Sadece Nexys-A7-100T indekslendi (50T kaldırıldı)
- PROJECT-B: SYNTHESIS_RESULTS.md kaldırıldı (Türkçe gürültü)

### Faz 5: Robustness İyileştirmeleri

#### Fix 1: Layer 6 COMPONENT-COMPONENT False Positive

**Sorun:** CrossRef Mode 1 (structural), benzer IP blokları arasına `CONTRADICTS` edge koyuyordu. Bu edge'ler Layer 6'yı gereksiz yere tetikliyordu.

```
COMP-B-microblaze_0 → COMP-A-microblaze_0  [CONTRADICTS, source=None, MEDIUM]
```

**Çözüm:**
```python
# hallucination_gate.py — _layer6_contradicts()
u_type = (self.graph.get_node(u) or {}).get("node_type", "")
v_type = (self.graph.get_node(v) or {}).get("node_type", "")
if u_type == "COMPONENT" or v_type == "COMPONENT":
    continue  # Sadece DECISION-DECISION çiftleri için ateşle
```

**Sonuç:** Test E 0.500/C → 1.000/A

#### Fix 2: `("microblaze", "PROJECT-B")` Yanlış Sinyali

**Sorun:** Her iki proje de MicroBlaze kullanıyor, ancak `_TEXT_PROJECT_SIGNALS`'a yanlışlıkla `("microblaze", "PROJECT-B")` eklenmişti. Bu, MicroBlaze içeren tüm soruları PROJECT-B'ye yönlendiriyordu.

```
# Test A sorusu "microblaze_0" içeriyordu
# → Yanlışlıkla PROJECT-B'ye route edildi
# → axi_gpio_example'dan source chunk'lar döndü
# → design_1.tcl hiç bulunamadı
```

**Çözüm:** İlgili yanlış sinyaller kaldırıldı:
```python
# KALDIRILDI:
# ("microblaze", "PROJECT-B"),  # Her iki proje de MicroBlaze kullanıyor!
# ("mdm_1", "PROJECT-B"),       # Aynı sebep
```

**Sonuç:** Test A için doğru proje tespiti restore edildi.

#### Fix 3: DDR3 / Cache Query Augmentation

**Sorun:** "DDR3", "icache" gibi Türkçe/teknik terimler doğru arama sonuçlarına ulaşamıyordu.

**Çözüm:** `_TR_EN_TERMS` sözlüğüne eklendi:
```python
"ddr3":   "ddr2 mig_7series MIG DDR SDRAM ui_clk mem_if_ddr2",
"ddr":    "mig_7series DDR2 ui_clk MIG 7series mem_if_ddr2 SDRAM",
"c_use_icache": "CONFIG.C_USE_ICACHE C_USE_DCACHE microblaze_0 cache 1 0 config",
"icache": "C_USE_ICACHE C_USE_DCACHE CONFIG microblaze cache ICache DCache",
```

#### Fix 4: CrossRef Global Fallback

**Sorun:** Meta-sorgular ("İki proje arasında ANALOGOUS_TO veya CONTRADICTS ilişkisi var mı?") spesifik bir node'a ulaşamadığında 0 edge döndürüyordu.

**Çözüm:** `_route_crossref()`'e global fallback eklendi:
```python
# Meta-sinyal tespiti varsa tüm ANALOGOUS_TO/CONTRADICTS edge'lerini döndür
meta_signals = ("analogous_to", "contradicts", "benzer yapı", "çelişki",
                "ilişki", "benzer", "analogous", "similar", "relationship",...)
if any(sig in q_lower for sig in meta_signals):
    for u, v, eattrs in self.graph._graph.edges(data=True):
        if etype in ("ANALOGOUS_TO", "CONTRADICTS", "ALTERNATIVE_TO"):
            cross_edges.append(...)
```

#### Fix 5: GroundingChecker Entegrasyonu

**Sorun:** LLM, context'te olmayan sayısal değerler üretebiliyordu.

**Çözüm:** `grounding_checker.py` oluşturuldu ve pipeline'a entegre edildi:
```python
# test_robustness.py ve app_v2.py'de:
grounding_warns = GroundingChecker().check(answer, sc_chunks, qr.graph_nodes)
if grounding_warns:
    gr.warnings.extend(grounding_warns)
```

#### Fix 6: System Prompt Rule 12 (EKLENDI → KALDIRILDI)

**Sorun:** Rule 12 ("Yeterli bilgi yoksa 'Bu bilgi sistemde yer almamaktadır' de ve dur") LLM'nin context'te geçerli bilgi olduğunda bile reddetmesine yol açtı.

**Sonuç:** 0.815/A → 0.303/F (felaket regresyon)

**Çözüm:** Rule 12 tamamen kaldırıldı. Rules 1-11 yeterli.

#### Fix 7: MicroBlaze ve AXI DMA node key_logic Güncelleme

Sorgu augmentasyonunun çalışması için node'ların embedding'lerinin cache/DMA parametrelerini içermesi gerekiyordu:

```python
# COMP-A-microblaze_0 key_logic güncellendi:
"C_USE_ICACHE {1} — ICache etkin. C_USE_DCACHE {1} — DCache etkin.
 vlnv: xilinx.com:ip:microblaze:10.0. AXI4 master, LMB BRAM arayüzü."

# COMP-A-axi_dma_0 key_logic güncellendi:
"vlnv: xilinx.com:ip:axi_dma:7.1. Scatter-Gather (SG) mode etkin.
 XAxiDma_HasSg=1. AXI4 master, AXI-Stream arayüzleri."
```

#### Fix 8: get_llm() API Sağlık Kontrolü

**Sorun:** Anthropic API kredisi tükendiğinde ClaudeGenerator başarıyla oluşturuluyor ancak `generate()` çağrısında hata fırlatıyordu. Fallback mekanizması çalışmıyordu.

**Çözüm:**
```python
def get_llm():
    try:
        llm = ClaudeGenerator(...)
        llm.generate(query="test", context_documents=["test"])  # Sağlık testi
        return llm
    except Exception as e:
        print(f"Claude kullanılamıyor, OpenAI'ya geçiliyor...")
    return OpenAIGenerator(...)  # Otomatik fallback
```

---

## 8. Test Sistemi

### 8.1 20 Soru Benchmark (`scripts/test_v2_20q.py`)

20 FPGA sorusu, her biri için:
- Beklenen anahtar terimler listesi
- Puan hesaplama: bulunan terimler / toplam terimler
- Ağırlıklı skor

```bash
source .venv/bin/activate && python3 scripts/test_v2_20q.py --save
```

**Soru Kategorileri:**

| Soru | Proje | Alan |
|------|-------|------|
| A-Q01 – A-Q10 | PROJECT-B (axi_gpio_example) | Kurgu, RTL, Sentez, Debug |
| B-Q01 – B-Q10 | PROJECT-A (nexys_a7_dma_audio) | Yazılım, Timing, Kurgu |

### 8.2 Robustness Test Suite (`scripts/test_robustness.py`)

5 test kategorisi, toplam ağırlıklı skor:

```bash
source .venv/bin/activate && python3 scripts/test_robustness.py --save
```

| Test | Ağırlık | Açıklama |
|------|---------|----------|
| **A — Held-Out Dosya** | %25 | `design_1.tcl` kaldırılıp eklenerek sistem testi |
| **B — Fabrication/Recall** | %30 | Uydurma değerleri reddedip gerçekleri kabul etme |
| **C — Multi-Hop Traversal** | %20 | 2-3 hop graph traversal |
| **D — Cross-Project Reasoning** | %15 | İki proje arası karşılaştırma |
| **E — Contradiction Detection** | %10 | Kasıtlı çelişki tespiti |

#### Test A — Held-Out Dosya (3 Faz)

```
Faz 1: design_1.tcl indekste mevcut → sistem doğru yanıt vermeli
Faz 2: design_1.tcl kaldırılıyor → sistem "bilgi yok" demeli
Faz 3: design_1.tcl geri ekleniyor → sistem yeniden doğru yanıt vermeli
```

#### Test B — Fabrication/Recall

**Tuzak soruları (LLM reddetmeli):**
- B-TRAP-1: axis2fifo FIFO derinliği (kaynak kodda tanımsız)
- B-TRAP-2: tone_generator.v DDS bit genişliği (kaynak kodda yok)
- B-TRAP-3: MicroBlaze L1 data cache boyutu (NO_CACHE ile oluşturulmuş)
- B-TRAP-4: I2S protokolü (projede yok)

**Gerçek sorular (LLM doğru yanıtlamalı):**
- B-REAL-1: C_USE_ICACHE değeri
- B-REAL-2: C_GPIO_WIDTH ve axi_gpio_0
- B-REAL-3: XDC R4 pini IOSTANDARD
- B-REAL-4: XAxiDma_HasSg ve init_dma fonksiyonu

#### Test E — Contradiction Detection (3 Faz)

```
Faz 1: Çelişkisiz baseline → Layer 6 ateşlememeli
Faz 2: TEST-DEC-CONTRA-001 node'u ekleniyor → Layer 6 ateşlemeli
Faz 3: Test node'u kaldırılıyor → sistem temizlenmeli
```

---

## 9. Performans Sonuçları

### 9.1 Skor Tarihçesi

| Tarih | 20q Skoru | Robustness | Açıklama |
|-------|-----------|------------|----------|
| Başlangıç | 0.503/C | — | ChromaDB tabanlı basit RAG |
| RAG v2 | 0.658/B | — | 4-store mimari |
| v2 + Fixes | 0.821/A | — | QueryRouter + project detection |
| + Matching/CrossRef | 0.849/A | 0.787/B | M1-M4 tespit |
| + Source chunks | 0.883/A | 0.815/A | TCL/XDC chunker iyileştirme |
| + Robustness fixes | 0.796/A* | **0.839/A** | Layer 6, CrossRef, microblaze fix |

*GPT-4o-mini ile (Claude API kredisi tükendi)

### 9.2 Son Robustness Sonuçları (2026-02-25)

```
A — Held-Out Dosya    ████████████████████ 1.000 [A] (ağırlık=%25)
B — Fabrication/Recall ███████████████░░░░░ 0.758 [B] (ağırlık=%30)
C — Multi-Hop          ███████████████░░░░░ 0.778 [B] (ağırlık=%20)
D — Cross-Project      ██████████████░░░░░░ 0.706 [B] (ağırlık=%15)
E — Contradiction      ████████████████████ 1.000 [A] (ağırlık=%10)
────────────────────────────────────────────
AĞIRLIKLI TOPLAM      : 0.839/A
```

**Test B Detay:**

| Soru | Sonuç | Açıklama |
|------|-------|----------|
| B-TRAP-1 | ✓ 1.000 | FIFO derinliği doğru reddedildi |
| B-TRAP-2 | ✗ 0.000 | "32 bit" halüsinasyon üretildi |
| B-TRAP-3 | ✓ 1.000 | NO_CACHE durumu doğru tespit edildi |
| B-TRAP-4 | ✗ 0.500 | I2S sorusu kısmen reddedildi |
| B-REAL-1 | ✓ 0.850 | C_USE_ICACHE doğru yanıtlandı |
| B-REAL-2 | ✓ 1.000 | C_GPIO_WIDTH doğru yanıtlandı |
| B-REAL-3 | ✓ 1.000 | XDC pin IOSTANDARD doğru yanıtlandı |
| B-REAL-4 | ✓ 1.000 | XAxiDma_HasSg doğru yanıtlandı |

### 9.3 Pipeline Performansı

| Metrik | Değer |
|--------|-------|
| Ortalama yanıt süresi | ~9s (GPT-4o-mini) |
| HIGH güven yanıtlar | 2/20 (%10) |
| MEDIUM güven yanıtlar | 18/20 (%90) |
| Stale node filtresi | Aktif |

---

## 10. Dosya Yapısı

```
GC-RAG-VIVADO-2/
├── app_v2.py                    # Streamlit web arayüzü
├── .env                         # API anahtarları
├── PROJECT_DOCUMENTATION.md     # Bu döküman
├── evaluation_v2_20q.json       # Son 20q test sonuçları
├── robustness_report.json       # Son robustness test sonuçları
│
├── src/
│   ├── rag_v2/
│   │   ├── query_router.py      # Sorgu yönlendirme motoru (ANA MODÜL)
│   │   ├── hallucination_gate.py # 6-katman anti-halüsinasyon
│   │   ├── response_builder.py  # LLM context + sistem promptu
│   │   ├── graph_store.py       # NetworkX knowledge graph
│   │   ├── vector_store_v2.py   # ChromaDB vektör arama
│   │   ├── source_chunk_store.py # Kaynak dosya indeksleme
│   │   ├── grounding_checker.py # LLM cevap doğrulama
│   │   ├── matching_engine.py   # Semantik eşleştirme
│   │   ├── cross_reference_detector.py # Proje arası ilişki
│   │   └── loader.py            # Graph + node yükleyici
│   └── rag/
│       ├── claude_generator.py  # Anthropic Claude API
│       ├── openai_generator.py  # OpenAI API (fallback)
│       └── gemini_generator.py  # Google Gemini API
│
├── scripts/
│   ├── test_v2_20q.py           # 20 soru benchmark
│   ├── test_robustness.py       # 5-kategori robustness testi
│   ├── index_source_files.py    # Kaynak dosya indeksleme
│   ├── build_graph_db.py        # Graph DB oluşturma
│   ├── add_new_knowledge_nodes.py # Node ekleme
│   ├── run_cross_reference.py   # CrossRef çalıştırma
│   └── chat.py                  # Terminal chat arayüzü
│
├── db/
│   ├── graph/
│   │   └── fpga_rag_v2_graph.json  # Knowledge graph (155 node, 495 edge)
│   ├── chroma_graph_nodes/      # Node embedding DB
│   └── chroma_source_chunks/    # Kaynak chunk DB (151 chunk)
│
└── data/
    ├── knowledge_graph/         # Node JSON tanımları
    │   ├── project_nodes.json
    │   ├── decision_nodes.json
    │   ├── component_nodes.json
    │   └── ...
    └── code/                    # FPGA proje kaynak dosyaları
        ├── nexys_a7_dma_audio/
        └── axi_gpio_example/
```

---

## 11. Çalıştırma Kılavuzu

### Ön Koşullar

```bash
cd /home/test123/GC-RAG-VIVADO-2
source .venv/bin/activate
```

### Web Arayüzü (Streamlit)

```bash
streamlit run app_v2.py
```

### Terminal Chat

```bash
python3 scripts/chat.py
```

### Tek Sorgu

```bash
python3 scripts/query_v2.py "axi_gpio_0 kaç bit GPIO kanalına sahip?"
```

### 20 Soru Benchmark

```bash
python3 scripts/test_v2_20q.py --save        # Sonuçları kaydet
python3 scripts/test_v2_20q.py --no-llm      # Sadece retrieval (LLM yok)
python3 scripts/test_v2_20q.py --verbose     # LLM cevaplarını göster
```

### Robustness Testi

```bash
python3 scripts/test_robustness.py --save
```

### Kaynak Dosya İndeksleme

```bash
python3 scripts/index_source_files.py
```

### Graph DB Güncelleme

```bash
python3 scripts/add_new_knowledge_nodes.py
python3 scripts/run_cross_reference.py
```

### Graph İstatistikleri

```bash
python3 scripts/show_stats.py
```

### API Durumu Kontrolü

```bash
python3 -c "
import sys, os; sys.path.insert(0, 'src')
from dotenv import load_dotenv; load_dotenv()
from rag.claude_generator import ClaudeGenerator
try:
    ClaudeGenerator().generate('test', ['test'])
    print('Claude: OK')
except Exception as e:
    print(f'Claude: HATA — {e}')
"
```

---

## 12. Bilinen Sorunlar ve Gelecek Çalışmalar

### Mevcut Açık Sorunlar

| Sorun | Etki | Durum |
|-------|------|-------|
| Anthropic API kredisi tükendi | 20q skoru ~%5 düşük (GPT-4o-mini ile) | Kredi yüklenmesi bekliyor |
| B-TRAP-2: tone_generator.v DDS halüsinasyonu | Robustness Test B %7 kayıp | Kaynak kod eksikliği |
| A-Q09: "microblaze_bd_wrapper" / "Utilization" | 20q 0.400/D | SYNTHESIS raporu eksik |
| D-CROSS-1 / D-CROSS-3: "Tek proje" yanıtı | Robustness Test D %12 kayıp | LLM cross-project inference zayıf |

### Gelecek İyileştirme Alanları

#### Kısa Vadeli
1. **Anthropic API kredisi yükleme** → Claude Sonnet 4.6 ile tekrar test
2. **tone_generator.v kaynak kodu ekleme** → B-TRAP-2 fix
3. **SYNTHESIS raporu entegrasyonu** → A-Q09 fix (microblaze_bd_wrapper, LUT/FF kullanımı)

#### Orta Vadeli
4. **Layer 7: Source Triangulation** — 3+ kaynakta bulunan bilgiler HIGH, tek kaynakta MEDIUM
5. **D-CROSS soruları için özel prompt** — "Her iki projede de kontrol et" yönlendirmesi
6. **Aktif öğrenme** — başarısız test sorularından otomatik node güncelleme

#### Uzun Vadeli
7. **Layer 8-10 implementasyonu** — Schema Validation, Temporal Consistency, Cross-Project
8. **Gerçek zamanlı graph güncelleme** — Vivado proje değişikliklerini otomatik takip
9. **Multi-project expansion** — 2+ proje desteği

---

## Ek: Önemli Sabitler

```python
# Proje ID'leri
PROJECT_A = "nexys_a7_dma_audio"
PROJECT_B = "axi_gpio_example"

# Veritabanı yolları
GRAPH_PATH = "db/graph/fpga_rag_v2_graph.json"
VECTOR_DB_PATH = "db/chroma_graph_nodes"
SOURCE_CHUNK_DB_PATH = "db/chroma_source_chunks"

# Model
DEFAULT_LLM = "claude-sonnet-4-6"
FALLBACK_LLM = "gpt-4o-mini"
EMBED_MODEL = "all-MiniLM-L6-v2"

# Threshold'lar
VECTOR_SIM_THRESHOLD = 0.70   # Project voting
MIN_VECTOR_HITS = 3            # Minimum hit sayısı
MAX_NODES_IN_CONTEXT = 10      # LLM context için
MAX_CHARS_IN_CONTEXT = 12000   # LLM context boyutu
```

---

*Bu döküman `2026-02-25` tarihinde oluşturulmuştur. Son güncelleme: Robustness 0.839/A, 20q 0.796/A.*
