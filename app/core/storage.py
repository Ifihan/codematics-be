from google.cloud import storage
from google.auth import default
from google.oauth2 import service_account
from pathlib import Path
from typing import Optional
import tarfile
import tempfile
from app.config import settings


class StorageService:
    """Service for Google Cloud Storage operations"""

    def __init__(self):
        """Initialize Storage client"""
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

    def create_source_tarball(self, source_dir: str) -> str:
        """Create a tarball of source directory"""
        source_path = Path(source_dir)

        with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as tmp:
            tarball_path = tmp.name

        with tarfile.open(tarball_path, 'w:gz') as tar:
            for file_path in source_path.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(source_path)
                    tar.add(file_path, arcname=arcname)

        return tarball_path

    def upload_source(
        self,
        source_dir: str,
        destination_blob_name: str
    ) -> str:
        """Upload source code to GCS"""
        bucket = self.client.bucket(self.bucket_name)

        tarball_path = self.create_source_tarball(source_dir)

        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(tarball_path)

        Path(tarball_path).unlink()

        return f"gs://{self.bucket_name}/{destination_blob_name}"

    def download_file(
        self,
        source_blob_name: str,
        destination_file_path: str
    ) -> str:
        """Download file from GCS"""
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(source_blob_name)

        blob.download_to_filename(destination_file_path)

        return destination_file_path

    def delete_blob(self, blob_name: str):
        """Delete a blob from GCS"""
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(blob_name)
        blob.delete()

    def list_blobs(self, prefix: Optional[str] = None) -> list:
        """List blobs in bucket"""
        bucket = self.client.bucket(self.bucket_name)
        blobs = bucket.list_blobs(prefix=prefix)
        return list(blobs)