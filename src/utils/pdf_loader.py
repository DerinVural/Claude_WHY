"""PDF and document loader for RAG pipeline."""

from typing import List, Dict, Any
from pathlib import Path
import os


class PDFLoader:
    """Load and extract text from PDF files."""

    def __init__(self, data_directory: str = "./data"):
        """Initialize PDF loader.

        Args:
            data_directory: Directory containing PDF files
        """
        self.data_directory = Path(data_directory)
        self.data_directory.mkdir(parents=True, exist_ok=True)

    def load_pdf(self, file_path: str) -> str:
        """Load text from a single PDF file.

        Args:
            file_path: Path to PDF file

        Returns:
            Extracted text content
        """
        try:
            import pypdf
            
            reader = pypdf.PdfReader(file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text.strip()
        except ImportError:
            raise ImportError("pypdf paketi gerekli. Kurulum: pip install pypdf")

    def load_all_pdfs(self) -> List[Dict[str, Any]]:
        """Load all PDF files from the data directory (recursive).

        Returns:
            List of documents with content and metadata
        """
        documents = []
        # Recursive glob ile alt klasörlerdeki PDF'leri de bul
        pdf_files = list(self.data_directory.glob("**/*.pdf"))
        
        if not pdf_files:
            print(f"⚠️ '{self.data_directory}' klasöründe PDF bulunamadı.")
            return documents

        print(f"📂 {len(pdf_files)} PDF dosyası bulundu.")
        
        for pdf_path in pdf_files:
            try:
                content = self.load_pdf(str(pdf_path))
                documents.append({
                    "id": pdf_path.stem,
                    "content": content,
                    "metadata": {
                        "source": str(pdf_path),
                        "filename": pdf_path.name,
                        "type": "pdf",
                    },
                })
                print(f"  ✅ {pdf_path.name} yüklendi.")
            except Exception as e:
                print(f"  ❌ {pdf_path.name} yüklenemedi: {e}")

        return documents

    def load_text_files(self) -> List[Dict[str, Any]]:
        """Load all text files from the data directory.

        Returns:
            List of documents with content and metadata
        """
        documents = []
        extensions = ["*.txt", "*.md"]
        
        for ext in extensions:
            for file_path in self.data_directory.glob(ext):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    documents.append({
                        "id": file_path.stem,
                        "content": content,
                        "metadata": {
                            "source": str(file_path),
                            "filename": file_path.name,
                            "type": file_path.suffix[1:],
                        },
                    })
                    print(f"  ✅ {file_path.name} yüklendi.")
                except Exception as e:
                    print(f"  ❌ {file_path.name} yüklenemedi: {e}")

        return documents

    def load_all_documents(self) -> List[Dict[str, Any]]:
        """Load all supported documents from the data directory.

        Returns:
            List of all documents
        """
        print("\n📚 Dökümanlar yükleniyor...")
        documents = []
        documents.extend(self.load_all_pdfs())
        documents.extend(self.load_text_files())
        print(f"📊 Toplam {len(documents)} döküman yüklendi.\n")
        return documents
