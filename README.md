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
