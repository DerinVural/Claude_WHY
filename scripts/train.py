#!/usr/bin/env python3
"""
Training Script - PDF ve Kod Dosyalarını İndeksle

Kullanım:
    python scripts/train.py                    # Tüm dosyaları indeksle
    python scripts/train.py --force            # Mevcut veritabanını sil ve yeniden indeksle
    python scripts/train.py --pdf-only         # Sadece PDF'leri indeksle
    python scripts/train.py --code-only        # Sadece kod dosyalarını indeksle
    python scripts/train.py --stats            # İstatistikleri göster
"""

import sys
import os
import argparse
from pathlib import Path

# Proje kök dizinini path'e ekle
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.utils.pdf_loader import PDFLoader
from src.utils.code_loader import CodeLoader
from src.utils.chunker import TextChunker
from src.rag.vertex_embeddings import GoogleGenAIEmbeddings
from src.vectorstore.chroma_store import ChromaVectorStore


def print_banner():
    """ASCII banner yazdır."""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║                   GCP-RAG-VIVADO TRAINER                      ║
║              PDF & Kod Dosyası İndeksleme Aracı               ║
╚═══════════════════════════════════════════════════════════════╝
    """)


def create_directories():
    """Gerekli klasörleri oluştur."""
    dirs = [
        project_root / "data" / "pdfs",
        project_root / "data" / "code",
        project_root / "data" / "docs",
        project_root / "chroma_db",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print("📁 Klasörler hazır.")


def load_pdfs(pdf_dir: Path) -> list:
    """PDF dosyalarını yükle."""
    print("\n📄 PDF Dosyaları Yükleniyor...")
    print("-" * 40)
    
    loader = PDFLoader(str(pdf_dir))
    documents = loader.load_all_pdfs()
    
    if not documents:
        print(f"   ⚠️ '{pdf_dir}' klasöründe PDF bulunamadı.")
        print(f"   💡 PDF dosyalarınızı buraya kopyalayın: {pdf_dir}")
    
    return documents


def load_code(code_dir: Path) -> list:
    """Kod dosyalarını yükle."""
    print("\n💻 Kod Dosyaları Yükleniyor...")
    print("-" * 40)
    
    loader = CodeLoader(str(code_dir))
    
    # İstatistikleri göster
    stats = loader.get_stats()
    if stats:
        print("   Bulunan diller:")
        for lang, count in sorted(stats.items(), key=lambda x: -x[1]):
            print(f"      {lang}: {count} dosya")
    
    documents = loader.load_all_code()
    
    if not documents:
        print(f"   ⚠️ '{code_dir}' klasöründe kod dosyası bulunamadı.")
        print(f"   💡 Kod dosyalarınızı buraya kopyalayın: {code_dir}")
    
    return documents


def load_texts(text_dir: Path) -> list:
    """Metin dosyalarını yükle."""
    print("\n📝 Metin Dosyaları Yükleniyor...")
    print("-" * 40)
    
    loader = PDFLoader(str(text_dir))
    documents = loader.load_text_files()
    
    return documents


def chunk_documents(documents: list, chunk_size: int = 1000, chunk_overlap: int = 200) -> list:
    """Dökümanları parçala."""
    print("\n✂️ Dökümanlar Parçalanıyor...")
    print("-" * 40)
    
    chunker = TextChunker(chunk_size, chunk_overlap)
    chunks = chunker.chunk_documents(documents)
    
    print(f"   📊 {len(documents)} döküman → {len(chunks)} parça")
    return chunks


def generate_embeddings(chunks: list) -> list:
    """Embedding vektörleri oluştur."""
    print("\n🧮 Embedding Vektörleri Oluşturuluyor...")
    print("-" * 40)
    
    embeddings_service = GoogleGenAIEmbeddings()
    texts = [chunk["content"] for chunk in chunks]
    
    embeddings = embeddings_service.embed_texts(texts)
    
    print(f"   ✅ {len(embeddings)} vektör oluşturuldu")
    return embeddings


def store_in_chromadb(chunks: list, embeddings: list, chroma_dir: Path, force: bool = False):
    """ChromaDB'ye kaydet."""
    print("\n💾 ChromaDB'ye Kaydediliyor...")
    print("-" * 40)
    
    vector_store = ChromaVectorStore(
        persist_directory=str(chroma_dir),
        collection_name="rag_documents"
    )
    
    # Eğer force ise mevcut koleksiyonu sil
    if force and not vector_store.is_empty():
        print("   🔄 Mevcut veritabanı temizleniyor...")
        vector_store.delete_collection()
        # Yeniden oluştur
        vector_store = ChromaVectorStore(
            persist_directory=str(chroma_dir),
            collection_name="rag_documents"
        )
    
    # Dökümanları batch halinde ekle (ChromaDB limit: 5461)
    batch_size = 5000
    total = len(chunks)
    
    for i in range(0, total, batch_size):
        end = min(i + batch_size, total)
        batch_chunks = chunks[i:end]
        batch_embeddings = embeddings[i:end]
        
        vector_store.add_documents(
            documents=[chunk["content"] for chunk in batch_chunks],
            embeddings=batch_embeddings,
            ids=[chunk["id"] for chunk in batch_chunks],
            metadatas=[chunk["metadata"] for chunk in batch_chunks],
        )
        print(f"   📦 Batch {i//batch_size + 1}: {end}/{total} eklendi")
    
    print(f"   📊 Toplam döküman sayısı: {vector_store.get_document_count()}")


def show_stats(chroma_dir: Path, pdf_dir: Path, code_dir: Path):
    """İstatistikleri göster."""
    print("\n📊 İSTATİSTİKLER")
    print("=" * 50)
    
    # PDF sayısı
    pdf_count = len(list(pdf_dir.glob("*.pdf"))) if pdf_dir.exists() else 0
    print(f"📄 PDF Dosyaları: {pdf_count}")
    
    # Kod dosyaları
    if code_dir.exists():
        code_loader = CodeLoader(str(code_dir))
        stats = code_loader.get_stats()
        total_code = sum(stats.values())
        print(f"💻 Kod Dosyaları: {total_code}")
        for lang, count in sorted(stats.items(), key=lambda x: -x[1]):
            print(f"   - {lang}: {count}")
    
    # ChromaDB
    if chroma_dir.exists():
        try:
            vector_store = ChromaVectorStore(
                persist_directory=str(chroma_dir),
                collection_name="rag_documents"
            )
            print(f"\n💾 ChromaDB:")
            print(f"   - İndekslenmiş parça sayısı: {vector_store.get_document_count()}")
        except:
            print(f"\n💾 ChromaDB: Henüz oluşturulmadı")
    
    print("=" * 50)


def main():
    """Ana fonksiyon."""
    parser = argparse.ArgumentParser(description="RAG Training Script")
    parser.add_argument("--force", "-f", action="store_true", help="Mevcut veritabanını sil ve yeniden indeksle")
    parser.add_argument("--pdf-only", action="store_true", help="Sadece PDF dosyalarını indeksle")
    parser.add_argument("--code-only", action="store_true", help="Sadece kod dosyalarını indeksle")
    parser.add_argument("--stats", "-s", action="store_true", help="İstatistikleri göster")
    parser.add_argument("--chunk-size", type=int, default=1000, help="Chunk boyutu (varsayılan: 1000)")
    parser.add_argument("--chunk-overlap", type=int, default=200, help="Chunk overlap (varsayılan: 200)")
    
    args = parser.parse_args()
    
    # Paths
    pdf_dir = project_root / "data" / "pdfs"
    code_dir = project_root / "data" / "code"
    text_dir = project_root / "data" / "docs"
    chroma_dir = project_root / "chroma_db"
    
    print_banner()
    
    # Sadece istatistik göster
    if args.stats:
        show_stats(chroma_dir, pdf_dir, code_dir)
        return
    
    # Klasörleri oluştur
    create_directories()
    
    # API key kontrolü
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("\n❌ HATA: GOOGLE_API_KEY bulunamadı!")
        print("   .env dosyasına GOOGLE_API_KEY=your_key ekleyin")
        sys.exit(1)
    print(f"✅ API Key: {api_key[:15]}...")
    
    # Dökümanları yükle
    all_documents = []
    
    if not args.code_only:
        all_documents.extend(load_pdfs(pdf_dir))
        all_documents.extend(load_texts(text_dir))
    
    if not args.pdf_only:
        all_documents.extend(load_code(code_dir))
    
    if not all_documents:
        print("\n⚠️ Hiç döküman bulunamadı!")
        print("\n📝 Dosyalarınızı şu klasörlere ekleyin:")
        print(f"   PDF'ler: {pdf_dir}")
        print(f"   Kodlar: {code_dir}")
        print(f"   Metinler: {text_dir}")
        return
    
    print(f"\n📚 Toplam {len(all_documents)} döküman yüklendi.")
    
    # Parçala
    chunks = chunk_documents(all_documents, args.chunk_size, args.chunk_overlap)
    
    if not chunks:
        print("❌ Parçalama başarısız!")
        return
    
    # Embedding oluştur
    embeddings = generate_embeddings(chunks)
    
    # ChromaDB'ye kaydet
    store_in_chromadb(chunks, embeddings, chroma_dir, args.force)
    
    # Final
    print("\n" + "=" * 50)
    print("✅ TRAİNİNG TAMAMLANDI!")
    print("=" * 50)
    print(f"   📄 Döküman: {len(all_documents)}")
    print(f"   ✂️ Parça: {len(chunks)}")
    print(f"   🧮 Vektör: {len(embeddings)}")
    print("\n💡 Şimdi soru sormak için:")
    print("   python scripts/chat.py")
    print("=" * 50)


if __name__ == "__main__":
    main()
