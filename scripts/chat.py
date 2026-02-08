#!/usr/bin/env python3
"""
Chat Script - RAG Pipeline ile Soru-Cevap

Kullanım:
    python scripts/chat.py              # İnteraktif mod
    python scripts/chat.py "Sorum"      # Tek soru sor
    python scripts/chat.py --top-k 5    # En yakın 5 parça ile yanıt
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

from src.rag.sentence_embeddings import SentenceEmbeddings
from src.rag.gemini_generator import GeminiGenerator
from src.vectorstore.chroma_store import ChromaVectorStore


def print_banner():
    """ASCII banner yazdır."""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║                    GCP-RAG-VIVADO CHAT                        ║
║                  PDF & Kod ile Soru-Cevap                     ║
╚═══════════════════════════════════════════════════════════════╝
    """)


class RAGChat:
    """RAG tabanlı chat sistemi."""
    
    def __init__(self, chroma_dir: str = "./chroma_db", top_k: int = 5):
        """Initialize chat.
        
        Args:
            chroma_dir: ChromaDB dizini
            top_k: Her sorgu için kaç parça getirileceği
        """
        self.top_k = top_k
        
        # Bileşenleri yükle
        print("🔄 Sistem başlatılıyor...")
        
        self.vector_store = ChromaVectorStore(
            persist_directory=chroma_dir,
            collection_name="vivado_rag"
        )
        self.embeddings = SentenceEmbeddings()
        self.generator = GeminiGenerator()
        
        doc_count = self.vector_store.get_document_count()
        if doc_count == 0:
            print("\n⚠️ Veritabanı boş! Önce training yapın:")
            print("   python scripts/train.py")
            sys.exit(1)
        
        print(f"✅ {doc_count} parça yüklendi.")

    def ask(self, question: str, verbose: bool = True) -> dict:
        """Soru sor ve yanıt al.
        
        Args:
            question: Kullanıcı sorusu
            verbose: Detaylı çıktı
            
        Returns:
            Yanıt ve kaynaklar
        """
        if verbose:
            print("\n" + "-" * 50)
            print(f"❓ Soru: {question}")
            print("-" * 50)
        
        # 1. Soruyu vektörleştir
        if verbose:
            print("\n🧮 Soru vektörleştiriliyor...")
        query_embedding = self.embeddings.embed_text(question)
        
        # 2. Benzer parçaları bul
        if verbose:
            print(f"🔍 En yakın {self.top_k} parça aranıyor...")
        results = self.vector_store.query(query_embedding, n_results=self.top_k)
        
        # 3. Sonuçları formatla
        retrieved_docs = []
        if verbose:
            print("\n📄 Bulunan Kaynaklar:")
        
        for i, (doc, metadata, distance) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )):
            similarity = 1 - distance
            retrieved_docs.append({
                "content": doc,
                "metadata": metadata,
                "similarity": similarity,
            })
            
            if verbose:
                source = metadata.get("filename", "Bilinmeyen")
                doc_type = metadata.get("type", "?")
                lang = metadata.get("language", "")
                lang_str = f" ({lang})" if lang else ""
                print(f"   [{i+1}] {source}{lang_str} - {similarity:.1%} benzerlik")
        
        # 4. Gemini ile yanıt oluştur
        if verbose:
            print("\n🤖 Gemini ile yanıt oluşturuluyor...")
        
        answer = self.generator.generate(question, retrieved_docs)
        
        if verbose:
            print("\n" + "=" * 50)
            print("💡 YANIT:")
            print("=" * 50)
            print(answer)
            print("=" * 50)
        
        return {
            "question": question,
            "answer": answer,
            "sources": retrieved_docs,
        }

    def interactive(self):
        """İnteraktif chat modu."""
        print("\n" + "-" * 50)
        print("💬 Soru sormaya başlayabilirsiniz!")
        print("   Çıkmak için: quit, q, exit")
        print("   Kaynakları görmek için: sources")
        print("-" * 50 + "\n")
        
        last_result = None
        
        while True:
            try:
                question = input("❓ ").strip()
                
                if not question:
                    continue
                
                if question.lower() in ["quit", "q", "exit", "cik", "çık"]:
                    print("\n👋 Görüşmek üzere!")
                    break
                
                if question.lower() == "sources" and last_result:
                    print("\n📚 Son yanıtın kaynakları:")
                    for i, src in enumerate(last_result["sources"], 1):
                        print(f"\n--- Kaynak {i} ---")
                        print(f"Dosya: {src['metadata'].get('filename', '?')}")
                        print(f"Benzerlik: {src['similarity']:.1%}")
                        print(f"İçerik (ilk 200 karakter):")
                        print(src["content"][:200] + "...")
                    print()
                    continue
                
                last_result = self.ask(question)
                print()
                
            except KeyboardInterrupt:
                print("\n\n👋 Görüşmek üzere!")
                break


def main():
    """Ana fonksiyon."""
    parser = argparse.ArgumentParser(description="RAG Chat")
    parser.add_argument("question", nargs="?", help="Sorulacak soru (opsiyonel)")
    parser.add_argument("--top-k", "-k", type=int, default=5, help="Kaç kaynak kullanılacak")
    parser.add_argument("--chroma-dir", default="./chroma_db", help="ChromaDB dizini")
    
    args = parser.parse_args()
    
    print_banner()
    
    # API key kontrolü
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ HATA: GOOGLE_API_KEY bulunamadı!")
        sys.exit(1)
    
    # Chat başlat
    chroma_path = project_root / args.chroma_dir.lstrip("./")
    chat = RAGChat(str(chroma_path), args.top_k)
    
    if args.question:
        # Tek soru modu
        chat.ask(args.question)
    else:
        # İnteraktif mod
        chat.interactive()


if __name__ == "__main__":
    main()
