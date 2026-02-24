#!/usr/bin/env python3
"""
Proje Bazlı Training Script - Her Proje Klasörü İçin Ayrı Embedding

Her proje klasörü için ayrı bir ChromaDB koleksiyonu oluşturur.

Kullanım:
    python scripts/train_by_project.py                     # Tüm projeleri indeksle
    python scripts/train_by_project.py --verbose           # Detaylı çıktı
    python scripts/train_by_project.py --force             # Mevcut koleksiyonları sil
    python scripts/train_by_project.py --project Arty-A7   # Tek proje indeksle
    python scripts/train_by_project.py --list              # Projeleri listele
    python scripts/train_by_project.py --stats             # İstatistikleri göster
"""

import sys
import os
import argparse
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

# Proje kök dizinini path'e ekle
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.utils.code_loader import CodeLoader
from src.utils.chunker import TextChunker
from src.rag.vertex_embeddings import GoogleGenAIEmbeddings
from src.vectorstore.chroma_store import ChromaVectorStore


# ==================== YARDIMCI FONKSİYONLAR ====================

def sanitize_collection_name(name: str) -> str:
    """Koleksiyon adını ChromaDB uyumlu hale getir.
    
    ChromaDB kuralları:
    - 3-63 karakter
    - Alfanumerik ve alt çizgi
    - Harf ile başlamalı
    """
    # Küçük harfe çevir
    name = name.lower()
    # Özel karakterleri alt çizgiye çevir
    name = re.sub(r'[^a-z0-9]', '_', name)
    # Birden fazla alt çizgiyi teke indir
    name = re.sub(r'_+', '_', name)
    # Başında/sonunda alt çizgi varsa kaldır
    name = name.strip('_')
    # Harf ile başlamalı
    if name and not name[0].isalpha():
        name = 'proj_' + name
    # Min 3 karakter
    if len(name) < 3:
        name = name + '_project'
    # Max 63 karakter
    if len(name) > 63:
        name = name[:63]
    return name


def get_project_folders(code_dir: Path) -> List[Path]:
    """Proje klasörlerini bul (sadece dizinler)."""
    projects = []
    for item in code_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.') and not item.name.startswith('__'):
            projects.append(item)
    return sorted(projects, key=lambda x: x.name.lower())


def print_banner():
    """ASCII banner yazdır."""
    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║              GCP-RAG-VIVADO PROJE BAZLI TRAINER                       ║
║          Her Proje İçin AYRI Embedding Koleksiyonu                    ║
╚═══════════════════════════════════════════════════════════════════════╝
    """)


def vprint(verbose: bool, message: str):
    """Verbose print."""
    if verbose:
        print(message)


# ==================== PROJE İŞLEME ====================

class ProjectTrainer:
    """Proje bazlı training yöneticisi."""
    
    def __init__(
        self,
        code_dir: Path,
        chroma_dir: Path,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        verbose: bool = False
    ):
        self.code_dir = code_dir
        self.chroma_dir = chroma_dir
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.verbose = verbose
        
        # Embedding servisi (lazy init)
        self._embeddings_service = None
        
        # ChromaDB Client - SADECE 1 KERE OLUŞTUR
        self._chroma_client = None
    
    @property
    def embeddings_service(self):
        """Lazy initialization for embeddings."""
        if self._embeddings_service is None:
            vprint(self.verbose, "   🔧 Embedding servisi başlatılıyor...")
            self._embeddings_service = GoogleGenAIEmbeddings()
        return self._embeddings_service
    
    @property
    def chroma_client(self):
        """Lazy initialization for ChromaDB client - SADECE 1 KERE."""
        if self._chroma_client is None:
            import chromadb
            from chromadb.config import Settings
            
            vprint(self.verbose, "   💾 ChromaDB PersistentClient başlatılıyor (1 kere)...")
            self.chroma_dir.mkdir(parents=True, exist_ok=True)
            
            # SQLite lock sorunları için optimizasyon
            settings = Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
            
            self._chroma_client = chromadb.PersistentClient(
                path=str(self.chroma_dir),
                settings=settings
            )
            vprint(self.verbose, "   ✅ ChromaDB client hazır")
        return self._chroma_client
    
    def load_project_code(self, project_path: Path) -> List[Dict[str, Any]]:
        """Tek projenin kod dosyalarını yükle."""
        loader = CodeLoader(str(project_path))
        
        if self.verbose:
            stats = loader.get_stats()
            if stats:
                print("      Bulunan diller:")
                for lang, count in sorted(stats.items(), key=lambda x: -x[1])[:5]:
                    print(f"         {lang}: {count} dosya")
        
        documents = loader.load_all_code()
        
        # Proje metadata ekle
        for doc in documents:
            doc["metadata"]["project"] = project_path.name
            doc["metadata"]["category"] = "code"
        
        return documents
    
    def chunk_documents(self, documents: List[Dict]) -> List[Dict]:
        """Dökümanları parçala."""
        if not documents:
            return []
        
        chunker = TextChunker(self.chunk_size, self.chunk_overlap)
        chunks = chunker.chunk_documents(documents)
        
        vprint(self.verbose, f"      ✂️ {len(documents)} dosya → {len(chunks)} parça")
        return chunks
    
    def generate_embeddings(self, chunks: List[Dict]) -> List[List[float]]:
        """Embedding vektörleri oluştur."""
        if not chunks:
            return []
        
        texts = [chunk["content"] for chunk in chunks]
        
        # Batch halinde işle
        batch_size = 100
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = self.embeddings_service.embed_texts(batch)
            all_embeddings.extend(batch_embeddings)
            
            if self.verbose:
                print(f"      📦 Embedding batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")
        
        return all_embeddings
    
    def store_project(
        self,
        project_name: str,
        chunks: List[Dict],
        embeddings: List[List[float]],
        force: bool = False
    ) -> int:
        """Projeyi ChromaDB'ye kaydet - SHARED CLIENT kullan."""
        if not chunks or not embeddings:
            return 0
        
        collection_name = sanitize_collection_name(project_name)
        
        vprint(self.verbose, f"      💾 Koleksiyon: {collection_name}")
        
        # SADECE koleksiyon al/oluştur, client'ı yeniden açma!
        try:
            if force:
                # Force ise koleksiyonu sil
                try:
                    self.chroma_client.delete_collection(name=collection_name)
                    vprint(self.verbose, f"      🔄 Mevcut koleksiyon silindi")
                except:
                    pass
            
            collection = self.chroma_client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=None
            )
        except Exception as e:
            print(f"      ❌ Koleksiyon oluşturma hatası: {e}")
            return 0
        
        # Batch halinde ekle
        batch_size = 5000
        total = len(chunks)
        
        for i in range(0, total, batch_size):
            end = min(i + batch_size, total)
            batch_chunks = chunks[i:end]
            batch_embeddings = embeddings[i:end]
            
            collection.add(
                documents=[chunk["content"] for chunk in batch_chunks],
                embeddings=batch_embeddings,
                ids=[chunk["id"] for chunk in batch_chunks],
                metadatas=[chunk["metadata"] for chunk in batch_chunks],
            )
        
        return collection.count()
    
    def process_project(self, project_path: Path, force: bool = False) -> Dict[str, Any]:
        """Tek bir projeyi işle."""
        project_name = project_path.name
        
        print(f"\n{'─'*60}")
        print(f"📁 {project_name}")
        print(f"{'─'*60}")
        
        # 1. Kod dosyalarını yükle
        vprint(self.verbose, "   📖 Kod dosyaları yükleniyor...")
        documents = self.load_project_code(project_path)
        
        if not documents:
            print(f"   ⚠️ Kod dosyası bulunamadı, atlanıyor.")
            return {"project": project_name, "files": 0, "chunks": 0, "embeddings": 0}
        
        print(f"   📄 {len(documents)} dosya bulundu")
        
        # 2. Parçala
        vprint(self.verbose, "   ✂️ Parçalanıyor...")
        chunks = self.chunk_documents(documents)
        
        if not chunks:
            print(f"   ⚠️ Parçalama başarısız.")
            return {"project": project_name, "files": len(documents), "chunks": 0, "embeddings": 0}
        
        # 3. Embedding oluştur
        vprint(self.verbose, "   🧮 Embedding oluşturuluyor...")
        embeddings = self.generate_embeddings(chunks)
        
        # 4. ChromaDB'ye kaydet
        vprint(self.verbose, "   💾 ChromaDB'ye kaydediliyor...")
        doc_count = self.store_project(project_name, chunks, embeddings, force)
        
        print(f"   ✅ {len(chunks)} parça → {doc_count} embedding kaydedildi")
        
        return {
            "project": project_name,
            "files": len(documents),
            "chunks": len(chunks),
            "embeddings": doc_count
        }
    
    def process_all_projects(self, force: bool = False, filter_pattern: Optional[str] = None) -> List[Dict]:
        """Tüm projeleri işle."""
        projects = get_project_folders(self.code_dir)
        
        # Filtre uygula
        if filter_pattern:
            pattern = filter_pattern.lower()
            projects = [p for p in projects if pattern in p.name.lower()]
        
        print(f"\n📦 {len(projects)} proje bulundu")
        
        results = []
        for i, project_path in enumerate(projects, 1):
            print(f"\n[{i}/{len(projects)}]", end="")
            result = self.process_project(project_path, force)
            results.append(result)
        
        return results


# ==================== İSTATİSTİKLER ====================

def list_projects(code_dir: Path):
    """Projeleri listele."""
    projects = get_project_folders(code_dir)
    
    print(f"\n📁 PROJE KLASÖRLERİ ({len(projects)} adet)")
    print("=" * 60)
    
    for i, project in enumerate(projects, 1):
        print(f"   {i:3d}. {project.name}")
    
    print("=" * 60)


def show_stats(chroma_dir: Path, code_dir: Path, verbose: bool = False):
    """Koleksiyon istatistiklerini göster."""
    import chromadb
    
    projects = get_project_folders(code_dir)
    
    print(f"\n📊 PROJE BAZLI İSTATİSTİKLER")
    print("=" * 70)
    
    total_docs = 0
    indexed_projects = 0
    
    # Tek bir client oluştur
    try:
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collections = client.list_collections()
        
        # Her proje için kontrol et
        for project in projects:
            collection_name = sanitize_collection_name(project.name)
            
            # Koleksiyon var mı kontrol et
            matching = [c for c in collections if c.name == collection_name]
            if matching:
                count = matching[0].count()
                if count > 0:
                    indexed_projects += 1
                    total_docs += count
                    print(f"   ✅ {project.name[:40]:<40} → {count:>6} parça")
                    if verbose:
                        print(f"      Koleksiyon: {collection_name}")
            elif verbose:
                print(f"   ⚪ {project.name[:40]:<40} → indekslenmemiş")
    except Exception as e:
        print(f"   ❌ ChromaDB hatası: {e}")
        return
    
    print("=" * 70)
    print(f"   📊 ÖZET:")
    print(f"      Toplam Proje: {len(projects)}")
    print(f"      İndekslenmiş: {indexed_projects}")
    print(f"      Toplam Parça: {total_docs}")
    print("=" * 70)


# ==================== MAIN ====================

def main():
    """Ana fonksiyon."""
    parser = argparse.ArgumentParser(description="Proje Bazlı RAG Training Script")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Detaylı çıktı göster")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Mevcut koleksiyonları sil ve yeniden indeksle")
    parser.add_argument("--project", "-p", type=str,
                        help="Sadece belirtilen projeyi indeksle (isim içermesi yeterli)")
    parser.add_argument("--list", "-l", action="store_true",
                        help="Projeleri listele")
    parser.add_argument("--stats", "-s", action="store_true",
                        help="İstatistikleri göster")
    parser.add_argument("--chunk-size", type=int, default=1000,
                        help="Chunk boyutu (varsayılan: 1000)")
    parser.add_argument("--chunk-overlap", type=int, default=200,
                        help="Chunk overlap (varsayılan: 200)")
    
    args = parser.parse_args()
    
    # Paths
    code_dir = project_root / "data" / "code"
    chroma_dir = project_root / "chroma_db"
    
    print_banner()
    
    # Liste göster
    if args.list:
        list_projects(code_dir)
        return
    
    # İstatistik göster
    if args.stats:
        show_stats(chroma_dir, code_dir, args.verbose)
        return
    
    # API key kontrolü
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("\n❌ HATA: GOOGLE_API_KEY bulunamadı!")
        print("   .env dosyasına GOOGLE_API_KEY=your_key ekleyin")
        sys.exit(1)
    print(f"✅ API Key: {api_key[:15]}...")
    
    # Trainer oluştur
    trainer = ProjectTrainer(
        code_dir=code_dir,
        chroma_dir=chroma_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        verbose=args.verbose
    )
    
    # Tek proje mi yoksa tümü mü?
    if args.project:
        # Tek proje
        matching = [p for p in get_project_folders(code_dir) 
                   if args.project.lower() in p.name.lower()]
        
        if not matching:
            print(f"\n❌ '{args.project}' ile eşleşen proje bulunamadı.")
            print("   Projeleri görmek için: python scripts/train_by_project.py --list")
            return
        
        if len(matching) > 1:
            print(f"\n⚠️ '{args.project}' ile {len(matching)} proje eşleşti:")
            for p in matching:
                print(f"   - {p.name}")
            print("\n   Daha spesifik bir isim girin.")
            return
        
        results = [trainer.process_project(matching[0], args.force)]
    else:
        # Tüm projeler
        results = trainer.process_all_projects(args.force)
    
    # Özet
    print("\n" + "=" * 70)
    print("✅ PROJE BAZLI TRAİNİNG TAMAMLANDI!")
    print("=" * 70)
    
    total_files = sum(r["files"] for r in results)
    total_chunks = sum(r["chunks"] for r in results)
    total_embeddings = sum(r["embeddings"] for r in results)
    successful = len([r for r in results if r["embeddings"] > 0])
    
    print(f"   📁 İşlenen Proje: {len(results)}")
    print(f"   ✅ Başarılı: {successful}")
    print(f"   📄 Toplam Dosya: {total_files}")
    print(f"   ✂️ Toplam Parça: {total_chunks}")
    print(f"   🧮 Toplam Embedding: {total_embeddings}")
    
    print("\n💡 İstatistikleri görmek için:")
    print("   python scripts/train_by_project.py --stats")
    print("=" * 70)


if __name__ == "__main__":
    main()
