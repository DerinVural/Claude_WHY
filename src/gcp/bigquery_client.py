"""BigQuery vector store for document embeddings."""

from typing import List, Dict, Any, Optional
from google.cloud import bigquery
import json


class BigQueryVectorStore:
    """Vector store implementation using BigQuery."""

    def __init__(self, project_id: str, dataset_id: str, table_id: str):
        """Initialize BigQuery vector store.

        Args:
            project_id: GCP project ID
            dataset_id: BigQuery dataset ID
            table_id: BigQuery table ID
        """
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.table_id = table_id
        self.client = bigquery.Client(project=project_id)
        self.table_ref = f"{project_id}.{dataset_id}.{table_id}"

    def create_table(self, embedding_dimension: int = 768) -> None:
        """Create the vector store table if it doesn't exist.

        Args:
            embedding_dimension: Dimension of embedding vectors
        """
        schema = [
            bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("content", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("embedding", "FLOAT64", mode="REPEATED"),
            bigquery.SchemaField("metadata", "JSON", mode="NULLABLE"),
            bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        ]

        table = bigquery.Table(self.table_ref, schema=schema)

        try:
            self.client.create_table(table)
        except Exception as e:
            if "Already Exists" not in str(e):
                raise

    def insert_documents(
        self,
        documents: List[Dict[str, Any]],
    ) -> None:
        """Insert documents with embeddings into the vector store.

        Args:
            documents: List of documents with id, content, embedding, metadata
        """
        rows = []
        for doc in documents:
            row = {
                "id": doc["id"],
                "content": doc["content"],
                "embedding": doc["embedding"],
                "metadata": json.dumps(doc.get("metadata", {})),
                "created_at": "AUTO",
            }
            rows.append(row)

        errors = self.client.insert_rows_json(self.table_ref, rows)
        if errors:
            raise RuntimeError(f"Failed to insert rows: {errors}")

    def delete_document(self, document_id: str) -> None:
        """Delete a document from the vector store.

        Args:
            document_id: ID of document to delete
        """
        query = f"""
        DELETE FROM `{self.table_ref}`
        WHERE id = @document_id
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("document_id", "STRING", document_id)
            ]
        )

        self.client.query(query, job_config=job_config).result()

    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID.

        Args:
            document_id: ID of document to retrieve

        Returns:
            Document dict or None if not found
        """
        query = f"""
        SELECT id, content, embedding, metadata, created_at
        FROM `{self.table_ref}`
        WHERE id = @document_id
        """

        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("document_id", "STRING", document_id)
            ]
        )

        results = self.client.query(query, job_config=job_config).result()

        for row in results:
            return {
                "id": row.id,
                "content": row.content,
                "embedding": list(row.embedding),
                "metadata": json.loads(row.metadata) if row.metadata else {},
                "created_at": row.created_at,
            }

        return None
