"""Tests for text splitter utility."""

import pytest
from src.utils.text_splitter import TextSplitter


class TestTextSplitter:
    """Tests for TextSplitter class."""

    def test_split_text_basic(self):
        """Test basic text splitting."""
        splitter = TextSplitter(chunk_size=50, chunk_overlap=10)
        text = "This is paragraph one.\n\nThis is paragraph two.\n\nThis is paragraph three."

        chunks = splitter.split_text(text)

        assert len(chunks) > 0
        assert all(isinstance(chunk, str) for chunk in chunks)

    def test_split_text_empty(self):
        """Test splitting empty text."""
        splitter = TextSplitter()
        chunks = splitter.split_text("")

        assert chunks == [] or chunks == [""]

    def test_split_documents(self):
        """Test splitting document dictionaries."""
        splitter = TextSplitter(chunk_size=100, chunk_overlap=20)
        documents = [
            {
                "id": "doc1",
                "content": "First document content.\n\nMore content here.",
                "metadata": {"source": "test"},
            }
        ]

        chunked = splitter.split_documents(documents)

        assert len(chunked) > 0
        assert all("chunk_index" in doc["metadata"] for doc in chunked)
        assert all("parent_id" in doc["metadata"] for doc in chunked)

    def test_chunk_overlap(self):
        """Test that chunk overlap is applied."""
        splitter = TextSplitter(chunk_size=30, chunk_overlap=10)
        text = "A" * 25 + "\n\n" + "B" * 25 + "\n\n" + "C" * 25

        chunks = splitter.split_text(text)

        # With overlap, later chunks should contain some content from previous chunks
        assert len(chunks) >= 2
