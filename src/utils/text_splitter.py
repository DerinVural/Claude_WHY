"""Text splitting utilities for document chunking."""

from typing import List, Dict, Any
import re


class TextSplitter:
    """Split text into chunks for embedding."""

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separator: str = "\n\n",
    ):
        """Initialize text splitter.

        Args:
            chunk_size: Maximum size of each chunk
            chunk_overlap: Overlap between consecutive chunks
            separator: Primary separator for splitting
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separator = separator

    def split_text(self, text: str) -> List[str]:
        """Split text into chunks.

        Args:
            text: Input text to split

        Returns:
            List of text chunks
        """
        # First, split by the primary separator
        splits = text.split(self.separator)

        chunks = []
        current_chunk = ""

        for split in splits:
            if len(current_chunk) + len(split) <= self.chunk_size:
                current_chunk += split + self.separator
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())

                # Handle overlap
                if self.chunk_overlap > 0 and current_chunk:
                    overlap_text = current_chunk[-self.chunk_overlap:]
                    current_chunk = overlap_text + split + self.separator
                else:
                    current_chunk = split + self.separator

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks

    def split_documents(
        self, documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Split documents into chunks.

        Args:
            documents: List of document dictionaries

        Returns:
            List of chunked documents
        """
        chunked_docs = []

        for doc in documents:
            chunks = self.split_text(doc["content"])

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
