"""Quick RAG test without interrupting training."""
from src.rag.sentence_embeddings import SentenceEmbeddings
from src.vectorstore.chroma_store import ChromaVectorStore

print("🔄 Loading RAG system...")
vs = ChromaVectorStore(persist_directory='chroma_db', collection_name='documents')
emb = SentenceEmbeddings()

doc_count = vs.get_document_count()
print(f"✅ Database: {doc_count:,} documents loaded\n")

# Test query
question = "create_bd_cell xilinx.com axi_gpio processing_system7 set_property CONFIG example TCL block design"
print(f"❓ Question: {question}\n")

# Embed and search
query_embedding = emb.embed_text(question)
results = vs.query(query_embedding, n_results=5)

# Display results
print("📄 Top 3 Matching Documents:")
print("=" * 70)
for i in range(min(5, len(results['documents'][0]))):
    source = results['metadatas'][0][i].get('source', 'Unknown')
    text = results['documents'][0][i]
    distance = results['distances'][0][i] if 'distances' in results else 'N/A'
    
    print(f"\n{i+1}. Source: {source}")
    print(f"   Similarity: {1 - distance:.4f}" if distance != 'N/A' else "")
    print(f"   Text: {text[:300]}...")
    print("-" * 70)

print("\n✅ RAG system working! Training continues in background.")
