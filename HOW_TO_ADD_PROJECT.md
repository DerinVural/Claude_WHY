# Yeni Proje Ekleme Rehberi — FPGA RAG v2

RAG sistemine yeni bir FPGA projesi eklemek **4 adımdan** oluşur.
Her adım zorunludur; atlanırsa sistem o proje için eksik ya da hatalı yanıt verir.

---

## Hızlı Bakış

```
Adım 1 → index_source_files.py   (kaynak dosyaları chunk'la)
Adım 2 → add_new_knowledge_nodes.py benzeri script (graph node'ları ekle + kaydet)
Adım 3 → vector_store_v2.add_node() (yeni node'ları embedding'le)
Adım 4 → query_router.py _TEXT_PROJECT_SIGNALS (proje keyword'leri ekle)
```

---

## Adım 1 — Kaynak Dosyaları İndeksle (`SourceChunkStore`)

**Dosya:** `scripts/index_source_files.py`

`PROJECT_SOURCE_CATALOG` listesine yeni proje ekle:

```python
{
    "project": "yeni_proje_adi",          # snake_case, benzersiz
    "display_name": "Okunabilir İsim",
    "roots": [
        str(_ROOT / "data/code/yeni_proje"),   # kaynak dizin(ler)
    ],
    "include_exts": [".v", ".sv", ".c", ".h", ".xdc", ".tcl", ".md"],
    "exclude_patterns": [
        ".git", "__pycache__", ".cache", ".gen", ".runs",
        ".hw", ".ip_user_files",           # Vivado üretilen dosyalar
    ],
    "specific_files": [
        # roots dışında kalan ama dahil edilmesi gereken tek dosyalar
        str(_ROOT / "data/code/yeni_proje/proje.srcs/constrs_1/new/pins.xdc"),
    ],
    "file_node_map": {
        # chunk'a graph node_id bağlar (opsiyonel, ama retrieval kalitesini artırır)
        "top_module.v": ["COMP-yeni-top_module"],
        "design_1.tcl": ["COMP-yeni-axi_dma_0", "COMP-yeni-clk_wiz_0"],
    },
},
```

**Çalıştır:**
```bash
source .venv/bin/activate
python scripts/index_source_files.py          # incremental (eski chunk'lar korunur)
python scripts/index_source_files.py --reset  # sıfırdan (DİKKAT: tüm indexi siler)
python scripts/index_source_files.py --dry-run --verbose  # önce kontrol et
```

> **Not:** `exclude_patterns` içinde Vivado proje dizinleri (`.gen`, `.runs`, `.cache`) mutlaka olmalı.
> Aksi halde binlerce otomatik üretilmiş stub/netlist dosyası indexlenir.

---

## Adım 2 — Graph Node'larını Ekle (`GraphStore`)

`db/graph/fpga_rag_v2_graph.json` dosyasına Python ile node ve edge ekle.
**Mutlaka `gs.save()` çağır**, yoksa değişiklikler bellekte kalır.

```python
import sys; sys.path.insert(0, 'src')
from rag_v2.graph_store import GraphStore

gs = GraphStore('db/graph/fpga_rag_v2_graph.json')

# ── 1. PROJECT root node ──────────────────────────────────────────────────────
gs.add_node("yeni_proje_adi", {
    "node_type": "PROJECT",                 # zorunlu — NODE_TYPES içinde olmalı
    "name": "Proje Okunabilir Adı",
    "description": "Proje ne yapıyor, hangi board, hangi FPGA.",
    "board": "Digilent Nexys Video",
    "fpga_part": "xc7a200tsbg484-1",
    "tool": "Vivado 2025.1",
    "language": ["Verilog", "C"],
    "project_type": "example",              # "application" | "educational" | "example"
    "confidence": "HIGH",
    "provenance": {"phase": 1, "source": "README.md + build.tcl"},
})

# ── 2. COMPONENT node'ları ────────────────────────────────────────────────────
gs.add_node("YENI-COMP-clk_wiz_0", {
    "node_type": "COMPONENT",
    "name": "clk_wiz_0 — Clock Wizard",
    "description": "Xilinx Clocking Wizard v6.0. CLKOUT0=100 MHz sistem saati.",
    "vlnv": "xilinx.com:ip:clk_wiz:6.0",
    "project": "yeni_proje_adi",            # proje adını buraya yaz
    "confidence": "HIGH",
})

# ── 3. Edge'ler ──────────────────────────────────────────────────────────────
# COMPONENT → PROJECT bağlantısı
gs.add_edge("YENI-COMP-clk_wiz_0", "yeni_proje_adi", "INFORMED_BY",
            {"confidence": "HIGH"})

# Başka projelerle benzerlik (opsiyonel ama cross-ref sorguları için gerekli)
gs.add_edge("YENI-COMP-clk_wiz_0", "COMP-A-clk_wiz_0", "ANALOGOUS_TO",
            {"confidence": "MEDIUM", "note": "Her iki projede Clocking Wizard v6.0"})

# ── 4. KAYDET ────────────────────────────────────────────────────────────────
gs.save()   # BU SATIRSIZ TÜM DEĞİŞİKLİKLER KAYBOLUR
print("Graph kaydedildi.")
```

**Geçerli node türleri:** `PROJECT`, `REQUIREMENT`, `DECISION`, `COMPONENT`, `CONSTRAINT`, `EVIDENCE`, `PATTERN`, `SOURCE_DOC`, `ISSUE`

**Geçerli edge türleri:** `DECOMPOSES_TO`, `MOTIVATED_BY`, `ALTERNATIVE_TO`, `IMPLEMENTS`, `VERIFIED_BY`, `CONSTRAINED_BY`, `DEPENDS_ON`, `ANALOGOUS_TO`, `CONTRADICTS`, `INFORMED_BY`, `REUSES_PATTERN`, `SUPERSEDES`

---

## Adım 3 — VectorStore'u Güncelle (`VectorStoreV2`)

Yeni graph node'larını embedding vektörüne çevir ve ChromaDB'ye ekle.

```python
import sys; sys.path.insert(0, 'src')
from rag_v2.graph_store import GraphStore
from rag_v2.vector_store_v2 import VectorStoreV2

gs = GraphStore('db/graph/fpga_rag_v2_graph.json')
vs = VectorStoreV2('db/chroma_v2')

# Eklediğin tüm node ID'leri buraya yaz
new_node_ids = [
    "yeni_proje_adi",
    "YENI-COMP-clk_wiz_0",
    # ... diğerleri
]

for nid in new_node_ids:
    node = gs.get_node(nid)
    if node:
        vs.add_node({"node_id": nid, **node})
        print(f"VS+ {nid}")

print(f"Toplam VS kayıt: {vs._collection.count()}")
```

> **Not:** `vs.add_node()` upsert yapar — aynı `node_id` ikinci kez eklenirse güncellenir, hata vermez.

---

## Adım 4 — QueryRouter'a Proje Sinyalleri Ekle

**Dosya:** `src/rag_v2/query_router.py`

`_TEXT_PROJECT_SIGNALS` listesine yeni proje için anahtar kelimeler ekle.
Liste **ilk eşleşmede** durduğundan, daha uzun/spesifik ifadeler üste gelmelidir.

```python
# query_router.py → _TEXT_PROJECT_SIGNALS listesi içinde:

# yeni_proje_adi — spesifik ifadeler ÜSTE
("nexys video yeni proje", "yeni_proje_adi"),   # uzun ifade önce
("yeni_proje_adi", "yeni_proje_adi"),           # tam proje adı eşleşmesi
("yeni_ip_adi", "yeni_proje_adi"),              # projede özgün bir IP adı
("build_yeni", "yeni_proje_adi"),               # TCL script adı
```

> **Kural:** Birden fazla projede ortak olan kelimeler (`"microblaze"`, `"clk_wiz"`, `"ddr3"`) sinyale **eklenmemeli**.
> Sadece o projeye özgü IP adları, script isimleri veya teknik terimler kullanılmalı.

---

## Doğrulama

Her adımdan sonra şu kontrolleri çalıştır:

```bash
source .venv/bin/activate

# 1. Chunk sayısı
python3 -c "
import sys; sys.path.insert(0,'src')
from rag_v2.source_chunk_store import SourceChunkStore
sc = SourceChunkStore('db/chroma_source_chunks', threshold=0.25)
data = sc._get_collection().get(include=['metadatas'])
from collections import Counter
for p, c in sorted(Counter(m.get('project') for m in data['metadatas']).items()):
    print(f'  {p:<35} {c}')
"

# 2. Graph node'ları kayıt edildi mi?
python3 -c "
import sys; sys.path.insert(0,'src')
from rag_v2.graph_store import GraphStore
gs = GraphStore('db/graph/fpga_rag_v2_graph.json')
node = gs.get_node('yeni_proje_adi')
print('PROJECT node:', node.get('name') if node else 'BULUNAMADI')
"

# 3. VectorStore'da var mı?
python3 -c "
import sys; sys.path.insert(0,'src')
from rag_v2.vector_store_v2 import VectorStoreV2
vs = VectorStoreV2('db/chroma_v2')
res = vs._collection.get(ids=['yeni_proje_adi'], include=['metadatas'])
print('VS kayıt:', res['metadatas'] if res['metadatas'] else 'BULUNAMADI')
"

# 4. Proje algılama testi
python3 -c "
import sys; sys.path.insert(0,'src')
from rag_v2.query_router import QueryRouter
from rag_v2.graph_store import GraphStore
from rag_v2.vector_store_v2 import VectorStoreV2
from rag_v2.source_chunk_store import SourceChunkStore
gs = GraphStore('db/graph/fpga_rag_v2_graph.json')
vs = VectorStoreV2('db/chroma_v2')
sc = SourceChunkStore('db/chroma_source_chunks', threshold=0.25)
router = QueryRouter(gs, vs, source_chunk_store=sc)
q = 'yeni_proje_adi projesinde clk_wiz nedir?'
print('Algılanan proje:', router._resolve_project(q, []))
"
```

---

## Manuel Adımlar ve Otomasyon

### Şu an manuel olan adımlar

| Adım | Manuel İş | Neden Manuel? |
|------|-----------|---------------|
| 1 — Chunklama | `PROJECT_SOURCE_CATALOG`'a giriş ekle | Proje dizin yapısı her projede farklı |
| 2 — Graph node | Her bileşen için Python dict yaz | İçerik analizi gerektirir (TCL/V okuma) |
| 3 — VectorStore | Node ID listesini elle gir | Adım 2'ye bağımlı |
| 4 — QueryRouter | Anahtar kelime listesi yaz | Projeye özgü terminoloji bilinmeli |

### Nasıl Otomatikleştirilir?

**`scripts/add_project.py` — tek komutla proje ekleme scripti yazılabilir:**

```bash
python scripts/add_project.py \
  --project-id  "yeni_proje_adi" \
  --display-name "Yeni Proje (Nexys Video)" \
  --root        "data/code/yeni_proje" \
  --board       "Digilent Nexys Video" \
  --fpga-part   "xc7a200tsbg484-1" \
  --tool        "Vivado 2025.1"
```

Bu script otomatik olarak şunları yapabilir:

1. **Chunklama** — `PROJECT_SOURCE_CATALOG`'a giriş ekler ve `store.add_file()` çağırır ✅ (kolay)

2. **Graph otomatik analiz** — TCL dosyalarını parse ederek IP instance'larını çıkarır:
   ```
   create_bd_cell → COMPONENT node
   set_property CONFIG.* → description'a eklenir
   ```
   Bu kısmen mümkün; TCL parse karmaşık ama `grep "create_bd_cell\|create_ip"` ile %70 kapsam sağlanabilir.

3. **VectorStore** — Graph adımından sonra hemen otomatik çağrılabilir ✅ (kolay)

4. **QueryRouter sinyalleri** — TCL içindeki IP isimlerinden (`aurora_8b10b`, `axi_vdma`, `dvi2rgb`) otomatik sinyal listesi üretilebilir ✅ (iyi yaklaşım)

**En verimli otomasyon noktaları (öncelik sırasıyla):**
- Adım 1 (chunklama) → tamamen otomatikleştirilebilir
- Adım 3 (VectorStore) → tamamen otomatikleştirilebilir
- Adım 4 (sinyal listesi) → IP isimlerinden %80 otomatik
- Adım 2 (graph içerik) → yarı otomatik (TCL parse) — description kalitesi düşer ama işlevsel

---

## Özet Kontrol Listesi

```
[ ] data/code/<proje_adi>/ dizinine kaynak dosyalar kopyalandı
[ ] index_source_files.py → PROJECT_SOURCE_CATALOG'a giriş eklendi
[ ] python scripts/index_source_files.py çalıştırıldı
[ ] PROJECT root node graph'a eklendi (node_type="PROJECT")
[ ] COMPONENT node'ları eklendi (her IP için ayrı)
[ ] ANALOGOUS_TO edge'leri eklendi (benzer projelerle)
[ ] gs.save() çağrıldı
[ ] VectorStoreV2'ye yeni node'lar eklendi
[ ] query_router.py → _TEXT_PROJECT_SIGNALS güncellendi
[ ] Doğrulama testleri çalıştırıldı (8/8 ✓)
```
