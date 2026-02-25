# FPGA RAG v2 — Altyapı Sorunları Teknik Analiz Raporu

**Tarih:** 2026-02-23
**Kapsam:** Sorgu altyapısı, DB mimarisi, anti-hallüsinasyon katmanları

---

## SORU 1: Neden Veri Üretiliyor Ama Sorgulanamıyor?

### Kök Neden: Commit Pipeline ile Query Pipeline Arasında Köprü Yok

Sistem şu anda iki ayrı, birbirine bağlanmamış parçadan oluşuyor:

```
                    ┌─────────────────────────────────────┐
  ÜRETIM PARÇASI    │  pipeline_graph.json (119 KB)        │
  (çalışıyor)       │  → 142 node, ~171 edge               │
                    │  → PROJECT, COMPONENT, REQUIREMENT   │
                    │  → IMPLEMENTS, CONSTRAINED_BY...      │
                    └──────────────┬──────────────────────┘
                                   │
                          ❌ KÖPRܠYOK
                                   │
                    ┌──────────────▼──────────────────────┐
  SORGU PARÇASI     │  ChromaDB (chroma_db/)               │
  (çalışıyor)       │  → 4.152.529 chunk                   │
                    │  → Düz metin, kaynak dosya meta       │
                    │  → rag_pipeline.py / app.py           │
                    └─────────────────────────────────────┘
```

`pipeline_graph.json` hiçbir zaman:
- ChromaDB'ye yüklenmedi
- Graph DB'ye aktarılmadı
- Herhangi bir sorgu motoruna bağlanmadı

Sonuç: "COMP-A-axis2fifo_0 hangi requirement'ı implement ediyor?" sorusu sorulduğunda sistem üretilen JSON'ı değil, ChromaDB'deki ham `axis2fifo.v` dosya metnini döner. Graph yapısı görünmez.

---

### Sorun 1a: Embedding Boyut Uyumsuzluğu

Sistemde iki farklı embedding modeli paralel çalışıyor ve **birbirleriyle uyumsuzlar**:

```
Model                    Boyut   Nerede Kullanılıyor
─────────────────────────────────────────────────────────────
all-mpnet-base-v2         768    app.py, chat.py, train_organized.py
                                 → Üretim ChromaDB bu modelle dolu
gemini-embedding-001     3072    src/rag_pipeline.py (özgün RAGPipeline)
                                 → Bu modelle sorgu yapılırsa BOYUT HATASI
```

**Pratik etki:**
```python
# app.py (çalışıyor — 768 boyut):
embedder = SentenceEmbeddings("all-mpnet-base-v2")
results = chroma.query(embedder.embed(question))  # ✅

# rag_pipeline.py (çalışmaz — 3072 boyut ChromaDB'ye 768 boyut verileri var):
embedder = GoogleGenAIEmbeddings("gemini-embedding-001")
results = chroma.query(embedder.embed(question))  # ❌ boyut hatası
```

ChromaDB HNSW index, boyut değişince yeni belgeleri kabul etmez ama eski belgeleri sorgularken hatalı sonuç verir veya exception fırlatır.

---

### Sorun 1b: Düz Metin İndeksleme — Yapısal Bilgi Kaybolmuş

`code_loader.py` kaynak dosyaları **ham metin** olarak yükliyor:

```python
# Mevcut: src/utils/code_loader.py
with open(file_path, 'r') as f:
    content = f.read()                  # Tüm dosya tek metin bloğu
chunks = chunker.split(content)          # Sadece boyuta göre parçala
chroma.add(chunks, metadata={"file": path})  # Kaydet
```

Bu yaklaşımla `axis2fifo.v` dosyasının içeriği `axis2fifo` → `DMA-REQ-L2-004` bağlantısı olmadan yükleniyor. Sorgu yapıldığında:

```
Soru: "axis2fifo hangi AXI-Stream gereksinimini karşılıyor?"

Mevcut yanıt (ChromaDB ham metin):
  "axis2fifo.v içeriği: assign axis_tready = ~fifo_full; ..."
  → LLM tahmin eder, IMPLEMENTS kenarını bilmez

Beklenen yanıt (Graph + Vector):
  "M-002: COMP-A-axis2fifo_0 → DMA-REQ-L1-006 (HIGH, semantic+evidence)"
  → Kanıta dayalı, LLM tahmin etmez
```

---

### Sorun 1c: pipeline_graph.json İçin Tüketici Script Yok

```
data/fpga_rag_v2_output/
├── pipeline_graph.json     ← üretildi ✅
├── pipeline_report.md      ← üretildi ✅
└── fpga_rag_v2_detayli_analiz.md ← üretildi ✅

scripts/
├── train_organized.py      ← ChromaDB'ye yükler (ham metin)
├── chat.py                 ← ChromaDB'den sorgular
└── (graph_loader.py)       ← MEVCUT DEĞİL ❌
```

`pipeline_graph.json`'ı parse edip Graph DB veya ChromaDB'ye yükleyecek hiçbir script yok.

---

## SORU 2: Neden Düz JSON Kullanılıyor? Graph DB / Vector DB Neden Yok?

### Mevcut Durum Haritası

```
MİMARİ DOKÜMANI (fpga_rag_architecture_v2.md) TASARIMI:

  ┌──────────────────────────────────────────────────────┐
  │                   Query Router                        │
  │  Soru → [Tip Sınıflandır: What/How/Why/Trace]        │
  │              │          │         │                   │
  │         Vector DB   Graph DB   Req Tree               │
  │         (semantic)  (struct.)  (decom.)               │
  │              └──────────┴─────────┘                   │
  │                         ↓                             │
  │              Anti-Hallüsinasyon Kapıları              │
  │                         ↓                             │
  │                 Yapılandırılmış Yanıt                 │
  └──────────────────────────────────────────────────────┘

GERÇEK UYGULAMA:

  ┌──────────────────────────────────────────────────────┐
  │  Soru → SentenceEmbeddings(768) → ChromaDB.query()   │
  │              ↓                                        │
  │  Top-K chunk metni → Gemini prompt'a ekle            │
  │              ↓                                        │
  │  Yanıt üret (sistem promptu: "sadece kaynaktan")     │
  └──────────────────────────────────────────────────────┘
```

### Neden Graph DB Yok?

#### Teknik Bariyer 1: Seçilmemiş Araç

| Seçenek | Durum | Sorun |
|---------|-------|-------|
| Neo4j | Kod yok | Kurulum + lisans karmaşıklığı |
| NetworkX | Kod yok | Bellek içi — 4M chunk ile ölçeklenmez |
| ArangoDB | Kod yok | Ek servis yönetimi |
| DGL/PyG | Kod yok | GNN odaklı — query için ağır |
| **JSON dosya** | **Mevcut** | **Basit ama sorgulanamaz** |

`pipeline_graph.json` aslında "Graph DB commit-ready format" olarak tasarlandı — bir Graph DB'ye yüklenecek intermediate format. Ama yükleme adımı hiç yazılmadı.

#### Teknik Bariyer 2: BigQuery Planlandı Ama Bağlanmadı

```python
# src/gcp/bigquery_client.py — KOD VAR, BAĞLANTI YOK
class BigQueryVectorStore:
    def __init__(self, project_id, dataset_id, table_id):
        self.client = bigquery.Client(project=project_id)  # GCP kimlik bilgisi gerekli
```

`.env` dosyasında:
```
GOOGLE_API_KEY=your-api-key-here   # placeholder
GCP_PROJECT_ID=your-project-id    # placeholder
```

GCP yapılandırması tamamlanmadığından BigQuery hiç kullanılmadı. Sistem yerel ChromaDB'ye geçti, ama Graph mantığı hiç eklenmedi.

#### Teknik Bariyer 3: İki Farklı ChromaDB Collection Sorunu

```python
# Mevcut: Her şey tek "documents" collection'ında
collection = chroma.get_or_create_collection("documents")

# Gerekli: Tip bazlı ayrım
collection_chunks   = chroma.get_or_create_collection("fpga_chunks")
collection_nodes    = chroma.get_or_create_collection("graph_nodes")
collection_req_text = chroma.get_or_create_collection("requirements")
```

Tek collection'da 4.15M chunk var. Graph node'ları (142 adet) buna eklenirse sorgular karışır — cosine similarity "COMP-A-axis2fifo_0" ile "axis2fifo modülü DMA ses akışını yönetir" arasında anlamsız benzerlik puanı hesaplar.

---

### Neden Sadece JSON?

JSON'un seçilmesinin pratik nedenleri:

```
1. HIZLI PROTOTIPLEME
   Herhangi bir DB kurulumu gerektirmez.
   Python'da json.dumps() — sıfır bağımlılık.

2. TAŞINABILIRLIK
   Üretim ortamında chromadb, sentencetransformers,
   google-generativeai zaten yeterince karmaşık.
   Bir Graph DB (Neo4j) ek container/servis demek.

3. HUMAN-READABLE
   pipeline_graph.json + pipeline_report.md doğrudan
   okunabilir. Mühendis inceleyip düzeltebilir.
   → Bu RAG v2'nin "provenance transparency" prensibi.

4. GRAPH DB SEÇMEME KÖK NEDENİ
   Mimari dokümanda Graph DB gerekliliği tanımlandı
   ama hangi Graph DB, nasıl kurulacak, nasıl sorgulanacak
   belirtilmedi. Uygulama boşlukta kaldı.
```

---

### Neden Mevcut ChromaDB Yetersiz?

```
ChromaDB başarılı olduğu durumlar:
  ✅ "FIFO backpressure nasıl çalışır?" → axis2fifo.v ham metni döner
  ✅ "MIG 7-Series DDR2 nedir?" → PDF chunk döner
  ✅ "AXI DMA parametreleri neler?" → design_1.tcl chunk döner

ChromaDB yetersiz kaldığı durumlar:
  ❌ "axis2fifo hangi isterl implement ediyor?"
     → Graph kenarı olmadan cevaplanamaz

  ❌ "DMA-REQ-L2-003 neden karşılanmıyor?"
     → Requirement tree ve Coverage Gap olmadan cevaplanamaz

  ❌ "tone_generator neden devre dışı?" (why sorusu)
     → DECISION node olmadan LLM tahmin eder (hallüsinasyon riski)

  ❌ "FPGA part 50T mi 100T mi?" (CONFLICT)
     → ISSUE node olmadan çakışan iki chunk döner, LLM karıştırır

  ❌ "Bu proje ile axi_example arasındaki fark ne?"
     → ANALOGOUS_TO kenarı olmadan semantik benzerlikten tahmin eder
```

---

## SORU 3: Neden Sadece 2 Anti-Hallüsinasyon Katmanı Aktif?

### Gerçek Durum: 4 Aktif, 8 Tasarım Aşamasında

Mimari dokümanda **10 mekanizma** tanımlanmış. Gerçekte **4'ü aktif**:

```
                    DURUM TABLOSU
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Katman                          Aktif?  Uygulama
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Source-Grounded Prompt       ✅      gemini_generator.py sistem promptu
2. Mandatory Retrieval Context  ✅      Yapısal: generate() her zaman context alır
3. Empty-DB Guard               ✅      is_empty() kontrolü → yanıt reddedilir
4. Source Attribution UI        ✅      app.py'de dosya adı + benzerlik skoru

5. Evidence Gate                ❌      Graph DB yok → uygulanamaz
6. Confidence Propagation       ❌      Node confidence değerleri JSON'da var ama
                                        sorgu zincirinde propagasyon kodu yok
7. Version/Context Filter       ❌      SUPERSEDES kenarı → Graph DB gerekli
8. Tool-Verified Loop           ❌      Vivado entegrasyonu yok
9. Contradiction Detection      ❌      CONTRADICTS kenarı → Graph DB gerekli
10. PARSE_UNCERTAIN Flagging     ❌      Üretimde etiket var (JSON'da),
                                        sorgu katmanında kontrol yok
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

> **Kullanıcı neden "2" görüyor?** Muhtemelen 1 ve 2 numaralı katmanlar birleşik tek mekanizma gibi görünüyor (her ikisi de "LLM'e context ver" prensibine dayanıyor). 3 ve 4 arka planda çalışıyor, fark edilmesi güç.

---

### Katman 1: Source-Grounded Prompt (Aktif ✅ — Zayıf)

```python
# src/rag/gemini_generator.py
system_prompt = """
Verilen kaynak belgelerden yalnızca bilgileri kullanın.
Kaynaklarda bilgi yoksa bunu açıkça belirtin.
Kaynak kullanırken dosya adını belirtin.
"""
```

**Neden zayıf:**
- LLM'in talimatı dinlemesi **garanti değil**
- Gemini-2.0-flash önceki eğitiminden FPGA bilgisi çıkarabilir
- "Kaynaklarda yoksa belirt" kural olarak yazılı ama doğrulama mekanizması yok
- Hiçbir mekanik engel yok

**Güçlü olması için:**
```python
# Gerekli ek: çıktıdan kaynak referansı parse et
# Referans yok → yanıt reddet
if not extract_citations(answer):
    return "YANIT REDDEDİLDİ: Kaynak referansı bulunamadı."
```

---

### Katman 2: Mandatory Retrieval Context (Aktif ✅ — Orta)

```python
# src/rag_pipeline.py
def query(self, question, top_k=3):
    if self.vector_store.is_empty():
        return {"answer": "Database boş."}     # Guard
    embedding = self.embedder.embed(question)
    results = self.vector_store.query(embedding, top_k)
    # LLM her zaman context alır — context'siz generate() çağrısı yok
    answer = self.generator.generate(question, context=results)
```

**Güç:** LLM hiçbir zaman boş context ile çağrılmıyor. Bu yapısal garanti.

**Zayıflık:** Retrieved chunk'lar **ilgisiz** olabilir (cosine similarity düşük). Sistem similarity threshold uygulamıyor:

```python
# app.py'de eşik YOK:
results = chroma.query(embedding, n_results=top_k)
# Benzerlik 0.1 bile olsa chunk LLM'e gönderiliyor
```

`src/rag/retriever.py`'de (KULLANILMIYOR) bir threshold var:
```python
threshold: float = 0.7
results = [r for r in results if r['similarity'] >= threshold]
```
Ama bu BigQuery retriever — hiç kullanılmıyor.

---

### Katman 3: Empty-DB Guard (Aktif ✅ — Etkili)

```python
# src/vectorstore/chroma_store.py
def is_empty(self) -> bool:
    return self.collection.count() == 0
```

Sadece boş DB durumunu yakalar. Prod'da DB 4.15M chunk içeriyor, bu guard hiç tetiklenmeyecek.

---

### Katman 4: Source Attribution UI (Aktif ✅ — Pasif Koruma)

```python
# app.py
for source in result['sources']:
    st.expander(f"📄 {source['metadata']['filename']} — {source['similarity']:.1%}")
```

Renk kodlaması:
```python
color = "🟢" if sim >= 0.70 else ("🟡" if sim >= 0.50 else "🔴")
```

**Güç:** Kullanıcı kaynağı görebilir, yanıtı doğrulayabilir.
**Zayıflık:** Pasif — sistem yanıtı kısıtlamaz, sadece bilgi gösterir.

---

### Neden 6 Katman Uygulanamadı?

#### Katman 5: Evidence Gate (❌ Graph DB gerekli)

Tasarım:
```
Her LLM iddiası → JSON'daki node ID'ye bağlanmalı
"axis_tlast bug var" → EVID-A-003 → tone_generator.v:69

Uygulama gereksinimi:
  graph.get_node("EVID-A-003") → {content: "assign axis_tlast = 1'b1", line: 69}
  assert evidence_supports(claim, evidence_node)
```

**Neden yok:** Graph DB olmadan `graph.get_node()` çağrısı yapılamaz. JSON dosyası üzerinde realtime sorgu için Python dict olarak load edilmeli (119KB'yi her sorguda) ve bir eşleştirme algoritması yazılmalı — bu yazılmadı.

---

#### Katman 6: Confidence Propagation (❌ Traversal kodu yok)

Tasarım:
```
Sorgu: "axi_dma_0 → DMA-REQ-L2-005 güvenilirliği?"

  M-006 kenarı: confidence=HIGH (direct match)
  DMA-REQ-L2-005 node: confidence=HIGH
  Zincir: HIGH ∧ HIGH = HIGH → yanıt HIGH güvenle verilir

  Karşı örnek:
  tone_generator → DMA-REQ-L2-003: confidence=HIGH (component exists)
  PARSE_UNCERTAIN_WHY_DISABLED flag var
  Zincir: HIGH ∧ PARSE_UNCERTAIN = MEDIUM → yanıtta uyarı ekle
```

Bu traversal mantığı JSON'da veriler mevcut (her node'da `confidence` alanı var) ama sorgu motoruna entegre edilmedi.

---

#### Katman 7: Version/Context Filter (❌ SUPERSEDES kenarı yok)

ISTER v2.0 → v2.1 güncellendi. Eski yanıt:
> "fpga_part: xc7a100tcsg324-1"

Yeni yanıt (UPD-001 sonrası):
> "fpga_part_intended: xc7a100tcsg324-1, fpga_part_actual_tcl: xc7a50ticsg324-1L"

ChromaDB her iki versiyonu da depoluyor (eğer her ikisi de yüklendiyse). Sorgu ikisini de döner. SUPERSEDES kenarı olmadan sistem hangisinin güncel olduğunu bilemez.

---

#### Katman 8: Tool-Verified Loop (❌ Vivado entegrasyonu yok)

Tasarım:
```python
# Timing iddiası varsa Vivado'ya doğrulat:
if "WNS" in claim or "timing" in claim:
    vivado_result = run_vivado_timing_check(design_files)
    assert vivado_result.wns > 0, "Timing ihlali: LLM yanıtı hatalı"
```

Vivado'nun makinede kurulu olması gerekir. Hiçbir Vivado entegrasyon kodu yok.

---

#### Katman 9: Contradiction Detection (❌ Graph DB gerekli)

FPGA part çakışması örneği:
```
ChromaDB'de iki chunk:
  Chunk 1 (README.md): "Nexys A7-100T"
  Chunk 2 (project_info.tcl): "xc7a50ticsg324-1L (50T)"

Mevcut durum: Her ikisi de top-K'ya girebilir → LLM karıştırır veya
              sadece birini seçer → yanlış yanıt

Graph'ta (ISSUE-A-001 varsa):
  CONTRADICTS(CONST_A_PART_ACTUAL, CONST_A_PART_INTENDED)
  → Sorgu motoru "CONFLICT tespit edildi" uyarısı üretir
  → LLM her iki kaynağı da gösterir + çelişki notu ekler
```

---

## Özet: Ne Yapılmalı?

### Kısa Vadeli (Mevcut ChromaDB altyapısıyla — 1-2 gün)

```python
# 1. pipeline_graph.json'ı ChromaDB'ye yükle (ayrı collection)
# scripts/load_graph_to_chroma.py  (YAZILMAMALI)

import json, chromadb
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-mpnet-base-v2")
client = chromadb.PersistentClient("chroma_db/")
col = client.get_or_create_collection("graph_nodes")

with open("data/fpga_rag_v2_output/pipeline_graph.json") as f:
    graph = json.load(f)

for node in graph["nodes"]:
    text = f"{node['node_type']} {node.get('name','')} {node.get('description','')}"
    embedding = model.encode(text).tolist()
    col.add(ids=[node["node_id"]], embeddings=[embedding],
            documents=[json.dumps(node, ensure_ascii=False)],
            metadatas={"type": node["node_type"], "project": node.get("project","")})

# 2. Sorgu sırasında önce graph_nodes collection'ına bak
def query_with_graph(question, top_k=5):
    embedding = model.encode(question).tolist()
    # Yapısal context
    graph_results = graph_col.query(query_embeddings=[embedding], n_results=3)
    # Semantik context
    doc_results = doc_col.query(query_embeddings=[embedding], n_results=top_k)
    # Birleştir
    context = graph_results + doc_results
    return gemini.generate(question, context)
```

```python
# 3. Similarity threshold ekle
MIN_SIMILARITY = 0.45
results = [r for r in results if (1 - r["distance"]) >= MIN_SIMILARITY]
if not results:
    return {"answer": "Bu soruya güvenilir kaynak bulunamadı.", "sources": []}
```

```python
# 4. Embedding model tutarsızlığını düzelt
# Tüm scriptlerde tek model:
EMBEDDING_MODEL = "all-mpnet-base-v2"  # Prod DB bu modelle dolu
# rag_pipeline.py'de GoogleGenAIEmbeddings'i kaldır
```

---

### Orta Vadeli (Graph DB entegrasyonu — 1-2 hafta)

```
Önerilen minimal Graph DB seçimi: NetworkX + JSON persist

from networkx.readwrite import json_graph
import networkx as nx

G = nx.DiGraph()
# pipeline_graph.json'dan yükle
for node in graph["nodes"]:
    G.add_node(node["node_id"], **node)
for edge in graph["edges"]:
    G.add_edge(edge["from"], edge["to"], **edge)

# Sorgu örnekleri:
G.successors("COMP-A-axis2fifo_0")         # Hangi requirement'ları implement ediyor?
G.predecessors("DMA-REQ-L2-004")           # Bu requirement'ı kim implement ediyor?
nx.shortest_path(G, "EVID-A-003", "DMA-REQ-L2-003")  # Kanıt zinciri
```

Ölçek: 142 node + 171 edge → NetworkX için önemsiz boyut.
Production'da büyüdükçe: Neo4j veya Kuzu (embedded, Parquet tabanlı).

---

### Uzun Vadeli (Anti-Hallüsinasyon tüm katmanlar)

```
Öncelik sırası (etki/maliyet oranına göre):

1. [YÜKSEK ETKİ, DÜŞÜK MALİYET] Similarity threshold → 2 satır kod
2. [YÜKSEK ETKİ, DÜŞÜK MALİYET] Graph nodes → ChromaDB ek collection → ~50 satır
3. [YÜKSEK ETKİ, ORTA MALİYET]  NetworkX graph → Traversal sorguları → ~200 satır
4. [ORTA ETKİ, ORTA MALİYET]    Confidence propagation → Traversal sonucu confidence hesaplama
5. [ORTA ETKİ, YÜKSEK MALİYET] Citation extraction → Yanıtta kaynak referansı zorunlu
6. [DÜŞÜK ETKİ, YÜKSEK MALİYET] Tool-verified loop → Vivado subprocess integration
```

---

## Hızlı Referans

| Sorun | Kök Neden | Çözüm |
|-------|-----------|-------|
| Üretilen JSON sorgulanamıyor | Graph→ChromaDB yükleme scripti yok | `load_graph_to_chroma.py` yaz |
| Graph DB yok | Seçilmedi/tasarlandı ama uygulanmadı | NetworkX (başlangıç) → Neo4j |
| Embedding boyut uyumsuzluğu | rag_pipeline.py farklı model kullanıyor | Tüm scriptleri `all-mpnet-base-v2`'de unify et |
| 6 katman aktif değil | Graph DB olmadan uygulanamaz | Graph altyapısını kur → katmanlar sırayla aktif edilir |
| Similarity threshold yok | retriever.py (BigQuery) kullanılmıyor | app.py + chat.py'ye `MIN_SIM=0.45` ekle |
| İki embedding modeli | Prototip→prod geçişi yönetilmedi | EMBEDDING_MODEL sabitini tek yerden yönet |

---

*Bu rapor `/home/test123/GC-RAG-VIVADO-2/` kaynak kodu ve pipeline_graph.json doğrudan analizi ile üretilmiştir.*
