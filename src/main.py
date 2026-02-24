"""Main RAG pipeline for GCP-RAG-VIVADO."""

from typing import List, Dict, Any, Optional
from src.rag import EmbeddingService, DocumentRetriever, ResponseGenerator
from src.gcp import StorageClient, BigQueryVectorStore
from src.fpga import FPGAAccelerator, VectorOperations
from src.utils import DocumentLoader, TextSplitter


class RAGPipeline:
    """Complete RAG pipeline with GCP integration and FPGA acceleration."""

    def __init__(
        self,
        project_id: str,
        dataset_id: str,
        table_id: str,
        bucket_name: str,
        use_fpga: bool = False,
        location: str = "us-central1",
    ):
        """Initialize RAG pipeline.

        Args:
            project_id: GCP project ID
            dataset_id: BigQuery dataset ID
            table_id: BigQuery table ID
            bucket_name: Cloud Storage bucket name
            use_fpga: Whether to use FPGA acceleration
            location: GCP region
        """
        self.project_id = project_id
        self.use_fpga = use_fpga

        # Initialize services
        self.embedding_service = EmbeddingService(project_id, location)
        self.retriever = DocumentRetriever(
            project_id, dataset_id, table_id, self.embedding_service
        )
        self.generator = ResponseGenerator(project_id, location)
        self.storage = StorageClient(project_id, bucket_name)
        self.vector_store = BigQueryVectorStore(project_id, dataset_id, table_id)

        # Initialize FPGA if requested
        self.vector_ops = None
        if use_fpga:
            self.fpga = FPGAAccelerator()
            self.fpga.initialize()
            self.vector_ops = VectorOperations(use_fpga=True, fpga_accelerator=self.fpga)

        # Utilities
        self.text_splitter = TextSplitter()

    def ingest_documents(
        self, documents: List[Dict[str, Any]], chunk: bool = True
    ) -> int:
        """Ingest documents into the vector store.

        Args:
            documents: List of documents with content and metadata
            chunk: Whether to chunk documents

        Returns:
            Number of documents ingested
        """
        if chunk:
            documents = self.text_splitter.split_documents(documents)

        # Generate embeddings
        for doc in documents:
            doc["embedding"] = self.embedding_service.embed_text(doc["content"])

        # Store in BigQuery
        self.vector_store.insert_documents(documents)

        return len(documents)

    def query(
        self,
        question: str,
        top_k: int = 5,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query the RAG pipeline.

        Args:
            question: User question
            top_k: Number of documents to retrieve
            system_prompt: Optional system prompt

        Returns:
            Response with answer and sources
        """
        # Retrieve relevant documents
        documents = self.retriever.retrieve(question, top_k=top_k)

        # Generate response
        answer = self.generator.generate(
            question, documents, system_prompt=system_prompt
        )

        return {
            "question": question,
            "answer": answer,
            "sources": documents,
        }


def main():
    """Main entry point."""
    import os

    # Configuration from environment
    project_id = os.getenv("GCP_PROJECT_ID", "your-project-id")
    dataset_id = os.getenv("BQ_DATASET_ID", "rag_dataset")
    table_id = os.getenv("BQ_TABLE_ID", "documents")
    bucket_name = os.getenv("GCS_BUCKET", "your-bucket-name")
    use_fpga = os.getenv("USE_FPGA", "false").lower() == "true"

    # Initialize pipeline
    pipeline = RAGPipeline(
        project_id=project_id,
        dataset_id=dataset_id,
        table_id=table_id,
        bucket_name=bucket_name,
        use_fpga=use_fpga,
    )

    # Example query
    result = pipeline.query("What is RAG?")
    print(f"Question: {result['question']}")
    print(f"Answer: {result['answer']}")


if __name__ == "__main__":
    main()
