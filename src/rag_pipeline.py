"""
GCP-RAG-VIVADO: RAG Pipeline with ChromaDB and Gemini

İki modlu çalışma:
1. Ingestion (Veri Hazırlama): PDF'leri oku, parçala, vektörleştir, ChromaDB'ye kaydet
2. Query (Sorgulama): Soru sor, benzer dökümanları bul, Gemini ile cevap üret
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.pdf_loader import PDFLoader
from src.utils.chunker import TextChunker
from src.rag.vertex_embeddings import GoogleGenAIEmbeddings
from src.rag.gemini_generator import GeminiGenerator
from src.vectorstore.chroma_store import ChromaVectorStore


class RAGPipeline:
    """Complete RAG pipeline with local ChromaDB storage."""

    def __init__(
        self,
        data_directory: str = "./data",
        chroma_directory: str = "./chroma_db",
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        """Initialize RAG pipeline.

        Args:
            data_directory: Directory containing source documents
            chroma_directory: Directory for ChromaDB persistence
            chunk_size: Size of text chunks
            chunk_overlap: Overlap between chunks
        """
        self.data_directory = data_directory
        self.chroma_directory = chroma_directory
        
        # Initialize components
        self.loader = PDFLoader(data_directory)
        self.chunker = TextChunker(chunk_size, chunk_overlap)
        self.embeddings = GoogleGenAIEmbeddings()
        self.generator = GeminiGenerator()
        self.vector_store = ChromaVectorStore(chroma_directory)

        print("🚀 RAG Pipeline başlatıldı!")
        print(f"   📂 Veri klasörü: {data_directory}")
        print(f"   💾 ChromaDB: {chroma_directory}")
        print(f"   📊 Mevcut döküman sayısı: {self.vector_store.get_document_count()}")

    # ==================== EVRE 1: VERİ HAZIRLAMA ====================

    def ingest(self, force: bool = False) -> int:
        """Ingest documents into the vector store.

        Args:
            force: Force re-ingestion even if documents exist

        Returns:
            Number of chunks ingested
        """
        # Check if already ingested
        if not force and not self.vector_store.is_empty():
            count = self.vector_store.get_document_count()
            print(f"ℹ️ Veritabanında zaten {count} döküman var.")
            print("   Yeniden indekslemek için: pipeline.ingest(force=True)")
            return count

        if force:
            print("🔄 Veritabanı temizleniyor...")
            self.vector_store.clear()

        print("\n" + "=" * 50)
        print("📥 EVRE 1: VERİ HAZIRLAMA (Ingestion)")
        print("=" * 50)

        # Step 1: Load documents
        print("\n📖 Adım 1: Dökümanlar yükleniyor...")
        documents = self.loader.load_all_documents()
        
        if not documents:
            print("❌ Hiç döküman bulunamadı. /data klasörüne PDF veya TXT ekleyin.")
            return 0

        # Step 2: Chunk documents
        print("✂️ Adım 2: Dökümanlar parçalanıyor...")
        chunks = self.chunker.chunk_documents(documents)
        print(f"   📊 {len(documents)} döküman → {len(chunks)} parça")

        # Step 3: Generate embeddings
        print("\n🧮 Adım 3: Vektörler oluşturuluyor (Vertex AI)...")
        texts = [chunk["content"] for chunk in chunks]
        embeddings = self.embeddings.embed_texts(texts)

        # Step 4: Store in ChromaDB
        print("\n💾 Adım 4: ChromaDB'ye kaydediliyor...")
        self.vector_store.add_documents(
            documents=texts,
            embeddings=embeddings,
            ids=[chunk["id"] for chunk in chunks],
            metadatas=[chunk["metadata"] for chunk in chunks],
        )

        print("\n" + "=" * 50)
        print(f"✅ Ingestion tamamlandı! {len(chunks)} parça indekslendi.")
        print("=" * 50 + "\n")

        return len(chunks)

    # ==================== EVRE 2: SORU-CEVAP ====================

    def query(self, question: str, top_k: int = 3) -> dict:
        """Query the RAG pipeline.

        Args:
            question: User question
            top_k: Number of relevant chunks to retrieve

        Returns:
            Response with answer and sources
        """
        if self.vector_store.is_empty():
            return {
                "question": question,
                "answer": "❌ Veritabanı boş. Önce `ingest()` çalıştırın.",
                "sources": [],
            }

        print("\n" + "=" * 50)
        print("🔍 EVRE 2: SORU-CEVAP (Retrieval & Generation)")
        print("=" * 50)

        # Step 1: Embed the question
        print(f"\n❓ Soru: {question}")
        print("\n🧮 Adım 1: Soru vektörleştiriliyor...")
        query_embedding = self.embeddings.embed_text(question)

        # Step 2: Search for similar chunks
        print(f"🔎 Adım 2: En yakın {top_k} parça aranıyor...")
        results = self.vector_store.query(query_embedding, n_results=top_k)

        # Format retrieved documents
        retrieved_docs = []
        for i, (doc, metadata, distance) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )):
            similarity = 1 - distance  # Convert distance to similarity
            retrieved_docs.append({
                "content": doc,
                "metadata": metadata,
                "similarity": similarity,
            })
            source = metadata.get("filename", "Bilinmeyen")
            print(f"   📄 [{i+1}] {source} (benzerlik: {similarity:.2%})")

        # Step 3: Generate response with Gemini
        print("\n🤖 Adım 3: Gemini ile yanıt üretiliyor...")
        answer = self.generator.generate(question, retrieved_docs)

        print("\n" + "=" * 50)
        print("💡 YANIT:")
        print("=" * 50)
        print(answer)
        print("=" * 50 + "\n")

        return {
            "question": question,
            "answer": answer,
            "sources": retrieved_docs,
        }

    def ask(self, question: str) -> str:
        """Simple query interface - returns just the answer.

        Args:
            question: User question

        Returns:
            Answer string
        """
        result = self.query(question)
        return result["answer"]

    def status(self) -> dict:
        """Get pipeline status.

        Returns:
            Status information
        """
        return {
            "data_directory": self.data_directory,
            "chroma_directory": self.chroma_directory,
            "document_count": self.vector_store.get_document_count(),
            "is_ready": not self.vector_store.is_empty(),
        }


def main():
    """Main entry point with interactive mode."""
    print("\n" + "🎯" * 25)
    print("  GCP-RAG-VIVADO: RAG Pipeline")
    print("🎯" * 25 + "\n")

    # Initialize pipeline
    pipeline = RAGPipeline()

    # Check if ingestion is needed
    if pipeline.vector_store.is_empty():
        print("📝 Veritabanı boş. Dökümanları indeksliyorum...")
        pipeline.ingest()
    else:
        print(f"✅ Veritabanında {pipeline.vector_store.get_document_count()} döküman hazır.")

    # Interactive mode
    print("\n" + "-" * 50)
    print("💬 Soru sormaya başlayabilirsiniz!")
    print("   Çıkmak için 'quit' veya 'q' yazın.")
    print("   Yeniden indekslemek için 'reindex' yazın.")
    print("-" * 50 + "\n")

    while True:
        try:
            question = input("❓ Sorunuz: ").strip()
            
            if not question:
                continue
            
            if question.lower() in ["quit", "q", "exit", "çık"]:
                print("\n👋 Görüşmek üzere!")
                break
            
            if question.lower() == "reindex":
                pipeline.ingest(force=True)
                continue
            
            pipeline.query(question)
            
        except KeyboardInterrupt:
            print("\n\n👋 Görüşmek üzere!")
            break


if __name__ == "__main__":
    main()
