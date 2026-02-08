"""Document loader utilities."""

from typing import List, Dict, Any
from pathlib import Path
import json


class DocumentLoader:
    """Load documents from various sources."""

    @staticmethod
    def load_text(file_path: str) -> str:
        """Load text from a file.

        Args:
            file_path: Path to text file

        Returns:
            Text content
        """
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def load_json(file_path: str) -> Dict[str, Any]:
        """Load JSON from a file.

        Args:
            file_path: Path to JSON file

        Returns:
            Parsed JSON content
        """
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def load_documents_from_directory(
        directory: str,
        extensions: List[str] = None,
    ) -> List[Dict[str, Any]]:
        """Load all documents from a directory.

        Args:
            directory: Path to directory
            extensions: List of file extensions to include

        Returns:
            List of document dictionaries
        """
        if extensions is None:
            extensions = [".txt", ".md", ".json"]

        documents = []
        dir_path = Path(directory)

        for ext in extensions:
            for file_path in dir_path.rglob(f"*{ext}"):
                try:
                    content = DocumentLoader.load_text(str(file_path))
                    documents.append({
                        "id": str(file_path),
                        "content": content,
                        "metadata": {
                            "source": str(file_path),
                            "extension": ext,
                            "filename": file_path.name,
                        },
                    })
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")

        return documents
