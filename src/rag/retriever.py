"""Document retriever for RAG pipeline."""

from typing import List, Dict, Any, Optional
from google.cloud import bigquery
from .embeddings import EmbeddingService


class DocumentRetriever:
    """Retrieves relevant documents from BigQuery vector store."""

    def __init__(
        self,
        project_id: str,
        dataset_id: str,
        table_id: str,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        """Initialize the document retriever.

        Args:
            project_id: GCP project ID
            dataset_id: BigQuery dataset ID
            table_id: BigQuery table ID containing vectors
            embedding_service: Optional embedding service instance
        """
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.table_id = table_id
        self.client = bigquery.Client(project=project_id)
        self.embedding_service = embedding_service or EmbeddingService(project_id)

    def retrieve(
        self, query: str, top_k: int = 5, threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant documents for a query.

        Args:
            query: Search query
            top_k: Number of documents to retrieve
            threshold: Minimum similarity threshold

        Returns:
            List of relevant documents with scores
        """
        query_embedding = self.embedding_service.embed_text(query)

        # BigQuery ML vector search query
        sql = f"""
        SELECT
            content,
            metadata,
            ML.DISTANCE(embedding, @query_embedding, 'COSINE') as distance
        FROM
            `{self.project_id}.{self.dataset_id}.{self.table_id}`
        ORDER BY
            distance ASC
        LIMIT {top_k}
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("query_embedding", "FLOAT64", query_embedding)
            ]
        )

        results = self.client.query(sql, job_config=job_config).result()

        documents = []
        for row in results:
            similarity = 1 - row.distance  # Convert distance to similarity
            if similarity >= threshold:
                documents.append({
                    "content": row.content,
                    "metadata": row.metadata,
                    "score": similarity,
                })

        return documents
