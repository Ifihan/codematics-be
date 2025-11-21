from google.cloud import storage
from google.auth import default
from google.oauth2 import service_account
from pathlib import Path
from typing import Optional
from app.config import settings


class StorageService:
    def __init__(self):
        if settings.gcp_service_account_key:
            credentials = service_account.Credentials.from_service_account_file(
                settings.gcp_service_account_key
            )
            self.client = storage.Client(
                project=settings.gcp_project_id,
                credentials=credentials
            )
        else:
            credentials, project = default()
            self.client = storage.Client(
                project=settings.gcp_project_id or project,
                credentials=credentials
            )

        self.bucket_name = settings.gcp_bucket_name

    def upload_file(self, local_path: str, blob_name: str) -> str:
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_path)
        return f"gs://{self.bucket_name}/{blob_name}"

    def upload_from_string(self, content: str, blob_name: str) -> str:
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(content)
        return f"gs://{self.bucket_name}/{blob_name}"

    def download_file(self, blob_name: str, destination_path: str) -> str:
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(destination_path)
        return destination_path

    def download_as_string(self, blob_name: str) -> str:
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(blob_name)
        return blob.download_as_text()

    def delete_blob(self, blob_name: str):
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()

    def list_blobs(self, prefix: Optional[str] = None) -> list:
        bucket = self.client.bucket(self.bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)
        return list(blobs)

    def upload_from_bytes(self, content: bytes, blob_name: str, content_type: str = None) -> str:
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(content, content_type=content_type)
        return f"gs://{self.bucket_name}/{blob_name}"

    def parse_gcs_uri(self, uri: str) -> str:
        if uri.startswith(f"gs://{self.bucket_name}/"):
            return uri.replace(f"gs://{self.bucket_name}/", "")
        return uri

    def blob_exists(self, blob_name: str) -> bool:
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(blob_name)
        return blob.exists()