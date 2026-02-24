"""Code file loader for RAG pipeline - Supports multiple programming languages."""

from typing import List, Dict, Any
from pathlib import Path


class CodeLoader:
    """Load and process source code files for RAG."""

    # Supported file extensions and their languages
    SUPPORTED_EXTENSIONS = {
        # Python
        ".py": "python",
        ".pyw": "python",
        ".pyi": "python",
        # JavaScript/TypeScript
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        # Web
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        # HDL (FPGA)
        ".v": "verilog",
        ".sv": "systemverilog",
        ".vhd": "vhdl",
        ".vhdl": "vhdl",
        # C/C++
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cc": "cpp",
        # Other
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".sql": "sql",
        ".sh": "bash",
        ".ps1": "powershell",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".xml": "xml",
        ".toml": "toml",
        ".ini": "ini",
        ".cfg": "config",
        ".tcl": "tcl",  # VIVADO scripts
        ".xdc": "xdc",  # VIVADO constraints
    }

    # Directories to ignore
    IGNORE_DIRS = {
        "__pycache__",
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "env",
        ".env",
        "dist",
        "build",
        ".idea",
        ".vscode",
        "chroma_db",
    }

    def __init__(self, code_directory: str = "./code"):
        """Initialize code loader.

        Args:
            code_directory: Directory containing source code files
        """
        self.code_directory = Path(code_directory)

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored.

        Args:
            path: Path to check

        Returns:
            True if should be ignored
        """
        for part in path.parts:
            if part in self.IGNORE_DIRS:
                return True
        return False

    def load_code_file(self, file_path: Path) -> Dict[str, Any]:
        """Load a single code file.

        Args:
            file_path: Path to code file

        Returns:
            Document dict with content and metadata
        """
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            language = self.SUPPORTED_EXTENSIONS.get(file_path.suffix.lower(), "unknown")
            relative_path = file_path.relative_to(self.code_directory) if self.code_directory in file_path.parents else file_path.name

            return {
                "id": f"code_{file_path.stem}_{hash(str(file_path)) % 10000}",
                "content": self._format_code_content(content, file_path, language),
                "metadata": {
                    "source": str(file_path),
                    "filename": file_path.name,
                    "type": "code",
                    "language": language,
                    "relative_path": str(relative_path),
                    "extension": file_path.suffix,
                },
            }
        except Exception as e:
            print(f"  ❌ {file_path.name} yüklenemedi: {e}")
            return None

    def _format_code_content(self, content: str, file_path: Path, language: str) -> str:
        """Format code content with context for better retrieval.

        Args:
            content: Raw code content
            file_path: Path to the file
            language: Programming language

        Returns:
            Formatted content string
        """
        # Add file context as header
        header = f"# Dosya: {file_path.name}\n# Dil: {language}\n# Yol: {file_path}\n\n"
        return header + content

    def load_all_code(self, recursive: bool = True) -> List[Dict[str, Any]]:
        """Load all code files from the directory.

        Args:
            recursive: Whether to search subdirectories

        Returns:
            List of document dicts
        """
        if not self.code_directory.exists():
            print(f"⚠️ Kod klasörü bulunamadı: {self.code_directory}")
            return []

        documents = []
        pattern = "**/*" if recursive else "*"

        # Collect all supported files
        all_files = []
        for ext in self.SUPPORTED_EXTENSIONS.keys():
            all_files.extend(self.code_directory.glob(f"{pattern}{ext}"))

        if not all_files:
            print(f"⚠️ '{self.code_directory}' klasöründe kod dosyası bulunamadı.")
            return documents

        print(f"📂 {len(all_files)} kod dosyası bulundu.")

        for file_path in sorted(all_files):
            if self._should_ignore(file_path):
                continue

            doc = self.load_code_file(file_path)
            if doc:
                documents.append(doc)
                print(f"  ✅ {file_path.name} ({doc['metadata']['language']})")

        return documents

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about code files.

        Returns:
            Dict with language counts
        """
        stats = {}
        for ext in self.SUPPORTED_EXTENSIONS.keys():
            files = list(self.code_directory.glob(f"**/*{ext}"))
            files = [f for f in files if not self._should_ignore(f)]
            if files:
                lang = self.SUPPORTED_EXTENSIONS[ext]
                stats[lang] = stats.get(lang, 0) + len(files)
        return stats
