import logging
from google.cloud import logging as cloud_logging
from google.oauth2 import service_account
from google.auth import default
from app.config import settings
from typing import Optional, Dict, Any
import json
import base64


class LoggingService:
    def __init__(self):
        if settings.gcp_service_account_key:
            decoded = base64.b64decode(settings.gcp_service_account_key).decode('utf-8')
            service_account_info = json.loads(decoded)
            credentials = service_account.Credentials.from_service_account_info(service_account_info)
            self.client = cloud_logging.Client(
                project=settings.gcp_project_id,
                credentials=credentials
            )
        else:
            credentials, _ = default()
            self.client = cloud_logging.Client(
                project=settings.gcp_project_id,
                credentials=credentials
            )

        self.logger_name = "notebook-deploy"
        self.logger = self.client.logger(self.logger_name)

    def _log(self, payload: Dict[str, Any], severity: str = "INFO"):
        try:
            self.logger.log_struct(payload, severity=severity)
        except Exception as e:
            if settings.debug:
                print(f"Logging failed: {e}")

    def log_deployment_start(self, deployment_id: int, notebook_id: int, user_id: int):
        self._log(
            {
                "event": "deployment_started",
                "deployment_id": deployment_id,
                "notebook_id": notebook_id,
                "user_id": user_id
            },
            severity="INFO"
        )

    def log_deployment_success(self, deployment_id: int, service_url: str, duration: float):
        self._log(
            {
                "event": "deployment_success",
                "deployment_id": deployment_id,
                "service_url": service_url,
                "duration_seconds": duration
            },
            severity="INFO"
        )

    def log_deployment_failure(self, deployment_id: int, error: str, stage: str):
        self._log(
            {
                "event": "deployment_failed",
                "deployment_id": deployment_id,
                "error": error,
                "stage": stage
            },
            severity="ERROR"
        )

    def log_build_start(self, build_id: str, deployment_id: int):
        self._log(
            {
                "event": "build_started",
                "build_id": build_id,
                "deployment_id": deployment_id
            },
            severity="INFO"
        )

    def log_build_complete(self, build_id: str, status: str, duration: float):
        self._log(
            {
                "event": "build_completed",
                "build_id": build_id,
                "status": status,
                "duration_seconds": duration
            },
            severity="INFO" if status == "SUCCESS" else "ERROR"
        )

    def log_analysis_start(self, notebook_id: int, user_id: int):
        self._log(
            {
                "event": "analysis_started",
                "notebook_id": notebook_id,
                "user_id": user_id
            },
            severity="INFO"
        )

    def log_analysis_complete(self, notebook_id: int, health_score: int, issues_count: int):
        self._log(
            {
                "event": "analysis_completed",
                "notebook_id": notebook_id,
                "health_score": health_score,
                "issues_count": issues_count
            },
            severity="INFO"
        )

    def log_api_request(self, method: str, path: str, user_id: Optional[int], status_code: int, duration_ms: float):
        self._log(
            {
                "event": "api_request",
                "method": method,
                "path": path,
                "user_id": user_id,
                "status_code": status_code,
                "duration_ms": duration_ms
            },
            severity="INFO"
        )

    def log_error(self, error_type: str, error_message: str, context: Dict[str, Any]):
        self._log(
            {
                "event": "error",
                "error_type": error_type,
                "error_message": error_message,
                "context": context
            },
            severity="ERROR"
        )

    def log_metric(self, metric_name: str, value: float, labels: Dict[str, str] = None):
        self._log(
            {
                "event": "metric",
                "metric_name": metric_name,
                "value": value,
                "labels": labels or {}
            },
            severity="INFO"
        )
