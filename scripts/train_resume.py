#!/usr/bin/env python3
"""
Resume Training Script - Kaldığı yerden devam eden eğitim

Kullanım:
    python scripts/train_resume.py              # Kaldığı yerden devam et
    python scripts/train_resume.py --reset      # Sıfırdan başla
    python scripts/train_resume.py --stats      # İstatistikleri göster
"""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime

# Proje kök dizinini path'e ekle
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# Checkpoint dosyası
CHECKPOINT_FILE = project_root / "training_checkpoint.json"


def load_checkpoint():
    """Checkpoint yükle."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "processed_pdfs": [],
        "processed_codes": [],
        "last_chunk_index": 0,
        "total_chunks": 0,
        "last_update": None,
        "status": "not_started"
    }


def save_checkpoint(checkpoint):
    """Checkpoint kaydet."""
    checkpoint["last_update"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)


def print_banner():
    print("""
╔═══════════════════════════════════════════════════════════════╗
║              GCP-RAG-VIVADO RESUME TRAINER                    ║
║           Kaldığı Yerden Devam Eden Eğitim Aracı              ║
╚═══════════════════════════════════════════════════════════════╝
    """)


def show_stats():
    """İstatistikleri göster."""
    from src.vectorstore.chroma_store import ChromaVectorStore
    from config.rag_config import load_config
    
    config = load_config()
    checkpoint = load_checkpoint()
    
    print("\n📊 EĞİTİM DURUMU")
    print("=" * 50)
    
    # Checkpoint bilgileri
    print(f"\n📝 Checkpoint:")
    print(f"   Son güncelleme: {checkpoint.get('last_update', 'Yok')}")
    print(f"   Durum: {checkpoint.get('status', 'Bilinmiyor')}")
    print(f"   İşlenen PDF sayısı: {len(checkpoint.get('processed_pdfs', []))}")
    print(f"   İşlenen kod sayısı: {len(checkpoint.get('processed_codes', []))}")
    print(f"   Son chunk index: {checkpoint.get('last_chunk_index', 0)}")
    
    # ChromaDB durumu
    try:
        vector_store = ChromaVectorStore(
            persist_directory=config.vector_store.persist_directory,
            collection_name=config.vector_store.collection_name
        )
        count = vector_store.get_document_count()
        print(f"\n💾 ChromaDB:")
        print(f"   İndekslenmiş parça: {count}")
    except Exception as e:
        print(f"\n❌ ChromaDB hatası: {e}")
    
    print("=" * 50)


def train_with_resume():
    """Resume destekli eğitim."""
    from src.utils.pdf_loader import PDFLoader
    from src.utils.code_loader import CodeLoader
    from src.utils.chunker import TextChunker
    from src.rag.vertex_embeddings import GoogleGenAIEmbeddings
    from src.vectorstore.chroma_store import ChromaVectorStore
    from config.rag_config import load_config
    
    config = load_config()
    checkpoint = load_checkpoint()
    
    print(f"\n🔄 Checkpoint yüklendi: {checkpoint.get('status', 'Yeni başlangıç')}")
    
    # Klasörleri kontrol et
    pdf_dir = project_root / "data" / "pdfs"
    code_dir = project_root / "data" / "code"
    text_dir = project_root / "data" / "docs"
    
    all_documents = []
    processed_pdfs = set(checkpoint.get("processed_pdfs", []))
    processed_codes = set(checkpoint.get("processed_codes", []))
    
    # PDF'leri yükle (işlenmemiş olanlar)
    print("\n📄 PDF Dosyaları Yükleniyor...")
    print("-" * 40)
    
    loader = PDFLoader(str(pdf_dir))
    pdf_files = list(pdf_dir.glob("**/*.pdf"))
    
    new_pdf_count = 0
    for pdf_path in pdf_files:
        pdf_key = str(pdf_path.relative_to(pdf_dir))
        if pdf_key not in processed_pdfs:
            try:
                content = loader.load_pdf(str(pdf_path))
                all_documents.append({
                    "id": pdf_path.stem,
                    "content": content,
                    "metadata": {
                        "source": str(pdf_path),
                        "filename": pdf_path.name,
                        "type": "pdf",
                    },
                })
                processed_pdfs.add(pdf_key)
                new_pdf_count += 1
                print(f"  ✅ {pdf_path.name}")
            except Exception as e:
                print(f"  ❌ {pdf_path.name}: {e}")
    
    print(f"📄 {new_pdf_count} yeni PDF yüklendi.")
    
    # Kod dosyalarını yükle (işlenmemiş olanlar)
    print("\n💻 Kod Dosyaları Yükleniyor...")
    print("-" * 40)
    
    code_loader = CodeLoader(str(code_dir))
    
    # Tüm kod dosyalarını bul
    code_files = []
    for ext in code_loader.SUPPORTED_EXTENSIONS.keys():
        code_files.extend(code_loader.code_directory.glob(f"**/*{ext}"))
    code_files = [f for f in code_files if not code_loader._should_ignore(f)]
    
    print(f"📂 {len(code_files)} kod dosyası bulundu.")
    
    new_code_count = 0
    batch_size = 1000  # Her 1000 dosyada bir checkpoint kaydet
    
    for i, code_path in enumerate(code_files):
        try:
            code_key = str(code_path.relative_to(code_dir))
        except ValueError:
            code_key = str(code_path)
            
        if code_key not in processed_codes:
            doc = code_loader.load_code_file(code_path)
            if doc:
                all_documents.append(doc)
                processed_codes.add(code_key)
                new_code_count += 1
                if new_code_count % 500 == 0:
                    print(f"  📝 {new_code_count} kod dosyası yüklendi...")
        
        # Her batch_size dosyada checkpoint kaydet
        if (i + 1) % batch_size == 0:
            checkpoint["processed_pdfs"] = list(processed_pdfs)
            checkpoint["processed_codes"] = list(processed_codes)
            checkpoint["status"] = "loading_files"
            save_checkpoint(checkpoint)
            print(f"  📊 İlerleme: {i+1}/{len(code_files)} dosya işlendi")
    
    print(f"💻 {new_code_count} yeni kod dosyası yüklendi.")
    
    # Text dosyalarını yükle
    print("\n📝 Metin Dosyaları Yükleniyor...")
    text_loader = PDFLoader(str(text_dir))
    text_docs = text_loader.load_text_files()
    all_documents.extend(text_docs)
    print(f"📝 {len(text_docs)} metin dosyası yüklendi.")
    
    # Checkpoint güncelle
    checkpoint["processed_pdfs"] = list(processed_pdfs)
    checkpoint["processed_codes"] = list(processed_codes)
    checkpoint["status"] = "chunking"
    save_checkpoint(checkpoint)
    
    if not all_documents:
        print("\n✅ Tüm dosyalar zaten işlenmiş!")
        return
    
    # Parçalama
    print(f"\n✂️ {len(all_documents)} döküman parçalanıyor...")
    chunker = TextChunker(
        chunk_size=config.chunking.chunk_size,
        chunk_overlap=config.chunking.chunk_overlap
    )
    
    all_chunks = []
    for doc in all_documents:
        try:
            # Metadata'yı içeriğe dahil et
            chunks = chunker.chunk_text(doc['content'])
            for chunk in chunks:
                all_chunks.append({
                    "content": chunk,
                    "metadata": doc['metadata']
                })
        except Exception as e:
            print(f"  ⚠️ Parçalama hatası: {e}")
    
    print(f"   📊 {len(all_chunks)} parça oluşturuldu.")
    
    # Embedding ve kayıt
    print("\n🧮 Embedding vektörleri oluşturuluyor...")
    print("-" * 40)
    
    embeddings = GoogleGenAIEmbeddings(
        api_key=config.embedding.api_key,
        model_name=config.embedding.model_name
    )
    vector_store = ChromaVectorStore(
        persist_directory=config.vector_store.persist_directory,
        collection_name=config.vector_store.collection_name
    )
    
    batch_size = 100  # Her 100 parçada bir kaydet
    start_index = checkpoint.get("last_chunk_index", 0)
    
    for i in range(start_index, len(all_chunks), batch_size):
        batch = all_chunks[i:i+batch_size]
        
        try:
            # Embedding oluştur
            texts = [c["content"] for c in batch]
            vectors = embeddings.embed_texts(texts)
            
            # ChromaDB'ye kaydet
            ids = [f"doc_{i+j}" for j in range(len(batch))]
            metadatas = [c["metadata"] for c in batch]
            
            vector_store.add_documents(ids, texts, vectors, metadatas)
            
            # Checkpoint güncelle
            checkpoint["last_chunk_index"] = i + len(batch)
            checkpoint["total_chunks"] = len(all_chunks)
            checkpoint["status"] = "embedding"
            save_checkpoint(checkpoint)
            
            print(f"  📊 Vektörleştirme: {i + len(batch)}/{len(all_chunks)}")
            
        except Exception as e:
            print(f"  ❌ Batch {i} hatası: {e}")
            checkpoint["status"] = f"error_at_{i}"
            save_checkpoint(checkpoint)
            raise
    
    # Tamamlandı
    checkpoint["status"] = "completed"
    checkpoint["last_chunk_index"] = len(all_chunks)
    save_checkpoint(checkpoint)
    
    print("\n" + "=" * 50)
    print("✅ EĞİTİM TAMAMLANDI!")
    print(f"   Toplam parça: {len(all_chunks)}")
    print(f"   ChromaDB'de: {vector_store.count()}")
    print("=" * 50)


def reset_training():
    """Eğitimi sıfırla."""
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("✅ Checkpoint silindi.")
    
    # ChromaDB'yi temizle
    from src.vectorstore.chroma_store import ChromaVectorStore
    from config.rag_config import load_config
    
    config = load_config()
    vector_store = ChromaVectorStore(config.vector_store)
    vector_store.clear()
    print("✅ ChromaDB temizlendi.")


def main():
    parser = argparse.ArgumentParser(description="Resume destekli RAG eğitimi")
    parser.add_argument("--reset", action="store_true", help="Eğitimi sıfırla")
    parser.add_argument("--stats", action="store_true", help="İstatistikleri göster")
    args = parser.parse_args()
    
    print_banner()
    
    if args.stats:
        show_stats()
    elif args.reset:
        reset_training()
    else:
        train_with_resume()


if __name__ == "__main__":
    main()
