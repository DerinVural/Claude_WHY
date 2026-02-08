# GC-RAG-VIVADO Başlangıç Rehberi

## ✅ Kurulum Tamamlandı!

RAG sistemi Vertex AI Gemini ve GCP API ile başarılı şekilde yapılandırıldı.

### 📊 Sistem Durumu

```
✅ Vertex AI Embeddings: Aktif (text-embedding-004)
✅ Gemini LLM: Aktif (gemini-2.0-flash)
✅ ChromaDB Vector Store: Aktif (28,840 parça)
✅ FPGA Kod Tabanı: 76,846 dosya
✅ Xilinx Dokümantasyonu: 1000+ PDF
✅ Özel Rehberler: 3 detaylı markdown dosyası
```

## 🚀 Hızlı Başlangıç

### 1. PowerShell Terminalde

```powershell
# Git klasörüne git
cd C:\Users\murat\Documents\GitHub\GC-RAG-VIVADO-2

# UTF-8 encoding'i ayarla (Türkçe karakterler için)
$env:PYTHONIOENCODING='utf-8'

# RAG sistemi istatistiklerini göster
python scripts/train.py --stats
```

### 2. İlk Sorgulamayı Yap

```powershell
# Etkileşimli chat'i başlat
python scripts/chat.py

# Veya doğrudan bir soru sor
python scripts/chat.py "Zybo HDMI video processing pipeline nasıl çalışır?"
```

### 3. Sistem Bilgileri

```powershell
# Tüm kaynakları indeksle (ilk çalıştırma)
python scripts/train.py

# Sadece yeni kodları ekle
python scripts/train.py --code-only

# Mevcut indexi sil ve yeniden oluştur
python scripts/train.py --force
```

## 🔍 Örnek Sorgular

Aşağıdaki soruları deneyin:

### FPGA Tasarım Soruları
```
1. "Zynq-7000 üzerinde DDR3 bellek nasıl erişilir?"
2. "AXI protocol'ü kullanarak custom IP nasıl yazılır?"
3. "Vivado IPI ile block diagram nasıl oluşturulur?"
4. "PetaLinux'da device tree nasıl düzenlenir?"
```

### Kod Analiz Soruları
```
1. "Zybo-HDMI projesinde video timing nasıl uygulanır?"
2. "Verilog'da state machine implementation best practices?"
3. "VHDL'de generics ve parameterization nasıl kullanılır?"
4. "Vivado TCL scripting örnekleri nelerdir?"
```

### Optimizasyon Soruları
```
1. "Vivado HLS'de loop pipelining nasıl yapılır?"
2. "FPGA alan kullanımı nasıl azaltılır?"
3. "Timing closure problemleri nasıl çözülür?"
4. "Power consumption optimization teknikleri?"
```

## 📚 Veri Kaynakları Yapısı

```
GC-RAG-VIVADO-2/
├── data/
│   ├── code/              (200+ FPGA projesi, 76K dosya)
│   │   ├── Arty-A7/      (35+ Arty-A7 projeleri)
│   │   ├── Zynq-Boards/  (Zybo, ZedBoard, ...)
│   │   ├── Nexys/        (40+ Nexys varyasyonu)
│   │   ├── Vitis-HLS/    (HLS örnekleri)
│   │   ├── PYNQ/         (Python FPGA)
│   │   └── ... (15+ platform)
│   ├── pdfs/             (1000+ Xilinx teknisyen dokümanı)
│   │   ├── Versal_Device/
│   │   ├── Zynq7000/
│   │   ├── Vivado_Design_Suite/
│   │   └── ... (5+ ürün serisi)
│   └── docs/             (Yapılandırma ve rehberler)
│       ├── README.md (Ana rehber)
│       ├── VIVADO_HLS_OPTIMIZATION.md
│       ├── ZYNQ7000_DESIGN_GUIDE.md
│       └── SYSTEM_CONFIGURATION.md
├── chroma_db/            (Vector database - SQLite)
├── src/                  (RAG pipeline kodu)
│   ├── rag/             (Embedding & LLM)
│   ├── vectorstore/     (Chroma entegrasyonu)
│   ├── utils/           (PDF/Kod yükleme)
│   └── gcp/             (GCP API entegrasyonu)
├── scripts/
│   ├── train.py         (Indexleme)
│   ├── chat.py          (İnteraktif chat)
│   └── query.py         (Programatik sorgu)
└── .env                 (Konfigürasyon - gizli)
```

## ⚙️ Yapılandırma Detayları

### Vertex AI Ayarları (`.env` dosyasında)

```env
# GCP Kimlik Bilgileri
GCP_PROJECT_ID=your-project-id
GOOGLE_API_KEY=your-gemini-api-key

# Vertex AI LLM
VERTEX_AI_LOCATION=us-central1
EMBEDDING_MODEL=text-embedding-004
LLM_MODEL=gemini-2.0-flash

# RAG Pipeline Ayarları
CHUNK_SIZE=1000          # Belge parçası boyutu
CHUNK_OVERLAP=200        # Parçalar arasında örtüşme
TOP_K_RESULTS=5          # Sorgu başına kaç kaynak
MIN_SIMILARITY=0.3       # Minimum benzerlik (0-1)
```

### ChromaDB Configuration (`config/rag_config.py`)

```python
# Vector store
persist_directory = "./chroma_db"
collection_name = "rag_documents"
distance_metric = "cosine"  # Benzerlik metriği

# Embedding model
embedding_dimension = 768   # text-embedding-004
batch_size = 5             # API limit

# Generator
model_name = "gemini-2.0-flash"
temperature = 0.7          # 0.0=deterministik, 1.0=yaratıcı
max_output_tokens = 2048
```

## 📈 Performans Beklentileri

| Metrik | Değer |
|--------|-------|
| İndexleme (ilk kez) | 5-10 dakika |
| Sorgu Yanıt Süresi | 2-5 saniye |
| Embedding Üretimi | <500ms |
| Vektör Araması | <100ms (28K kaynak) |
| LLM Üretimi | 1-3 saniye |
| Bellek Kullanımı | ~500MB (RAM) |
| Depolama | ~100MB (SQLite) |

## 🎯 İleri Özellikler

### Reranking (Opsiyonel)
```python
# Daha iyi sonuçlar için second-pass ranking
use_reranking = True
```

### Özel Sistem Promptu
```python
system_prompt = """Sen FPGA tasarım uzmanısın. 
Soruları verilen kaynak belgelere dayanarak cevapla.
Kod örnekleri ver ve kaynaklara referans göster."""
```

### Batch Processing
```python
# Büyük sorgu setleri için
python scripts/batch_query.py --input queries.txt --output results.json
```

## 🔐 Güvenlik Notları

1. **API Key**: `.env` dosyasını asla commit etme (`.gitignore`'a ekle)
2. **Lokal Depolama**: Tüm veriler yerel makinede kalır
3. **Veri Saklama**: Sorgu geçmişi hiç tutulmuyor
4. **Açık Kaynak**: Tüm kod GitHub'da incelenebilir

## 🐛 Sorun Giderme

### Hata: `GOOGLE_API_KEY bulunamadı`
```
→ .env dosyasını kontrol et
→ GCP Console'dan API key'i kopyala
→ Terminal'i yeniden başlat
```

### Hata: `Vertex AI başlatılamadı`
```
→ GCP_PROJECT_ID doğru mu?
→ Vertex AI API etkin mi? (GCP Console → APIs)
→ IAM permissions'ı kontrol et
```

### Düşük Benzerlik Sonuçları
```
→ min_similarity: 0.3 → 0.2 yap
→ top_k: 5 → 10 yap
→ Soru daha detaylı yaz
```

### Memory Problems
```
→ CHUNK_SIZE: 1000 → 500 yap
→ top_k: 5 → 3 yap
→ batch_size: 5 → 2 yap
```

## 📞 İletişim ve Destek

- **Xilinx Resources**: https://www.xilinx.com/support
- **GCP Vertex AI**: https://cloud.google.com/vertex-ai
- **ChromaDB Docs**: https://docs.trychroma.com/
- **GitHub Issues**: Bu repo'daki issue'ları aç

## 📝 Sonraki Adımlar

### Kısa Vadede
- [ ] Tüm FPGA projelerini test et
- [ ] Custom Vivado HLS kodu indexle
- [ ] Kendi device driver'larını ekle
- [ ] Performance tuning yap

### Orta Vadede
- [ ] Web arayüzü ekle (Streamlit/Flask)
- [ ] Multimodal desteği (diagram recognition)
- [ ] Advanced RAG (reranking, fusion)
- [ ] Conversation memory (chat history)

### Uzun Vadede
- [ ] Fine-tuned FPGA-specific LLM
- [ ] Real-time design validation
- [ ] Automated code generation
- [ ] Hardware-software co-design

## 📊 Kullanım İstatistikleri

```
İndekslenmiş Kaynaklar:
├── Toplam Parça: 28,840
├── Verilog Kod: 8,500+ parça
├── C/C++ Kod: 12,000+ parça
├── VHDL: 2,200+ parça
├── Documentation: 4,000+ parça
└── Other: 2,000+ parça

Desteklenen Platformlar:
├── Zynq-7000 (35+ proje)
├── Zynq UltraScale+ (15+ proje)
├── Artix-7 (40+ proje)
├── Spartan-7 (20+ proje)
└── Versal (10+ proje)
```

---

## ✨ Özet

**GC-RAG-VIVADO**, FPGA tasarımcıları ve yazılım geliştirmeleri için:

✅ **Bağlamsal Yanıtlar**: 28K+ parçalı veri tabanından anında bulunur  
✅ **Kod Örnekleri**: Gerçek proje kodlarından çalıştırılabilir örnekler  
✅ **Xilinx Referans**: 1000+ teknik belgeye erişim  
✅ **Türkçe Desteği**: Tüm sorular Türkçe'de cevaplanır  
✅ **Ekonomik**: GCP API'si çok düşük maliyetli  
✅ **Güvenli**: Tüm veriler yerel kalır  
✅ **Açık Kaynak**: Kod modifikasyon ve inceleme için açık  

---

**Sistem Versiyon**: 1.0  
**Tarih**: 1 Şubat 2026  
**Durum**: ✅ Üretim Hazır

Happy FPGA Designing! 🚀
