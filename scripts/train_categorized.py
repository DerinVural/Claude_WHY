#!/usr/bin/env python3
"""
Kategorize Training Script - PDF ve Kod için Ayrı Embedding'ler

Kullanım:
    python scripts/train_categorized.py                # Tüm kategorileri ayrı indeksle
    python scripts/train_categorized.py --force        # Mevcut veritabanlarını sil ve yeniden indeksle
    python scripts/train_categorized.py --pdf-only     # Sadece PDF koleksiyonunu oluştur
    python scripts/train_categorized.py --code-only    # Sadece kod koleksiyonunu oluştur
    python scripts/train_categorized.py --stats        # İstatistikleri göster
"""

import sys
import os
import argparse
from pathlib import Path
from typing import List, Dict, Any

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


# ==================== KONFİGÜRASYON ====================

# Kategori tanımları
CATEGORIES = {
    "pdf": {
        "name": "PDF Dökümanları",
        "collection_name": "pdf_documents",
        "emoji": "📄",
        "description": "PDF dosyalarından oluşturulan embedding'ler",
    },
    "code": {
        "name": "Kod Dosyaları",
        "collection_name": "code_documents", 
        "emoji": "💻",
        "description": "Kaynak kod dosyalarından oluşturulan embedding'ler",
    },
    "docs": {
        "name": "Metin Dökümanları",
        "collection_name": "text_documents",
        "emoji": "📝",
        "description": "Metin dosyalarından (txt, md) oluşturulan embedding'ler",
    },
}


def print_banner():
    """ASCII banner yazdır."""
    print("""
╔════════════════════════════════════════════════════════════════════╗
║             GCP-RAG-VIVADO KATEGORIZED TRAINER                     ║
║         PDF & Kod için AYRI Embedding Koleksiyonları               ║
╚════════════════════════════════════════════════════════════════════╝
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


def load_pdfs(pdf_dir: Path) -> List[Dict[str, Any]]:
    """PDF dosyalarını yükle."""
    print(f"\n{CATEGORIES['pdf']['emoji']} PDF Dosyaları Yükleniyor...")
    print("-" * 50)
    
    loader = PDFLoader(str(pdf_dir))
    documents = loader.load_all_pdfs()
    
    # Kategori bilgisi ekle
    for doc in documents:
        doc["metadata"]["category"] = "pdf"
    
    if not documents:
        print(f"   ⚠️ '{pdf_dir}' klasöründe PDF bulunamadı.")
    else:
        print(f"   ✅ {len(documents)} PDF yüklendi.")
    
    return documents


def load_code(code_dir: Path) -> List[Dict[str, Any]]:
    """Kod dosyalarını yükle."""
    print(f"\n{CATEGORIES['code']['emoji']} Kod Dosyaları Yükleniyor...")
    print("-" * 50)
    
    loader = CodeLoader(str(code_dir))
    
    # İstatistikleri göster
    stats = loader.get_stats()
    if stats:
        print("   Bulunan diller:")
        for lang, count in sorted(stats.items(), key=lambda x: -x[1])[:10]:
            print(f"      {lang}: {count} dosya")
    
    documents = loader.load_all_code()
    
    # Kategori bilgisi ekle
    for doc in documents:
        doc["metadata"]["category"] = "code"
    
    if not documents:
        print(f"   ⚠️ '{code_dir}' klasöründe kod dosyası bulunamadı.")
    else:
        print(f"   ✅ {len(documents)} kod dosyası yüklendi.")
    
    return documents


def load_texts(text_dir: Path) -> List[Dict[str, Any]]:
    """Metin dosyalarını yükle."""
    print(f"\n{CATEGORIES['docs']['emoji']} Metin Dosyaları Yükleniyor...")
    print("-" * 50)
    
    loader = PDFLoader(str(text_dir))
    documents = loader.load_text_files()
    
    # Kategori bilgisi ekle
    for doc in documents:
        doc["metadata"]["category"] = "docs"
    
    if not documents:
        print(f"   ⚠️ '{text_dir}' klasöründe metin dosyası bulunamadı.")
    else:
        print(f"   ✅ {len(documents)} metin dosyası yüklendi.")
    
    return documents


def chunk_documents(documents: List[Dict], chunk_size: int = 1000, chunk_overlap: int = 200) -> List[Dict]:
    """Dökümanları parçala."""
    if not documents:
        return []
    
    chunker = TextChunker(chunk_size, chunk_overlap)
    chunks = chunker.chunk_documents(documents)
    
    print(f"   ✂️ {len(documents)} döküman → {len(chunks)} parça")
    return chunks


def generate_embeddings(chunks: List[Dict]) -> List[List[float]]:
    """Embedding vektörleri oluştur."""
    if not chunks:
        return []
    
    print(f"   🧮 {len(chunks)} parça için embedding oluşturuluyor...")
    
    embeddings_service = GoogleGenAIEmbeddings()
    texts = [chunk["content"] for chunk in chunks]
    
    # Batch halinde işle (API limitleri için)
    batch_size = 100
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_embeddings = embeddings_service.embed_texts(batch)
        all_embeddings.extend(batch_embeddings)
        print(f"      📦 Batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1} tamamlandı")
    
    print(f"   ✅ {len(all_embeddings)} embedding vektörü oluşturuldu")
    return all_embeddings


def store_category(
    category_key: str,
    chunks: List[Dict],
    embeddings: List[List[float]],
    chroma_dir: Path,
    force: bool = False
):
    """Kategori için ChromaDB koleksiyonu oluştur."""
    if not chunks or not embeddings:
        print(f"   ⚠️ {category_key} için veri yok, atlanıyor.")
        return
    
    category = CATEGORIES[category_key]
    collection_name = category["collection_name"]
    
    print(f"\n{category['emoji']} {category['name']} ChromaDB'ye Kaydediliyor...")
    print(f"   Koleksiyon: {collection_name}")
    print("-" * 50)
    
    vector_store = ChromaVectorStore(
        persist_directory=str(chroma_dir),
        collection_name=collection_name
    )
    
    # Eğer force ise mevcut koleksiyonu sil
    if force and not vector_store.is_empty():
        print(f"   🔄 '{collection_name}' koleksiyonu temizleniyor...")
        vector_store.delete_collection()
        # Yeniden oluştur
        vector_store = ChromaVectorStore(
            persist_directory=str(chroma_dir),
            collection_name=collection_name
        )
    
    # Dökümanları batch halinde ekle
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
    
    print(f"   ✅ Toplam: {vector_store.get_document_count()} döküman")


def process_category(
    category_key: str,
    documents: List[Dict],
    chroma_dir: Path,
    chunk_size: int,
    chunk_overlap: int,
    force: bool
):
    """Tek bir kategoriyi işle: parçala, embedding oluştur, kaydet."""
    category = CATEGORIES[category_key]
    
    print(f"\n{'='*60}")
    print(f"{category['emoji']} {category['name'].upper()} İŞLENİYOR")
    print(f"{'='*60}")
    
    if not documents:
        print(f"   ⚠️ Bu kategori için döküman yok.")
        return {"chunks": 0, "embeddings": 0}
    
    # Parçala
    chunks = chunk_documents(documents, chunk_size, chunk_overlap)
    
    if not chunks:
        return {"chunks": 0, "embeddings": 0}
    
    # Embedding oluştur
    embeddings = generate_embeddings(chunks)
    
    # ChromaDB'ye kaydet
    store_category(category_key, chunks, embeddings, chroma_dir, force)
    
    return {"chunks": len(chunks), "embeddings": len(embeddings)}


def show_stats(chroma_dir: Path, pdf_dir: Path, code_dir: Path, text_dir: Path):
    """İstatistikleri göster."""
    print("\n" + "=" * 60)
    print("📊 KATEGORİZE İSTATİSTİKLER")
    print("=" * 60)
    
    # Kaynak dosya sayıları
    print("\n📁 KAYNAK DOSYALAR:")
    print("-" * 40)
    
    # PDF sayısı
    pdf_count = len(list(pdf_dir.glob("**/*.pdf"))) if pdf_dir.exists() else 0
    print(f"   📄 PDF Dosyaları: {pdf_count}")
    
    # Kod dosyaları
    if code_dir.exists():
        code_loader = CodeLoader(str(code_dir))
        stats = code_loader.get_stats()
        total_code = sum(stats.values())
        print(f"   💻 Kod Dosyaları: {total_code}")
        for lang, count in sorted(stats.items(), key=lambda x: -x[1])[:5]:
            print(f"      - {lang}: {count}")
    else:
        print(f"   💻 Kod Dosyaları: 0")
    
    # Metin dosyaları
    txt_count = 0
    if text_dir.exists():
        txt_count = len(list(text_dir.glob("*.txt"))) + len(list(text_dir.glob("*.md")))
    print(f"   📝 Metin Dosyaları: {txt_count}")
    
    # ChromaDB koleksiyonları
    print("\n💾 CHROMADB KOLEKSİYONLARI:")
    print("-" * 40)
    
    if chroma_dir.exists():
        for cat_key, cat_info in CATEGORIES.items():
            try:
                vector_store = ChromaVectorStore(
                    persist_directory=str(chroma_dir),
                    collection_name=cat_info["collection_name"]
                )
                count = vector_store.get_document_count()
                print(f"   {cat_info['emoji']} {cat_info['name']}: {count} parça")
                print(f"      Koleksiyon: {cat_info['collection_name']}")
            except Exception as e:
                print(f"   {cat_info['emoji']} {cat_info['name']}: Henüz oluşturulmadı")
    else:
        print("   ChromaDB henüz oluşturulmadı.")
    
    print("=" * 60)


def main():
    """Ana fonksiyon."""
    parser = argparse.ArgumentParser(description="Kategorize RAG Training Script")
    parser.add_argument("--force", "-f", action="store_true", 
                        help="Mevcut veritabanlarını sil ve yeniden indeksle")
    parser.add_argument("--pdf-only", action="store_true", 
                        help="Sadece PDF koleksiyonunu oluştur")
    parser.add_argument("--code-only", action="store_true", 
                        help="Sadece kod koleksiyonunu oluştur")
    parser.add_argument("--docs-only", action="store_true", 
                        help="Sadece metin koleksiyonunu oluştur")
    parser.add_argument("--stats", "-s", action="store_true", 
                        help="İstatistikleri göster")
    parser.add_argument("--chunk-size", type=int, default=1000, 
                        help="Chunk boyutu (varsayılan: 1000)")
    parser.add_argument("--chunk-overlap", type=int, default=200, 
                        help="Chunk overlap (varsayılan: 200)")
    
    args = parser.parse_args()
    
    # Paths
    pdf_dir = project_root / "data" / "pdfs"
    code_dir = project_root / "data" / "code"
    text_dir = project_root / "data" / "docs"
    chroma_dir = project_root / "chroma_db"
    
    print_banner()
    
    # Sadece istatistik göster
    if args.stats:
        show_stats(chroma_dir, pdf_dir, code_dir, text_dir)
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
    
    # İşlenecek kategorileri belirle
    process_pdf = not args.code_only and not args.docs_only
    process_code = not args.pdf_only and not args.docs_only
    process_docs = not args.pdf_only and not args.code_only
    
    # Sonuç özeti
    results = {}
    
    # ==================== PDF KATEGORİSİ ====================
    if process_pdf:
        pdf_documents = load_pdfs(pdf_dir)
        results["pdf"] = process_category(
            "pdf", pdf_documents, chroma_dir,
            args.chunk_size, args.chunk_overlap, args.force
        )
    
    # ==================== KOD KATEGORİSİ ====================
    if process_code:
        code_documents = load_code(code_dir)
        results["code"] = process_category(
            "code", code_documents, chroma_dir,
            args.chunk_size, args.chunk_overlap, args.force
        )
    
    # ==================== METİN KATEGORİSİ ====================
    if process_docs:
        text_documents = load_texts(text_dir)
        results["docs"] = process_category(
            "docs", text_documents, chroma_dir,
            args.chunk_size, args.chunk_overlap, args.force
        )
    
    # ==================== ÖZET ====================
    print("\n" + "=" * 60)
    print("✅ KATEGORİZE TRAİNİNG TAMAMLANDI!")
    print("=" * 60)
    
    total_chunks = 0
    total_embeddings = 0
    
    for cat_key, cat_result in results.items():
        if cat_result:
            cat_info = CATEGORIES[cat_key]
            print(f"   {cat_info['emoji']} {cat_info['name']}:")
            print(f"      Parça: {cat_result['chunks']}")
            print(f"      Embedding: {cat_result['embeddings']}")
            total_chunks += cat_result["chunks"]
            total_embeddings += cat_result["embeddings"]
    
    print("-" * 40)
    print(f"   📊 TOPLAM:")
    print(f"      Parça: {total_chunks}")
    print(f"      Embedding: {total_embeddings}")
    
    print("\n💡 Koleksiyonları görmek için:")
    print("   python scripts/train_categorized.py --stats")
    print("\n💡 Soru sormak için chat.py'ı güncelleyin veya:")
    print("   - pdf_documents: PDF'lerden soru sor")
    print("   - code_documents: Kodlardan soru sor")
    print("=" * 60)


if __name__ == "__main__":
    main()
