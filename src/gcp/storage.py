"""Google Cloud Storage client for document management."""

from typing import List, Optional, Iterator
from google.cloud import storage
from pathlib import Path


class StorageClient:
    """Client for Google Cloud Storage operations."""

    def __init__(self, project_id: str, bucket_name: str):
        """Initialize the storage client.

        Args:
            project_id: GCP project ID
            bucket_name: Cloud Storage bucket name
        """
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.client = storage.Client(project=project_id)
        self.bucket = self.client.bucket(bucket_name)

    def upload_file(
        self, local_path: str, destination_blob_name: Optional[str] = None
    ) -> str:
        """Upload a file to Cloud Storage.

        Args:
            local_path: Path to local file
            destination_blob_name: Optional destination name in bucket

        Returns:
            GCS URI of uploaded file
        """
        if destination_blob_name is None:
            destination_blob_name = Path(local_path).name

        blob = self.bucket.blob(destination_blob_name)
        blob.upload_from_filename(local_path)

        return f"gs://{self.bucket_name}/{destination_blob_name}"

    def download_file(self, blob_name: str, local_path: str) -> str:
        """Download a file from Cloud Storage.

        Args:
            blob_name: Name of blob in bucket
            local_path: Local path to save file

        Returns:
            Local path of downloaded file
        """
        blob = self.bucket.blob(blob_name)
        blob.download_to_filename(local_path)
        return local_path

    def list_blobs(self, prefix: Optional[str] = None) -> Iterator[storage.Blob]:
        """List blobs in the bucket.

        Args:
            prefix: Optional prefix to filter blobs

        Yields:
            Storage blob objects
        """
        return self.client.list_blobs(self.bucket_name, prefix=prefix)

    def read_text(self, blob_name: str) -> str:
        """Read text content from a blob.

        Args:
            blob_name: Name of blob in bucket

        Returns:
            Text content of the blob
        """
        blob = self.bucket.blob(blob_name)
        return blob.download_as_text()

    def delete_blob(self, blob_name: str) -> None:
        """Delete a blob from the bucket.

        Args:
            blob_name: Name of blob to delete
        """
        blob = self.bucket.blob(blob_name)
        blob.delete()
