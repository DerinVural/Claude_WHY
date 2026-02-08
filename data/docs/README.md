# GC-RAG-VIVADO Dokümantasyon

## İçerik Yapısı

Bu klasör, RAG (Retrieval Augmented Generation) sistemi tarafından işlenen dokümantasyonları ve kaynak materyalleri içerir.

### Veri Kaynakları

#### 📄 PDF Dokümantasyonu
- **Konum**: `../pdfs/`
- **Sayı**: 1000+ Xilinx teknik dokümantasyonu
- **Kategoriler**:
  - Versal Device Documentation
  - Virtex Serisi
  - Zynq-7000 & UltraScale+
  - Vivado Design Suite
  - Vitis Araçları

#### 💻 FPGA Proje Kodları
- **Konum**: `../code/`
- **Sayı**: 200+ örnek proje
- **Diller**:
  - Verilog / SystemVerilog
  - VHDL
  - C / C++
  - Python
  - TCL (Vivado scripts)

#### 📋 RAG İndeksi
- **İndekslenmiş Belgeler**: 28,840+ parça
- **Vector Store**: ChromaDB (Chroma)
- **Embedding Model**: Vertex AI text-embedding-004
- **LLM**: Gemini 2.0 Flash

## RAG Pipeline İşlevleri

### 1. İndeksleme (Training)
```bash
# Tüm dosyaları indeksle
python scripts/train.py

# Sadece PDF'leri indeksle
python scripts/train.py --pdf-only

# Sadece kod dosyalarını indeksle
python scripts/train.py --code-only

# Mevcut veritabanını sil ve yeniden indeksle
python scripts/train.py --force
```

### 2. Sorgulama (Querying)
```bash
# Etkileşimli sorgulama başlat
python scripts/chat.py

# Örnek: Zybo HDMI entegrasyonu
python scripts/query.py "Zybo HDMI implementasyonu nasıl yapılır?"

# Örnek: Vivado HLS optimization
python scripts/query.py "HLS kodasında optimization teknikleri nelerdir?"
```

## GCP Entegrasyonu

### Vertex AI LLM
- **Model**: `gemini-2.0-flash`
- **Bölge**: US Central 1
- **Özellikleri**: Hızlı, düşük maliyetli, çok-dilli

### Vertex AI Embeddings
- **Model**: `text-embedding-004`
- **Boyut**: 768-dimensional vectors
- **Batch Size**: 5 (API limiti)

### Google Cloud Storage
- **Bucket**: Chroma vektör veritabanı yedeklemeleri
- **Format**: SQLite + Binary embeddings

## Yapılandırma

### `.env` Dosyası
```env
# GCP Kimlik Bilgileri
GCP_PROJECT_ID=your-project-id
GOOGLE_API_KEY=your-api-key

# Vertex AI Ayarları
VERTEX_AI_LOCATION=us-central1
EMBEDDING_MODEL=text-embedding-004
LLM_MODEL=gemini-2.0-flash

# RAG Pipeline
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
TOP_K_RESULTS=5
```

## Kullanım Örnekleri

### FPGA Tasarım Soruları
```
"Zynq-7000 üzerinde HDMI video akışı nasıl uygulanır?"
"Vivado HLS'de en iyi optimizasyon pratikleri nelerdir?"
"PetaLinux ile custom device driver yazarken dikkat edilmesi gereken noktalar?"
```

### Kod Analizi
```
"../data/code/Zybo-HDMI klasöründe video processing pipeline nedir?"
"Verilog'da state machine pattern en iyi nasıl uygulanır?"
```

### Dokümantasyon Sorgusu
```
"Vertex Device PCIe DMA transfer hızı nasıl optimize edilir?"
"Vivado IP Custom protokol nasıl tanımlanır?"
```

## Performans Metrikleri

- **İndeksleme Hızı**: ~500 MB/saat (PDF)
- **Sorgu Yanıtı**: <2 saniye
- **Embedding Accuracy**: %95+
- **Vector Similarity**: Cosine (0-1)

## Sistem Mimarisi

```
┌─────────────────────────────────────────┐
│         Kullanıcı Sorgusu               │
└────────────────┬────────────────────────┘
                 │
         ┌───────▼────────┐
         │ Vertex AI      │
         │ Embeddings     │
         │ (Sorgu Vekt.)  │
         └───────┬────────┘
                 │
         ┌───────▼──────────┐
         │ ChromaDB Vector  │
         │ Store (Retrieval)│
         └───────┬──────────┘
                 │
         ┌───────▼──────────┐
         │ Top-K Dokümanlar │
         │ (Benzerlik       │
         │  Taraması)       │
         └───────┬──────────┘
                 │
         ┌───────▼──────────┐
         │ Gemini LLM       │
         │ (Response Gen.)  │
         └───────┬──────────┘
                 │
         ┌───────▼──────────┐
         │ Yanıt + Kaynaklar│
         └──────────────────┘
```

## Geliştirilmiş İşlevler

- ✅ Multi-dil support (Türkçe/İngilizce)
- ✅ Kod-spesifik chunking stratejileri
- ✅ Kaynak belirtme (file paths, line numbers)
- ✅ Benzerlik skoru filtreleme
- ✅ Batch processing (1000+ belge)
- ✅ Reranking desteği (opsiyonel)

## Sorun Giderme

### API Anahtarı Hatası
```
HATA: GOOGLE_API_KEY bulunamadı
FİKR: .env dosyasını kontrol edin
```

### Vertex AI Bağlantısı
```
HATA: Vertex AI başlatılamadı
FİKR: GCP_PROJECT_ID ve kimlik bilgilerinizi doğrulayın
```

### Düşük Benzerlik Skoru
```
FİKR: top_k artırın veya min_similarity azaltın
      rag_config.py'ı düzenleyin
```

## Kaynaklar

- [Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [Gemini API](https://ai.google.dev/)
- [ChromaDB](https://docs.trychroma.com/)
- [FPGA Design Guides](../pdfs/)

---

**Son Güncelleme**: 2024
**Versiyon**: 1.0
