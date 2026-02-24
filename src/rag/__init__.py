"""RAG pipeline components."""

# Lazy imports to avoid dependency issues
def __getattr__(name):
    if name == "EmbeddingService":
        from .embeddings import EmbeddingService
        return EmbeddingService
    elif name == "DocumentRetriever":
        from .retriever import DocumentRetriever
        return DocumentRetriever
    elif name == "ResponseGenerator":
        from .generator import ResponseGenerator
        return ResponseGenerator
    elif name == "GoogleGenAIEmbeddings":
        from .vertex_embeddings import GoogleGenAIEmbeddings
        return GoogleGenAIEmbeddings
    elif name == "VertexEmbeddings":
        from .vertex_embeddings import VertexEmbeddings
        return VertexEmbeddings
    elif name == "GeminiGenerator":
        from .gemini_generator import GeminiGenerator
        return GeminiGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "EmbeddingService",
    "DocumentRetriever", 
    "ResponseGenerator",
    "GoogleGenAIEmbeddings",
    "VertexEmbeddings",
    "GeminiGenerator",
]
