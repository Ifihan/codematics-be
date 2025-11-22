import time
import json
import base64
from google.cloud import monitoring_v3
from google.oauth2 import service_account
from google.auth import default
from google.protobuf.timestamp_pb2 import Timestamp
from app.config import settings
from typing import Dict, Any

class MonitoringService:
    def __init__(self):
        self.project_id = settings.gcp_project_id
        self.project_name = f"projects/{self.project_id}"

        if settings.gcp_service_account_key:
            decoded = base64.b64decode(settings.gcp_service_account_key).decode('utf-8')
            service_account_info = json.loads(decoded)
            credentials = service_account.Credentials.from_service_account_info(service_account_info)
            self.client = monitoring_v3.MetricServiceClient(credentials=credentials)
        else:
            credentials, _ = default()
            self.client = monitoring_v3.MetricServiceClient(credentials=credentials)

    def create_time_series(self, metric_type: str, value: float, labels: Dict[str, str] = None):
        try:
            series = monitoring_v3.TimeSeries()
            series.metric.type = metric_type
            
            if labels:
                for key, val in labels.items():
                    series.metric.labels[key] = str(val)

            series.resource.type = "global"
            series.resource.labels["project_id"] = self.project_id

            now = time.time()
            seconds = int(now)
            nanos = int((now - seconds) * 10**9)

            interval = monitoring_v3.TimeInterval()
            interval.end_time = Timestamp(seconds=seconds, nanos=nanos)

            point = monitoring_v3.Point()
            point.value.double_value = value
            point.interval = interval
            
            series.points = [point]
            
            self.client.create_time_series(
                request={"name": self.project_name, "time_series": [series]}
            )
        except Exception as e:
            if settings.debug:
                print(f"Failed to write metric {metric_type}: {e}")

    def track_deployment(self, status: str, duration_seconds: float):
        self.create_time_series(
            "custom.googleapis.com/notebook_deployments",
            1.0,
            {"status": status}
        )

        if duration_seconds > 0:
            self.create_time_series(
                "custom.googleapis.com/deployment_duration",
                duration_seconds,
                {"status": status}
            )

    def track_analysis(self, health_score: int):
        self.create_time_series(
            "custom.googleapis.com/notebook_health_score",
            float(health_score),
            {}
        )
