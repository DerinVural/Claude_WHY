#!/usr/bin/env python3
"""ChromaDB Basit Test - Ekleme çalışıyor mu?"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("🧪 ChromaDB Test Başlıyor...")
print("=" * 50)

try:
    print("1️⃣ ChromaDB import ediliyor...")
    import chromadb
    from chromadb.config import Settings
    print("   ✅ Import başarılı")
    
    print("\n2️⃣ PersistentClient oluşturuluyor...")
    chroma_dir = project_root / "chroma_db"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    
    settings = Settings(
        anonymized_telemetry=False,
        allow_reset=True,
    )
    
    client = chromadb.PersistentClient(
        path=str(chroma_dir),
        settings=settings
    )
    print(f"   ✅ Client oluşturuldu: {chroma_dir}")
    
    print("\n3️⃣ Test koleksiyonu oluşturuluyor...")
    collection = client.get_or_create_collection(
        name="test_collection",
        metadata={"hnsw:space": "cosine"},
        embedding_function=None
    )
    print(f"   ✅ Koleksiyon: test_collection")
    print(f"   📊 Mevcut döküman sayısı: {collection.count()}")
    
    print("\n4️⃣ Test verisi ekleniyor...")
    test_docs = ["Bu bir test belgesi", "İkinci test belgesi"]
    test_embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    test_ids = ["test_1", "test_2"]
    test_metadatas = [{"source": "test1"}, {"source": "test2"}]
    
    collection.add(
        documents=test_docs,
        embeddings=test_embeddings,
        ids=test_ids,
        metadatas=test_metadatas
    )
    print(f"   ✅ {len(test_docs)} döküman eklendi")
    
    print("\n5️⃣ Eklenen veriler kontrol ediliyor...")
    final_count = collection.count()
    print(f"   📊 Toplam döküman: {final_count}")
    
    print("\n6️⃣ Koleksiyonlar listeleniyor...")
    collections = client.list_collections()
    print(f"   📁 Toplam koleksiyon: {len(collections)}")
    for col in collections:
        print(f"      - {col.name}: {col.count()} döküman")
    
    print("\n" + "=" * 50)
    print("✅ TÜM TESTLER BAŞARILI!")
    print("=" * 50)
    print("\n💡 ChromaDB çalışıyor, train_by_project.py kullanabilirsiniz.")
    
except Exception as e:
    print(f"\n❌ HATA: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
