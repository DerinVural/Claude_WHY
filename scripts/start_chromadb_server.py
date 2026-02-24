#!/usr/bin/env python3
"""ChromaDB - HTTP Server Modu ile Çalışma

Windows'ta PersistentClient takılma sorunu varsa,
ChromaDB'yi HTTP server olarak çalıştırıp HttpClient ile bağlan.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("🚀 ChromaDB HTTP Server Başlatılıyor...")
print("=" * 60)
print("Bu terminal açık kalacak. CTRL+C ile durdurun.")
print("Başka bir terminalde train_by_project.py çalıştırın.")
print("=" * 60)

try:
    import chromadb
    from chromadb.config import Settings
    
    chroma_dir = project_root / "chroma_db"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    
    # HTTP server ayarları
    settings = Settings(
        chroma_api_impl="chromadb.api.fastapi.FastAPI",
        chroma_server_host="localhost",
        chroma_server_http_port=8000,
        persist_directory=str(chroma_dir),
        anonymized_telemetry=False,
    )
    
    print(f"\n📁 Data: {chroma_dir}")
    print(f"🌐 Server: http://localhost:8000")
    print(f"\n✅ Server başlatıldı. Beklemede...\n")
    
    # Server'ı başlat
    import uvicorn
    uvicorn.run(
        "chromadb.app:app",
        host="localhost",
        port=8000,
        reload=False
    )
    
except ImportError as e:
    print(f"\n❌ Gerekli paket eksik: {e}")
    print("\nKurulum:")
    print("  pip install chromadb[server]")
    sys.exit(1)
    
except Exception as e:
    print(f"\n❌ Hata: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
