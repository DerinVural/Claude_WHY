# FPGA RAG v2 — Güncel Mimari Durum Raporu

**Tarih:** 2026-02-27
**Model:** claude-sonnet-4-6
**Versiyon:** RAG v2 (4-Store Federated)

---

## 1. Sistem Genel Bakış

```
┌─────────────────────────────────────────────────────────────────────┐
│                     FPGA RAG v2 — 4-Store Federated Query           │
│                                                                     │
│  Kullanıcı sorusu (TR/EN)                                           │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────────┐                                                │
│  │  QueryRouter    │ ← 5 tip: WHAT / HOW / WHY / TRACE / CROSSREF  │
│  │  (796 satır)    │ ← 3-tier project filter (both/text/vector)     │
│  └────────┬────────┘                                                │
│           │                                                         │
│    ┌──────┴──────────────────────────────────┐                      │
│    │              4 STORE                    │                      │
│    ▼              ▼            ▼             ▼                      │
│ VectorStore  GraphStore  SourceChunk    ReqTree                     │
│ (155 node)  (496 edge)  (229 chunk)   (BFS expand)                 │
│    │              │            │             │                      │
│    └──────────────┴────────────┴─────────────┘                      │
│                        │                                            │
│                        ▼                                            │
│            ┌───────────────────────┐                                │
│            │  HallucinationGate    │ ← 6 katman                     │
│            │  + GroundingChecker   │ ← LLM post-hoc verify          │
│            └───────────┬───────────┘                                │
│                        │                                            │
│                        ▼                                            │
│            ResponseBuilder → LLM (claude-sonnet-4-6)               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Sayısal Durum

### 2.1 Kod Tabanı

| Dosya | Satır | Rol |
|-------|-------|-----|
| `src/rag_v2/source_chunk_store.py` | 1065 | 4. store: kaynak dosya chunklama + semantic arama |
| `src/rag_v2/query_router.py` | 796 | Ana yönlendirici, 5 tip, 4-store federasyonu |
| `src/rag_v2/matching_engine.py` | 560 | REQ→COMP otomatik bağlantı (5 strateji) |
| `app_v2.py` | 547 | UI + pipeline orkestratörü |
| `src/rag_v2/cross_reference_detector.py` | 432 | Çapraz-proje benzerlik/çelişki tespiti |
| `src/rag_v2/hallucination_gate.py` | 350 | 6-katman anti-hallucination |
| `src/rag_v2/vector_store_v2.py` | 298 | ChromaDB graph node wrapper |
| `src/rag_v2/graph_store.py` | 296 | NetworkX DiGraph FPGA-domain API |
| `src/rag_v2/response_builder.py` | 291 | LLM context builder (max 14K char) |
| `src/rag_v2/loader.py` | 251 | Graph + vector store yükleyici |
| `src/rag_v2/grounding_checker.py` | 166 | LLM cevap doğrulama |
| **TOPLAM** | **5382** | |

### 2.2 Veritabanları

| Store | Boyut | Kayıt | İçerik |
|-------|-------|-------|--------|
| `db/chroma_graph_nodes/` | 3.4 MB | 155 node | Graph node embedding'leri |
| `db/chroma_source_chunks/` | 11 MB | 229 chunk | Kaynak kod parçaları |
| `db/graph/fpga_rag_v2_graph.json` | 260 KB | 155 node / 496 edge | Bilgi grafiği |

### 2.3 Graf Yapısı

| Node Tipi | Sayı | | Edge Tipi | Sayı |
|-----------|------|-|-----------|------|
| REQUIREMENT | 31 | | VERIFIED_BY | 155 |
| COMPONENT | 30 | | IMPLEMENTS | 149 |
| EVIDENCE | 21 | | CONSTRAINED_BY | 102 |
| SOURCE_DOC | 20 | | DECOMPOSES_TO | 30 |
| ISSUE | 14 | | DEPENDS_ON | 19 |
| CONSTRAINT | 13 | | REUSES_PATTERN | 13 |
| PATTERN | 12 | | MOTIVATED_BY | 11 |
| DECISION | 12 | | ANALOGOUS_TO | 8 |
| PROJECT | 2 | | CONTRADICTS | 1 |
| **TOPLAM** | **155** | | **TOPLAM** | **496** |

### 2.4 Source Chunk Dağılımı

| Proje | Chunk | | Dosya Tipi | Chunk |
|-------|-------|-|------------|-------|
| PROJECT-A (Nexys A7 DMA Audio) | 117 | | `.tcl` | 90 |
| PROJECT-B (Nexys Video GPIO) | 112 | | `.xdc` | 57 |
| | | | `.c` | 46 |
| | | | `.md` | 30 |
| | | | `.verilog` | 4 |

**En yoğun dosyalar:**

| Dosya | Chunk | Proje |
|-------|-------|-------|
| `helloworld.c` | 40 | PROJECT-A |
| `design_1.tcl` | 39 | PROJECT-A |
| `SYNTHESIS_RESULTS.md` | 30 | PROJECT-B |
| `Nexys-Video-Master.xdc` | 30 | PROJECT-B |
| `Nexys-A7-100T-Master.xdc` | 26 | PROJECT-A |
| `add_axi_gpio.tcl` | 13 | PROJECT-B |
| `create_axi_with_xdc.tcl` | 10 | PROJECT-B |

---

## 3. Güncel Başarı Metrikleri

| Test | Skor | Not |
|------|------|-----|
| 20-Question Benchmark | **0.926 / A** | 20 soru, project-aware |
| Robustness (A–E tier) | **0.940 / A** | A=1.00, B=0.97, C=0.91, D=0.77, E=1.00 |
| Blind Benchmark v2 | **0.918 / A** | IP=0.98, RTL=1.00, C=0.98, XDC=1.00, Cross=0.78, Trap=0.50 |

**Güçlü alanlar:** RTL, C Advanced, XDC, Robustness A+B+E
**Zayıf alanlar:** Cross-project (0.77–0.78), Trap responses (0.50), Robustness D-tier (0.77)

---

## 4. Mimari Bileşenler — Detay

### 4.1 QueryRouter — Sorgu Yönlendirme Mantığı

```
5 Query Tipi:
  WHAT   → "ne", "nedir", "hangi"     → 4 store paralel
  HOW    → "nasıl", "çalış"           → Vector (COMPONENT/PATTERN) + graph + source
  WHY    → "neden", "karar", "rationale" → Vector (DECISION) + MOTIVATED_BY edges
  TRACE  → "zincir\w+", "izle\w+"    → Vector + IMPLEMENTS/DEPENDS_ON traversal
  CROSSREF → "karşılaştır", "iki proje", "arasındaki" → Her iki proje, no filter

3-Tier Project Resolution:
  Tier 1: _BOTH_PROJECTS_RE match → project=None (iki proje birden)
  Tier 2: _TEXT_PROJECT_SIGNALS   → keyword eşleşmesi (nexys video → PROJECT-B)
  Tier 3: _infer_project()        → vector voting (%70 threshold)
```

### 4.2 SourceChunkStore — Chunklama Stratejileri

| Dosya Tipi | Strateji | Özellik |
|------------|----------|---------|
| `.v` / `.sv` | Module boundary | `module...endmodule` blokları |
| `.c` / `.cpp` | Function + struct | Brace-depth matching, header pinning |
| `.h` / `.hpp` | Header bloklar | typedef struct sınırları, includes/defines ayrı |
| `.xdc` | Section grupları | `##` veya `#`+büyükharf (her subsection ayrı chunk) |
| `.tcl` | IP blok adımları | BD-TCL: IP başına isimli chunk (axi_dma_0, clk_wiz_0) |
| Default | Fixed overlap | 3000 char, 300 char overlap |

**C-header pinning:** `includes_defines`, `global_vars`, `typedef_struct_*` chunk'ları her zaman
context'e eklenir — semantic rank ne olursa olsun.

**File-name boost:** `search_within_file(query, stem, n=8)` — dosya adı sorgu içindeyse
o dosyanın semantic top-8'i çekilir, context bloat önlenir.

### 4.3 HallucinationGate — 6 Katman

```
Layer 1: Evidence Gate         → İddia var, evidence node yok → FAIL
Layer 2: Confidence Prop       → Zincir: en zayıf halka = zincir güveni
Layer 3: Coverage Gap          → REQ node'un IMPLEMENTS edge'i yok → WARNING
Layer 4: PARSE_UNCERTAIN flag  → Otomatik parse edilmiş → MEDIUM confidence
Layer 5: SUPERSEDES filter     → Eski/geçersiz node'ları dışla
Layer 6: CONTRADICTS check     → Çelişen edge'leri tespit et, uyar
```

### 4.4 LLM Konfigürasyonu

```
Default model : claude-sonnet-4-6
Fallback      : gpt-4o-mini (Anthropic credits yetersizse)
Context budget: 14.000 karakter max
               60% source chunks / 40% graph nodes oranı
Max nodes     : 12 (context'e alınan)
n_vector_hits : 6 (graph node vector search)
n_source_hits : 10 (source chunk search)
```

---

## 5. Mimari Güçlü Taraflar

**4-Store Federasyonu çalışıyor.**
Her store farklı soru tipine cevap veriyor: semantic benzerlik, yapısal gezinme, gerçek implementasyon detayı, hiyerarşik decomposition. Hiçbiri tek başına yeterli değil, birlikte güçlü.

**6-Katman HallucinationGate sağlam.**
Yanlış cevap yerine "bilmiyorum + uyarı" üretiyor. Confidence zinciri sistemik bir güven metriği sağlıyor.

**Türkçe-bilinçli routing.**
Morfolojik suffix tolerans (`\bzincir\w+`), negasyon kelimeleri, cross-project detection — Türkçe sorgularda skor düşmüyor.

**File-name boost + C-header pinning.**
Dosya bazlı büyük chunk kümelerinde önemli bilgilerin kaybolmaması için iki ayrı güvenlik ağı var.

**REQ → COMP coverage %100.**
31 REQUIREMENT node'un tamamının IMPLEMENTS edge'i var — coverage gap sıfır.

---

## 6. Mimari Zayıf Taraflar

### Zayıflık A — Graph Açıklamaları Kaynak Koddan Sapabiliyor

```
Agent → graph node description yazar (bir kere)
Kaynak dosya → güncellenir veya değeri farklıydı
LLM → graph açıklamasını önce okuyor → yanlış değeri alıyor

Örnek: FIFO depth "512" yazılmış, gerçek 4096
       DMA burst size eksik yazılmış, gerçek 256
```

Bu sınıfın her yeni instance'ı şu an ayrı bir düzeltme gerektiriyor.

### Zayıflık B — Context Trust Sırası Suboptimal

LLM şu an graph açıklamasını kaynak chunk'tan **önce** görüyor. Graph yanlış değer içerdiğinde, kaynak chunk doğruyu gösteren olsa bile graph'ı referans alıyor.

### Zayıflık C — Çapraz Dosya Reasoning Eksik

```
design_1.tcl  → clk_wiz_0: 100 MHz çıkışı
helloworld.c  → MIG init: 100 MHz bekleniyor

"Bu iki değer uyuşuyor mu?" → RAG cevap veremez
```

Retrieval sorunu değil, LLM reasoning sınırı. Hiçbir RAG sistemi bu sınıfı tam çözmüyor.

### Zayıflık D — Trap Response Template (%50)

LLM "bilgi yok" derken trap keyword'leri (CS4344, FreeRTOS, Ethernet) sayıyor. Evaluator bunu PARTIAL kabul ediyor. Kök neden: system prompt'ta "bilinmeyen konuları say" kuralı yok.

### Zayıflık E — CROSSREF Dengeli Chunk Garantisi Yok

`search(query, project_filter=None, n=10)` semantik olarak daha güçlü projeye 8 chunk, zayıf projeye 2 chunk veriyor. D-tier cross-project sorularında dengesizlik.

---

## 7. Önerilen İyileştirmeler

### İyileştirme 1 — Parser Agent (Öncelik: Yüksek, Etki: Büyük)

**Yeni agent:** `scripts/extract_facts_agent.py`

```
index_source_files.py çalışınca otomatik tetiklenir:

  XDC Parser:
    uncommented set_property satırları → pin atama dict'i
    {"PWM_AUDIO_0_pwm": {"PACKAGE_PIN":"A11","IOSTANDARD":"LVCMOS33"}}

  BD-TCL Parser:
    create_bd_cell + set_property blokları → IP config dict'i
    {"axi_dma_0": {"C_MM2S_BURST_SIZE":"256","C_INCLUDE_SG":"0"}}

  C Parser:
    #define sabitler → sabit değer dict'i
    {"DMA_RESET_TIMEOUT_CNT":"1000000","DMA_BUSY_TIMEOUT_CNT":"2000000"}

  Graph node'larına "auto_params" alanı olarak yaz (auto_generated: true)
```

**Sonuç:** Graph description yanlış olsa bile `auto_params` alanından doğru değer okunur. FIFO depth / burst size / pin atama gap sınıfı kapanır.

### İyileştirme 2 — Context Trust Sırası Düzeltmesi (Öncelik: Yüksek, Etki: Orta)

**Dosya:** `src/rag_v2/response_builder.py`

```
Şu an:  [GRAPH description] önce → [SOURCE chunk] sonra
Olması: [SOURCE chunk] önce      → [GRAPH: sadece topoloji] sonra
```

LLM source chunk'ı referans alır, graph sadece "bu IP şuna bağlı" ilişkisini verir. Tek bir context sıralama değişikliği.

### İyileştirme 3 — Trap Response Template Fix (Öncelik: Orta, Etki: Trap +30p)

**Dosya:** `src/rag_v2/response_builder.py` → `FPGA_RAG_SYSTEM_PROMPT`

```
Eklenecek kural:
  Bilgi mevcut değilse sadece şunu söyle:
  "Bu bilgi mevcut kaynaklarda yer almıyor."
  Konuyla ilgili spesifik teknoloji adı (CS4344, FreeRTOS vb.) SAYMA.
  Analoji veya tahmin üretme.
```

### İyileştirme 4 — Dengeli CROSSREF Chunk Garantisi (Öncelik: Orta, Etki: D-tier +15p)

**Dosya:** `src/rag_v2/query_router.py` → `_route_crossref()`

```python
# Şu an: search(q, project_filter=None, n=10)  → semantik baskın proje kazanır
# Olması gereken:
if project_filter is None:
    chunks_a = source_chunk_store.search(q, project_filter='PROJECT-A', n=5)
    chunks_b = source_chunk_store.search(q, project_filter='PROJECT-B', n=5)
    chunks = chunks_a + chunks_b   # garantili denge
```

### İyileştirme 5 — Graph Sync Agent (Öncelik: Düşük, Etki: Uzun Vadeli)

**Yeni agent:** `scripts/graph_sync_agent.py`

```
Tetikleme: extract_facts_agent.py çalıştıktan sonra

  1. Parser çıktısı vs graph node description karşılaştır
  2. auto_params alanını güncelle (otomatik)
  3. Büyük sapma varsa → log'a yaz (review kuyruğu)
  4. VectorStore yeniden indeksle

Sonuç: Graph hiçbir zaman kaynak koddan sapmaz
```

---

## 8. Hedef Agent Pipeline Mimarisi

```
YENİ PROJE EKLENDİĞİNDE
        │
        ▼
┌───────────────────┐
│  Indexer Agent    │  index_source_files.py
└────────┬──────────┘
         │
    ┌────┴──────────────────┬────────────────────┐
    ▼                       ▼                    ▼
Parser Agent          Chunker Agent        Graph Sync Agent
(TCL/XDC/C           (domain-aware        (auto_params +
 parametre           split stratejisi)     description sync)
 extraction)
    │                       │                    │
    └───────────────────────┴────────────────────┘
                            │
                ┌───────────▼───────────┐
                │    Eval Agent         │  test_robustness.py
                │  (otomatik regresyon) │  test_blind_benchmark_v2.py
                └───────────┬───────────┘
                            │
                     Skor düştüyse:
                ┌───────────▼───────────┐
                │  Gap Analysis Agent   │  fix_architecture_gaps.py
                └───────────────────────┘
```

**Mevcut durum:**

| Agent | Durum | Not |
|-------|-------|-----|
| Indexer Agent | ✅ Var | `index_source_files.py` |
| Chunker Agent | ✅ Var | Domain-specific, C-header pinning |
| Parser Agent | ❌ Eksik | **En kritik boşluk** |
| Graph Sync Agent | ❌ Eksik | Parser'a bağımlı |
| Eval Agent | ✅ Var | İki benchmark script |
| Gap Analysis Agent | ⚠️ Kısmi | `fix_architecture_gaps.py` sınırlı |

---

## 9. Öncelik Matrisi

| Öncelik | İyileştirme | Beklenen Etki | Efor |
|---------|-------------|---------------|------|
| 🔴 1 | Parser Agent (TCL/XDC/C extraction) | Graph drift gap sınıfı kapanır | Orta |
| 🔴 2 | Context trust sırası: source önce | Cross/Robustness +2–3p | Düşük |
| 🟡 3 | Trap response template fix | Trap 0.50 → 0.80+ | Düşük |
| 🟡 4 | CROSSREF dengeli chunk garantisi | D-tier +15p | Düşük |
| 🟢 5 | Graph Sync Agent | Uzun vadeli sıfır bakım | Yüksek |

**En hızlı kazanım:** İyileştirme 2 ve 3 — kod değişikliği küçük, skor etkisi ölçülebilir, bugün yapılabilir.

**Strateji dönüşümü:** İyileştirme 1 ve 5 — graph'ı "truth source" olmaktan çıkarır, kaynak dosyalar ground truth olur, graph sadece ilişki haritası kalır. Yeni proje eklemek artık sadece dosya göstermek anlamına gelir.

---

## 10. Kök Mimari İlkeler (Bu Sistemden Öğrenilenler)

1. **Kaynak kod ground truth'tur** — graph açıklaması değil. LLM'in önce kaynak chunk'ı okuması gerekir.

2. **Parametre değerleri parser ile çıkarılmalı** — LLM veya insan agent tarafından elle yazılmamalı.

3. **Graph'ta sadece ilişkiler ve hiyerarşi tutulmalı** — topoloji, REQ ağacı, DECISION rationale, cross-project analogy.

4. **Chunklama semantik birim sınırlarında olmalı** — dosya başlangıç/bitiş değil, `module/endmodule`, `proc`, `typedef struct` gibi anlam sınırları.

5. **Büyük dosyalar için `search_within_file()`** — tüm dosyayı context'e atmak yerine semantik top-N seç.

6. **Anti-hallucination çok katmanlı olmalı** — retrieval kalitesi + LLM post-verification + confidence propagation birlikte çalışmalı.

7. **Değerlendirme süreci retrieval sisteminin parçası** — her yeni soru tipi potansiyel gap. Eval agent pipeline'ın sonunda değil, içinde olmalı.

---

*Rapor sonu. Güncel kaynak: `db/graph/fpga_rag_v2_graph.json` + `db/chroma_source_chunks/`*
