"""ChromaDB vector store for local document embeddings."""

import os
# Disable ChromaDB telemetry and default embedding download
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
from pathlib import Path


class NoEmbedding:
    """Dummy embedding function - we provide our own embeddings."""
    pass


class ChromaVectorStore:
    """Local vector store using ChromaDB."""

    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        collection_name: str = "documents",
        verbose: bool = False,
    ):
        """Initialize ChromaDB vector store.

        Args:
            persist_directory: Directory to persist the database
            collection_name: Name of the collection
            verbose: Print detailed progress
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.verbose = verbose
        
        # Ensure directory exists
        if verbose:
            print(f"        -> Klasor kontrol: {persist_directory}", flush=True)
        Path(persist_directory).mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB client with persistence
        if verbose:
            print("        -> ChromaDB PersistentClient baslatiliyor...", flush=True)
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        if verbose:
            print("        -> Collection olusturuluyor...", flush=True)
        
        # embedding_function=None - biz kendi embeddinglerimizi sagliyoruz
        from chromadb.utils import embedding_functions
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None  # Varsayilan modeli indirme!
        )
        if verbose:
            print(f"        -> ChromaDB hazir: {self.collection.count()} dokuman", flush=True)

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        ids: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Add documents with embeddings to the store.

        Args:
            documents: List of document texts
            embeddings: List of embedding vectors
            ids: List of unique document IDs
            metadatas: Optional list of metadata dicts
        """
        self.collection.add(
            documents=documents,
            embeddings=embeddings,
            ids=ids,
            metadatas=metadatas or [{}] * len(documents),
        )

    def count(self) -> int:
        """Return the number of documents in the collection."""
        return self.collection.count()

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 3,
    ) -> Dict[str, Any]:
        """Query the vector store for similar documents.

        Args:
            query_embedding: Query vector
            n_results: Number of results to return

        Returns:
            Query results with documents and distances
        """
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        return results

    def get_document_count(self) -> int:
        """Get the number of documents in the collection.

        Returns:
            Number of documents
        """
        return self.collection.count()

    def is_empty(self) -> bool:
        """Check if the collection is empty.

        Returns:
            True if collection has no documents
        """
        return self.collection.count() == 0

    def delete_collection(self) -> None:
        """Delete the entire collection."""
        self.client.delete_collection(self.collection_name)
        print(f"🗑️ '{self.collection_name}' koleksiyonu silindi.")

    def clear(self) -> None:
        """Clear all documents from the collection."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        print("🗑️ Tüm dökümanlar silindi.")
