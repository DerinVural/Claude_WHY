#!/usr/bin/env python3
"""
ChromaDB SQLite Lock Sorunu Çözücü

SQLite veritabanını WAL moduna çevirir ve optimize eder.
"""

import sqlite3
from pathlib import Path

project_root = Path(__file__).parent.parent
chroma_db_path = project_root / "chroma_db"

print("🔧 ChromaDB SQLite Optimizasyonu")
print("=" * 50)

# ChromaDB'nin SQLite dosyasını bul
sqlite_file = chroma_db_path / "chroma.sqlite3"

if not sqlite_file.exists():
    print(f"⚠️ SQLite dosyası bulunamadı: {sqlite_file}")
    print("   ChromaDB henüz oluşturulmamış olabilir.")
else:
    print(f"📁 SQLite: {sqlite_file}")
    
    try:
        # SQLite'a bağlan
        conn = sqlite3.connect(str(sqlite_file))
        cursor = conn.cursor()
        
        # WAL modunu aktifleştir (eşzamanlı okuma/yazma için)
        print("\n1️⃣ WAL (Write-Ahead Logging) modu aktifleştiriliyor...")
        cursor.execute("PRAGMA journal_mode=WAL;")
        result = cursor.fetchone()
        print(f"   ✅ Journal mode: {result[0]}")
        
        # Timeout artır
        print("\n2️⃣ Timeout ayarlanıyor...")
        conn.execute("PRAGMA busy_timeout = 30000;")  # 30 saniye
        print(f"   ✅ Busy timeout: 30000ms")
        
        # Synchronous modunu optimize et
        print("\n3️⃣ Synchronous modu optimize ediliyor...")
        cursor.execute("PRAGMA synchronous = NORMAL;")
        print(f"   ✅ Synchronous: NORMAL")
        
        # Cache size artır
        print("\n4️⃣ Cache boyutu artırılıyor...")
        cursor.execute("PRAGMA cache_size = -64000;")  # 64MB
        print(f"   ✅ Cache size: 64MB")
        
        conn.commit()
        conn.close()
        
        print("\n" + "=" * 50)
        print("✅ ChromaDB SQLite optimizasyonu tamamlandı!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ Hata: {e}")

print("\n💡 Şimdi train_by_project.py çalıştırabilirsiniz:")
print("   python scripts/train_by_project.py --verbose")
