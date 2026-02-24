# GCP-RAG-VIVADO

🚀 **Google Cloud Platform tabanlı RAG (Retrieval-Augmented Generation) sistemi**

Bu proje, PDF dökümanlarınızı yerel ChromaDB veritabanında indeksler ve Gemini AI ile akıllı soru-cevap yapmanızı sağlar.

## 🏗️ Mimari

```
┌─────────────────────────────────────────────────────────────────┐
│                    RAG Pipeline Mimarisi                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📥 EVRE 1: VERİ HAZIRLAMA (Ingestion)                         │
│  ┌─────────┐   ┌──────────┐   ┌───────────┐   ┌─────────────┐  │
│  │  PDF    │ → │ Chunking │ → │ Vertex AI │ → │  ChromaDB   │  │
│  │ Okuma   │   │ (1000ch) │   │ Embedding │   │  (Yerel)    │  │
│  └─────────┘   └──────────┘   └───────────┘   └─────────────┘  │
│       ↓                             ↓                           │
│   /data/*.pdf              text-embedding-004           /chroma_db│
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  🔍 EVRE 2: SORU-CEVAP (Retrieval & Generation)                │
│  ┌─────────┐   ┌───────────┐   ┌─────────────┐   ┌──────────┐  │
│  │  Soru   │ → │ Embedding │ → │  ChromaDB   │ → │  Gemini  │  │
│  │         │   │           │   │   Arama     │   │  Flash   │  │
│  └─────────┘   └───────────┘   └─────────────┘   └──────────┘  │
│       ↓              ↓               ↓                ↓         │
│   "FPGA nedir?"   Vektör      En yakın 3 parça    Yanıt       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 📦 Kurulum

### 1. Bağımlılıkları Yükle

```bash
pip install -e .
```

veya:

```bash
pip install google-generativeai chromadb pypdf python-dotenv numpy
```

### 2. API Anahtarını Ayarla

`.env` dosyası oluşturun:

```env
GOOGLE_API_KEY=your-api-key-here
```

### 3. Dökümanları Ekle

PDF veya TXT dosyalarınızı `/data` klasörüne koyun.

## 🚀 Kullanım

### Interaktif Mod

```bash
python src/rag_pipeline.py
```

### Python Kodu

```python
from src.rag_pipeline import RAGPipeline

# Pipeline başlat
pipeline = RAGPipeline()

# Dökümanları indeksle (ilk seferde)
pipeline.ingest()

# Soru sor
result = pipeline.query("FPGA nedir?")
print(result["answer"])

# Basit kullanım
answer = pipeline.ask("Vivado nasıl kullanılır?")
```

## 📁 Proje Yapısı

```
GCP-RAG-VIVADO/
├── src/
│   ├── rag_pipeline.py      # Ana RAG pipeline
│   ├── rag/
│   │   ├── vertex_embeddings.py  # Embedding servisi
│   │   └── gemini_generator.py   # LLM yanıt üretici
│   ├── vectorstore/
│   │   └── chroma_store.py  # ChromaDB vektör deposu
│   └── utils/
│       ├── pdf_loader.py    # PDF yükleyici
│       └── chunker.py       # Metin parçalayıcı
├── data/                    # PDF/TXT dökümanları (siz ekleyin)
├── chroma_db/              # Vektör veritabanı (otomatik oluşur)
├── .env                    # API anahtarları
└── pyproject.toml          # Proje bağımlılıkları
```

## 🔧 Bileşenler

| Bileşen | Araç/Model | Konum | Görevi |
|---------|-----------|-------|--------|
| Orkestra Şefi | Python | Yerel PC | Tüm parçaları birbirine bağlar |
| Anlamlandırıcı | text-embedding-004 | Google Cloud | Metni vektöre çevirir |
| Hafıza | ChromaDB | Yerel PC | Vektörleri saklar |
| Cevaplayıcı | Gemini Flash | Google Cloud | Kaynaklara göre cevap yazar |

## 💡 İpuçları

- **İlk çalıştırma**: `ingest()` dökümanları indeksler, bu bir kere yapılır
- **Sonraki çalıştırmalar**: Sadece soru sorun, indeksleme gerekmez
- **Yeniden indeksleme**: `pipeline.ingest(force=True)` kullanın
- **Chunk boyutu**: Varsayılan 1000 karakter, `TextChunker(chunk_size=500)` ile değiştirin

## 📄 Lisans

MIT License
---

## 📊 EĞİTİM DURUMU (Son Güncelleme: 9 Şubat 2026, 01:15)

### 🟢 Genel İlerleme
- **Toplam İşlenen Dosya:** 3,406
- **Toplam Chunk (Embedding):** 1,243,029
- **ChromaDB Boyutu:** ~7+ GB
- **Embedding Modeli:** Sentence Transformers `all-mpnet-base-v2` (768 boyut, lokal)
- **Veritabanı:** ChromaDB PersistentClient, collection: `documents`

### ✅ Tamamlanan Kategoriler (16/28)

| # | Kategori | Dosya | Chunk |
|---|----------|-------|-------|
| 1 | pdf_PetaLinux | 0 | 0 |
| 2 | pdf_7_Series | 322 | 53,369 |
| 3 | pdf_UltraScale | 189 | 60,458 |
| 4 | pdf_Zynq_7000 | 142 | 32,386 |
| 5 | pdf_Zynq_MPSoC | 101 | 35,224 |
| 6 | pdf_Versal | 172 | 114,959 |
| 7 | pdf_Vivado | 62 | 38,387 |
| 8 | pdf_Vitis | 14 | 17,525 |
| 9 | pdf_IP | 1,309 | 417,066 |
| 10 | pdf_Alveo | 91 | 18,072 |
| 11 | pdf_Virtex_5 | 253 | 45,345 |
| 12 | pdf_Virtex_6 | 184 | 33,283 |
| 13 | pdf_Spartan_6 | 183 | 25,123 |
| 14 | pdf_CoolRunner | 228 | 14,380 |
| 15 | pdf_Other_PDFs | 131 | 91,406 |
| 16 | code_Arty_7Series | 25 | 246,046 |

### 🔄 Kalan Kategoriler (12/28) — Buradan Devam Edilecek

| # | Kategori | Dosya Sayısı |
|---|----------|-------------|
| 17 | **code_Arty_Zynq** ← ŞU AN BURASI | 19 |
| 18 | code_Basys | 9 |
| 19 | code_Nexys | 35 |
| 20 | code_Zybo | 25 |
| 21 | code_Cmod | 14 |
| 22 | code_Cora | 13 |
| 23 | code_Genesys | 9 |
| 24 | code_Eclypse | 3 |
| 25 | code_Zedboard | 7 |
| 26 | code_Vitis_Examples | 11 |
| 27 | code_Vivado_Tutorials | 4 |
| 28 | code_HDL_Libraries | 6 |
| 29 | code_PYNQ | 5 |
| 30 | code_Linux_BSP | 2 |
| 31 | code_Other_Code | 40 |

### 🚀 Makine Açıldığında Devam Etmek İçin

```bash
# 1. Eğitimi kaldığı yerden başlat (checkpoint otomatik yüklenir)
python scripts/train_organized.py

# 2. Durumu izle (opsiyonel, ayrı bir terminalde)
python scripts/monitor_training.py

# 3. İstatistikleri gör
python scripts/train_organized.py --stats

# 4. RAG'a soru sor (eğitim devam ederken bile çalışır)
python test_rag_quick.py
```

### ⚠️ Önemli Notlar
- **Checkpoint sistemi** otomatik çalışır — her 3 dosyada kayıt yapar
- `training_organized_checkpoint.json` dosyası kaldığı yeri tutar
- ChromaDB veritabanı `chroma_db/` klasöründe (7+ GB)
- Embedding modeli lokal cache'de, internet gerekmez
- Eğitim sırasında `test_rag_quick.py` ile soru sorulabilir (read-only)
- **Conda ortamı:** `astro` (Python 3.12.12)