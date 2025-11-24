from google.cloud.devtools import cloudbuild_v1
from google.cloud import logging_v2
from google.oauth2 import service_account
from google.auth import default
from app.config import settings
import json
import base64
from typing import List, Dict, Any


class CloudBuildService:
    def __init__(self):
        if settings.gcp_service_account_key:
            decoded = base64.b64decode(settings.gcp_service_account_key).decode('utf-8')
            service_account_info = json.loads(decoded)
            credentials = service_account.Credentials.from_service_account_info(service_account_info)
            self.client = cloudbuild_v1.CloudBuildClient(credentials=credentials)
            self.logging_client = logging_v2.Client(credentials=credentials, project=settings.gcp_project_id)
        else:
            credentials, _ = default()
            self.client = cloudbuild_v1.CloudBuildClient(credentials=credentials)
            self.logging_client = logging_v2.Client(project=settings.gcp_project_id)

        self.project_id = settings.gcp_project_id

    def submit_build(self, source_uri: str, image_name: str, dockerfile_path: str = "Dockerfile") -> str:
        build = cloudbuild_v1.Build()
        build.source = cloudbuild_v1.Source()
        build.source.storage_source = cloudbuild_v1.StorageSource()

        bucket = source_uri.replace("gs://", "").split("/")[0]
        object_path = "/".join(source_uri.replace("gs://", "").split("/")[1:])

        build.source.storage_source.bucket = bucket
        build.source.storage_source.object_ = object_path

        build.steps = [
            cloudbuild_v1.BuildStep(
                name="gcr.io/cloud-builders/docker",
                args=["build", "-t", image_name, "-f", dockerfile_path, "."]
            ),
            cloudbuild_v1.BuildStep(
                name="gcr.io/cloud-builders/docker",
                args=["push", image_name]
            )
        ]

        build.images = [image_name]

        operation = self.client.create_build(
            project_id=self.project_id,
            build=build
        )

        return operation.metadata.build.id

    def get_build(self, build_id: str) -> cloudbuild_v1.Build:
        return self.client.get_build(
            project_id=self.project_id,
            id=build_id
        )

    def get_build_status(self, build_id: str) -> str:
        build = self.get_build(build_id)
        return build.status.name

    def get_build_logs(self, build_id: str) -> str:
        """Get the Cloud Console URL for build logs"""
        build = self.get_build(build_id)
        return build.log_url

    def fetch_build_log_entries(self, build_id: str, page_size: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch actual log entries from Cloud Logging for a build.

        Returns a list of log entries with timestamp and message.
        """
        try:
            # Cloud Build logs are stored in Cloud Logging with this resource name
            filter_str = f'resource.type="build" AND resource.labels.build_id="{build_id}"'

            entries = self.logging_client.list_entries(
                filter_=filter_str,
                order_by=logging_v2.ASCENDING,
                page_size=page_size
            )

            log_entries = []
            for entry in entries:
                log_entries.append({
                    "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                    "severity": entry.severity,
                    "message": entry.payload if isinstance(entry.payload, str) else str(entry.payload)
                })

            return log_entries
        except Exception as e:
            print(f"Error fetching logs for build {build_id}: {e}")
            return []

    def fetch_build_log_text(self, build_id: str) -> str:
        """
        Fetch build logs as plain text.

        Returns concatenated log messages.
        """
        entries = self.fetch_build_log_entries(build_id)

        if not entries:
            return "No logs available yet. Build may still be starting..."

        log_lines = []
        for entry in entries:
            timestamp = entry.get("timestamp", "")
            message = entry.get("message", "")
            severity = entry.get("severity", "INFO")

            log_lines.append(f"[{timestamp}] [{severity}] {message}")

        return "\n".join(log_lines)
