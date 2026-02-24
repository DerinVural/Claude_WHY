#!/usr/bin/env python3
"""
Incremental Training Script - Küçük parçalarla güvenli eğitim

Büyük dosyaları küçük parçalara böler ve her dosyadan sonra checkpoint kaydeder.
Bellek kullanımını minimize eder.

Kullanım:
    python scripts/train_incremental.py              # Kaldığı yerden devam et
    python scripts/train_incremental.py --reset      # Sıfırdan başla
    python scripts/train_incremental.py --stats      # İstatistikleri göster
"""

import sys
import os
import json
import argparse
import gc
from pathlib import Path
from datetime import datetime
import time

# Proje kök dizinini path'e ekle
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# Checkpoint dosyası
CHECKPOINT_FILE = project_root / "training_checkpoint_incremental.json"

# Küçük batch ve chunk ayarları - bellek tasarrufu için
CHUNK_SIZE = 500  # Daha küçük parçalar
CHUNK_OVERLAP = 50  # Daha az overlap
EMBEDDING_BATCH_SIZE = 20  # Çok küçük batch'ler
FILE_BATCH_SIZE = 5  # Her 5 dosyada bir kaydet


def load_checkpoint():
    """Checkpoint yükle."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "processed_files": [],
        "current_file_index": 0,
        "current_chunk_index": 0,
        "total_embedded": 0,
        "last_update": None,
        "status": "not_started",
        "errors": []
    }


def save_checkpoint(checkpoint):
    """Checkpoint kaydet."""
    checkpoint["last_update"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)


def print_banner():
    print("""
╔═══════════════════════════════════════════════════════════════╗
║          GCP-RAG-VIVADO INCREMENTAL TRAINER                   ║
║        Küçük Parçalarla Güvenli Eğitim Aracı                  ║
╚═══════════════════════════════════════════════════════════════╝
    """)


def chunk_text_small(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list:
    """Metni küçük parçalara böl."""
    if not text or len(text) == 0:
        return []
    
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # Doğal sınırda kes
        if end < len(text):
            # Paragraf sonu ara
            para_break = text.rfind("\n\n", start, end)
            if para_break > start + chunk_size // 2:
                end = para_break + 2
            else:
                # Cümle sonu ara
                for sep in [". ", ".\n", "? ", "!\n", "\n"]:
                    sent_break = text.rfind(sep, start, end)
                    if sent_break > start + chunk_size // 3:
                        end = sent_break + len(sep)
                        break
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = end - overlap
        if start >= len(text):
            break
    
    return chunks


def process_single_file(file_path: Path, file_type: str, embeddings, vector_store, doc_id_prefix: str) -> int:
    """Tek bir dosyayı işle ve embedding'leri kaydet. Bellek tasarrufu için."""
    try:
        # Dosyayı oku
        if file_type == "pdf":
            from src.utils.pdf_loader import PDFLoader
            loader = PDFLoader(str(file_path.parent))
            content = loader.load_pdf(str(file_path))
        else:
            # Kod veya text dosyası
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
                    content = f.read()
        
        if not content or len(content.strip()) < 10:
            return 0
        
        # Küçük parçalara böl
        chunks = chunk_text_small(content)
        
        if not chunks:
            return 0
        
        # Her chunk'ı ayrı ayrı işle (bellek tasarrufu)
        embedded_count = 0
        
        for i in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
            batch_chunks = chunks[i:i + EMBEDDING_BATCH_SIZE]
            
            try:
                # Embedding oluştur
                vectors = embeddings.embed_texts(batch_chunks)
                
                # IDs ve metadata
                ids = [f"{doc_id_prefix}_chunk_{i+j}" for j in range(len(batch_chunks))]
                metadatas = [{
                    "source": str(file_path),
                    "filename": file_path.name,
                    "type": file_type,
                    "chunk_index": i + j,
                    "total_chunks": len(chunks)
                } for j in range(len(batch_chunks))]
                
                # ChromaDB'ye kaydet (sıra: documents, embeddings, ids, metadatas)
                vector_store.add_documents(batch_chunks, vectors, ids, metadatas)
                embedded_count += len(batch_chunks)
                
                # Kısa bekleme (rate limiting)
                time.sleep(0.1)
                
            except Exception as e:
                print(f"    ⚠️ Batch hatası: {e}")
                time.sleep(1)  # Hata sonrası bekle
                continue
        
        # Bellek temizle
        del content
        del chunks
        gc.collect()
        
        return embedded_count
        
    except Exception as e:
        print(f"  ❌ Dosya hatası ({file_path.name}): {e}")
        return 0


def get_all_files() -> list:
    """Tüm eğitim dosyalarını listele."""
    files = []
    
    # PDF'ler
    pdf_dir = project_root / "data" / "pdfs"
    if pdf_dir.exists():
        for pdf_path in pdf_dir.glob("**/*.pdf"):
            files.append(("pdf", pdf_path))
    
    # Kod dosyaları
    code_dir = project_root / "data" / "code"
    code_extensions = [".v", ".sv", ".vhd", ".tcl", ".xdc", ".c", ".h", ".py"]
    
    if code_dir.exists():
        for ext in code_extensions:
            for code_path in code_dir.glob(f"**/*{ext}"):
                # Bazı dosyaları atla
                if any(skip in str(code_path) for skip in ["__pycache__", ".git", "node_modules"]):
                    continue
                files.append(("code", code_path))
    
    # Markdown ve text dosyaları
    docs_dir = project_root / "data" / "docs"
    if docs_dir.exists():
        for ext in [".md", ".txt", ".rst"]:
            for doc_path in docs_dir.glob(f"**/*{ext}"):
                files.append(("text", doc_path))
    
    return files


def train_incremental():
    """Incremental eğitim - dosya dosya işle."""
    from config.rag_config import load_config
    
    config = load_config()
    checkpoint = load_checkpoint()
    
    print(f"\n🔄 Checkpoint yüklendi: {checkpoint.get('status', 'Yeni başlangıç')}")
    print(f"   Daha önce işlenen: {len(checkpoint.get('processed_files', []))} dosya")
    print(f"   Toplam embedding: {checkpoint.get('total_embedded', 0)}")
    
    # Embeddings ve vector store
    print("\n🔧 Servisleri başlatılıyor...")
    
    try:
        print("   📌 Embeddings yükleniyor...")
        from src.rag.vertex_embeddings import GoogleGenAIEmbeddings
        embeddings = GoogleGenAIEmbeddings(
            api_key=config.embedding.api_key,
            model_name=config.embedding.model_name
        )
        print("   ✅ Embeddings hazır")
    except Exception as e:
        print(f"   ❌ Embeddings hatası: {e}")
        return
    
    try:
        print("   📌 ChromaDB yükleniyor...")
        from src.vectorstore.chroma_store import ChromaVectorStore
        vector_store = ChromaVectorStore(
            persist_directory=config.vector_store.persist_directory,
            collection_name=config.vector_store.collection_name
        )
        print("   ✅ ChromaDB hazır")
    except Exception as e:
        print(f"   ❌ ChromaDB hatası: {e}")
        return
    
    # Tüm dosyaları al
    print("\n📂 Dosyalar taranıyor (bu biraz sürebilir)...")
    all_files = get_all_files()
    processed_files = set(checkpoint.get("processed_files", []))
    
    print(f"   Toplam {len(all_files)} dosya bulundu.")
    print(f"   Kalan: {len(all_files) - len(processed_files)} dosya")
    
    # İşlenmemiş dosyaları filtrele
    files_to_process = [(ftype, fpath) for ftype, fpath in all_files 
                        if str(fpath) not in processed_files]
    
    if not files_to_process:
        print("\n✅ Tüm dosyalar zaten işlenmiş!")
        return
    
    total_embedded = checkpoint.get("total_embedded", 0)
    
    print(f"\n🚀 {len(files_to_process)} dosya işlenecek...")
    print("-" * 50)
    
    for idx, (file_type, file_path) in enumerate(files_to_process):
        file_key = str(file_path)
        doc_id = f"doc_{len(processed_files) + idx}"
        
        # Dosya boyutunu kontrol et
        try:
            file_size = file_path.stat().st_size
            if file_size > 10 * 1024 * 1024:  # 10MB'dan büyük
                print(f"  ⏭️ Atlanıyor (çok büyük): {file_path.name} ({file_size // 1024 // 1024}MB)")
                processed_files.add(file_key)
                continue
        except Exception:
            pass
        
        print(f"\n[{idx + 1}/{len(files_to_process)}] 📄 {file_path.name}")
        
        try:
            embedded = process_single_file(file_path, file_type, embeddings, vector_store, doc_id)
            
            if embedded > 0:
                total_embedded += embedded
                print(f"  ✅ {embedded} parça eklendi (Toplam: {total_embedded})")
            else:
                print(f"  ⏭️ Boş veya okunamadı")
            
            # Checkpoint kaydet
            processed_files.add(file_key)
            checkpoint["processed_files"] = list(processed_files)
            checkpoint["total_embedded"] = total_embedded
            checkpoint["status"] = "in_progress"
            save_checkpoint(checkpoint)
            
        except KeyboardInterrupt:
            print("\n\n⚠️ Kullanıcı tarafından durduruldu!")
            checkpoint["processed_files"] = list(processed_files)
            checkpoint["total_embedded"] = total_embedded
            checkpoint["status"] = "interrupted"
            save_checkpoint(checkpoint)
            return
            
        except Exception as e:
            print(f"  ❌ Hata: {e}")
            checkpoint["errors"].append({
                "file": file_key,
                "error": str(e),
                "time": datetime.now().isoformat()
            })
            # Hataya rağmen devam et
            processed_files.add(file_key)
            save_checkpoint(checkpoint)
            time.sleep(1)
            continue
        
        # Her birkaç dosyada bellek temizle
        if (idx + 1) % 10 == 0:
            gc.collect()
            print(f"  📊 İlerleme: {idx + 1}/{len(files_to_process)} ({(idx + 1) * 100 // len(files_to_process)}%)")
    
    # Tamamlandı
    checkpoint["status"] = "completed"
    checkpoint["processed_files"] = list(processed_files)
    checkpoint["total_embedded"] = total_embedded
    save_checkpoint(checkpoint)
    
    print("\n" + "=" * 50)
    print("✅ EĞİTİM TAMAMLANDI!")
    print(f"   İşlenen dosya: {len(processed_files)}")
    print(f"   Toplam parça: {total_embedded}")
    try:
        print(f"   ChromaDB'de: {vector_store.count()}")
    except:
        pass
    print("=" * 50)


def show_stats():
    """İstatistikleri göster."""
    checkpoint = load_checkpoint()
    
    print("\n📊 EĞİTİM DURUMU (Incremental)")
    print("=" * 50)
    
    print(f"\n📝 Checkpoint:")
    print(f"   Son güncelleme: {checkpoint.get('last_update', 'Yok')}")
    print(f"   Durum: {checkpoint.get('status', 'Bilinmiyor')}")
    print(f"   İşlenen dosya: {len(checkpoint.get('processed_files', []))}")
    print(f"   Toplam embedding: {checkpoint.get('total_embedded', 0)}")
    print(f"   Hata sayısı: {len(checkpoint.get('errors', []))}")
    
    # ChromaDB durumu
    try:
        from src.vectorstore.chroma_store import ChromaVectorStore
        from config.rag_config import load_config
        
        config = load_config()
        vector_store = ChromaVectorStore(
            persist_directory=config.vector_store.persist_directory,
            collection_name=config.vector_store.collection_name
        )
        print(f"\n💾 ChromaDB:")
        print(f"   İndekslenmiş parça: {vector_store.count()}")
    except Exception as e:
        print(f"\n❌ ChromaDB hatası: {e}")
    
    print("=" * 50)


def reset_training():
    """Eğitimi sıfırla."""
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("✅ Checkpoint silindi.")
    
    print("⚠️ ChromaDB'yi temizlemek için --clear-db flag'ini kullanın.")


def main():
    parser = argparse.ArgumentParser(description="Incremental RAG eğitimi")
    parser.add_argument("--reset", action="store_true", help="Checkpoint'i sıfırla")
    parser.add_argument("--stats", action="store_true", help="İstatistikleri göster")
    parser.add_argument("--clear-db", action="store_true", help="ChromaDB'yi temizle")
    args = parser.parse_args()
    
    print_banner()
    
    if args.stats:
        show_stats()
    elif args.reset:
        reset_training()
    elif args.clear_db:
        from src.vectorstore.chroma_store import ChromaVectorStore
        from config.rag_config import load_config
        config = load_config()
        vector_store = ChromaVectorStore(
            persist_directory=config.vector_store.persist_directory,
            collection_name=config.vector_store.collection_name
        )
        vector_store.clear()
        print("✅ ChromaDB temizlendi.")
    else:
        train_incremental()


if __name__ == "__main__":
    main()
