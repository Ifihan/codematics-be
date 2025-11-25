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
            # Get build to access logs
            build = self.get_build(build_id)

            # Cloud Build writes logs to Cloud Logging under cloud_build resource
            filter_str = f'resource.type="build" AND labels.build_id="{build_id}"'

            entries = self.logging_client.list_entries(
                filter_=filter_str,
                order_by=logging_v2.ASCENDING,
                page_size=page_size
            )

            log_entries = []
            for entry in entries:
                # Extract text from structured log
                if hasattr(entry, 'text_payload') and entry.text_payload:
                    message = entry.text_payload
                elif hasattr(entry, 'json_payload') and entry.json_payload:
                    message = str(entry.json_payload)
                else:
                    message = str(entry.payload)

                log_entries.append({
                    "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                    "severity": entry.severity,
                    "message": message
                })

            # If Cloud Logging returns nothing, extract from build steps
            if not log_entries and build.steps:
                for i, step in enumerate(build.steps):
                    log_entries.append({
                        "timestamp": None,
                        "severity": "INFO",
                        "message": f"Step {i+1}: {step.name} {' '.join(step.args)}"
                    })
                # Add build status
                log_entries.append({
                    "timestamp": None,
                    "severity": "INFO" if build.status.name == "SUCCESS" else "ERROR",
                    "message": f"Build Status: {build.status.name}"
                })

            return log_entries
        except Exception as e:
            print(f"Error fetching logs for build {build_id}: {e}")
            # Return build info as fallback
            try:
                build = self.get_build(build_id)
                return [{
                    "timestamp": None,
                    "severity": "INFO",
                    "message": f"Build {build_id} - Status: {build.status.name}. Logs available at: {build.log_url}"
                }]
            except:
                return []

    def fetch_build_log_text(self, build_id: str) -> str:
        """
        Fetch build logs as plain text.

        Returns concatenated log messages.
        """
        entries = self.fetch_build_log_entries(build_id)

        if not entries:
            try:
                build = self.get_build(build_id)
                return f"Build {build_id}\nStatus: {build.status.name}\n\nLogs available at: {build.log_url}\n\nNote: Real-time logs from Cloud Logging are not available. View detailed logs at the URL above."
            except:
                return "No logs available yet. Build may still be starting..."

        log_lines = []
        for entry in entries:
            timestamp = entry.get("timestamp", "")
            message = entry.get("message", "")
            severity = entry.get("severity", "INFO")

            if timestamp:
                log_lines.append(f"[{timestamp}] [{severity}] {message}")
            else:
                log_lines.append(f"[{severity}] {message}")

        return "\n".join(log_lines)
