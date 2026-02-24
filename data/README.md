# Data Directory

Bu klasöre PDF ve TXT dosyalarınızı ekleyin.

## Desteklenen Formatlar

- `.pdf` - PDF dökümanları
- `.txt` - Düz metin dosyaları
- `.md` - Markdown dosyaları

## Örnek

```
data/
├── fpga_basics.pdf
├── vivado_guide.pdf
└── notes.txt
```

Dökümanları ekledikten sonra:

```python
from src.rag_pipeline import RAGPipeline

pipeline = RAGPipeline()
pipeline.ingest()  # Dökümanları indeksle
```
