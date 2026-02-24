"""Text chunking utilities for document processing."""

from typing import List, Dict, Any


class TextChunker:
    """Split documents into smaller chunks for embedding."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ):
        """Initialize text chunker.

        Args:
            chunk_size: Maximum characters per chunk
            chunk_overlap: Overlap between consecutive chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks.

        Args:
            text: Input text to split

        Returns:
            List of text chunks
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0

        while start < len(text):
            # Find the end of this chunk
            end = start + self.chunk_size

            # Try to break at a natural boundary (sentence or paragraph)
            if end < len(text):
                # Look for paragraph break
                para_break = text.rfind("\n\n", start, end)
                if para_break > start + self.chunk_size // 2:
                    end = para_break + 2
                else:
                    # Look for sentence break
                    for sep in [". ", ".\n", "? ", "!\n"]:
                        sent_break = text.rfind(sep, start, end)
                        if sent_break > start + self.chunk_size // 2:
                            end = sent_break + len(sep)
                            break

            chunks.append(text[start:end].strip())
            
            # Move start with overlap
            start = end - self.chunk_overlap
            if start >= len(text):
                break

        return [c for c in chunks if c]  # Remove empty chunks

    def chunk_documents(
        self, documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Split documents into chunks with metadata.

        Args:
            documents: List of document dictionaries

        Returns:
            List of chunked documents
        """
        chunked_docs = []

        for doc in documents:
            chunks = self.chunk_text(doc["content"])
            
            for i, chunk in enumerate(chunks):
                chunked_docs.append({
                    "id": f"{doc['id']}_chunk_{i}",
                    "content": chunk,
                    "metadata": {
                        **doc.get("metadata", {}),
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "parent_id": doc["id"],
                    },
                })

        return chunked_docs
