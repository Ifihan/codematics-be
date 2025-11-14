from google.cloud.run_v2 import ServicesClient
from google.cloud.run_v2.types import Service, Container, TrafficTarget, Revision
from google.auth import default
from google.oauth2 import service_account
from typing import Optional, Dict, List
from app.config import settings


class CloudRunService:
    """Service for Google Cloud Run operations"""

    def __init__(self):
        """Initialize Cloud Run client"""
        self.project_id = settings.gcp_project_id
        self.region = settings.gcp_region

        if settings.gcp_service_account_key:
            credentials = service_account.Credentials.from_service_account_file(
                settings.gcp_service_account_key
            )
            self.client = ServicesClient(credentials=credentials)
        else:
            credentials, _ = default()
            self.client = ServicesClient(credentials=credentials)

    def create_or_update_service(
        self,
        service_name: str,
        image_uri: str,
        env_vars: Optional[Dict[str, str]] = None,
        cpu: str = "1",
        memory: str = "512Mi",
        max_instances: int = 10,
        min_instances: int = 0,
        port: int = 8080,
        allow_unauthenticated: bool = True
    ) -> Service:
        """Create or update a Cloud Run service"""
        parent = f"projects/{self.project_id}/locations/{self.region}"
        service_path = f"{parent}/services/{service_name}"

        container = Container(
            image=image_uri,
            ports=[{"container_port": port}],
            env=[{"name": k, "value": v} for k, v in (env_vars or {}).items()],
            resources={
                "limits": {
                    "cpu": cpu,
                    "memory": memory
                }
            }
        )

        try:
            existing_service = self.client.get_service(name=service_path)

            service = Service(
                name=service_path,
                template={
                    "containers": [container],
                    "scaling": {
                        "min_instance_count": min_instances,
                        "max_instance_count": max_instances
                    }
                },
                traffic=[
                    TrafficTarget(
                        type_="TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST",
                        percent=100
                    )
                ]
            )

            operation = self.client.update_service(service=service)
            return operation.result()
        except Exception:
            service = Service(
                template={
                    "containers": [container],
                    "scaling": {
                        "min_instance_count": min_instances,
                        "max_instance_count": max_instances
                    }
                },
                traffic=[
                    TrafficTarget(
                        type_="TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST",
                        percent=100
                    )
                ]
            )

            operation = self.client.create_service(parent=parent, service=service, service_id=service_name)
            return operation.result()

    def get_service(self, service_name: str) -> Service:
        """Get Cloud Run service details"""
        service_path = f"projects/{self.project_id}/locations/{self.region}/services/{service_name}"
        return self.client.get_service(name=service_path)

    def list_services(self) -> List[Service]:
        """List all Cloud Run services"""
        parent = f"projects/{self.project_id}/locations/{self.region}"
        services = []
        for service in self.client.list_services(parent=parent):
            services.append(service)
        return services

    def delete_service(self, service_name: str):
        """Delete a Cloud Run service"""
        service_path = f"projects/{self.project_id}/locations/{self.region}/services/{service_name}"
        operation = self.client.delete_service(name=service_path)
        return operation.result()

    def get_service_url(self, service_name: str) -> Optional[str]:
        """Get the URL of a deployed service"""
        try:
            service = self.get_service(service_name)
            return service.uri
        except Exception:
            return None

    def set_traffic(
        self,
        service_name: str,
        revision_traffic: Dict[str, int]
    ) -> Service:
        """Set traffic distribution between revisions"""
        service = self.get_service(service_name)

        traffic_targets = [
            TrafficTarget(revision=rev, percent=percent)
            for rev, percent in revision_traffic.items()
        ]

        service.traffic = traffic_targets
        operation = self.client.update_service(service=service)
        return operation.result()

    def rollback_to_revision(self, service_name: str, revision_name: str) -> Service:
        """Rollback to a specific revision"""
        return self.set_traffic(service_name, {revision_name: 100})

    def set_iam_policy(self, service_name: str, allow_public: bool = True):
        """Set IAM policy to allow public access"""
        from google.iam.v1 import iam_policy_pb2, policy_pb2

        service_path = f"projects/{self.project_id}/locations/{self.region}/services/{service_name}"

        if allow_public:
            policy = policy_pb2.Policy(
                bindings=[
                    policy_pb2.Binding(
                        role="roles/run.invoker",
                        members=["allUsers"]
                    )
                ]
            )

            request = iam_policy_pb2.SetIamPolicyRequest(
                resource=service_path,
                policy=policy
            )

            return self.client.set_iam_policy(request=request)
