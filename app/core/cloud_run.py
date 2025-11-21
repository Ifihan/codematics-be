from google.cloud import run_v2
from google.oauth2 import service_account
from google.auth import default
from google.iam.v1 import iam_policy_pb2, policy_pb2
from app.config import settings


class CloudRunService:
    def __init__(self):
        if settings.gcp_service_account_key:
            credentials = service_account.Credentials.from_service_account_file(
                settings.gcp_service_account_key
            )
            self.client = run_v2.ServicesClient(credentials=credentials)
        else:
            credentials, _ = default()
            self.client = run_v2.ServicesClient(credentials=credentials)

        self.project_id = settings.gcp_project_id
        self.region = settings.gcp_region

    def deploy_service(
        self,
        service_name: str,
        image_uri: str,
        port: int = 8080,
        memory: str = "512Mi",
        cpu: str = "1",
        min_instances: int = 0,
        max_instances: int = 10,
        env_vars: dict = None
    ) -> run_v2.Service:
        parent = f"projects/{self.project_id}/locations/{self.region}"

        container = run_v2.Container(
            image=image_uri,
            ports=[run_v2.ContainerPort(container_port=port)],
        )

        if env_vars:
            container.env = [
                run_v2.EnvVar(name=k, value=v) for k, v in env_vars.items()
            ]

        template = run_v2.RevisionTemplate(
            containers=[container],
            scaling=run_v2.RevisionScaling(
                min_instance_count=min_instances,
                max_instance_count=max_instances
            )
        )

        template.containers[0].resources = run_v2.ResourceRequirements(
            limits={"memory": memory, "cpu": cpu}
        )

        service = run_v2.Service(
            template=template,
            ingress=run_v2.IngressTraffic.INGRESS_TRAFFIC_ALL,
        )

        request = run_v2.CreateServiceRequest(
            parent=parent,
            service=service,
            service_id=service_name
        )

        operation = self.client.create_service(request=request)
        response = operation.result()

        self._set_iam_policy(service_name)

        return response

    def _set_iam_policy(self, service_name: str):
        service_path = f"projects/{self.project_id}/locations/{self.region}/services/{service_name}"

        try:
            policy_request = iam_policy_pb2.GetIamPolicyRequest(resource=service_path)
            policy = self.client.get_iam_policy(request=policy_request)

            binding = policy_pb2.Binding(
                role="roles/run.invoker",
                members=["allUsers"]
            )

            policy.bindings.append(binding)

            set_policy_request = iam_policy_pb2.SetIamPolicyRequest(
                resource=service_path,
                policy=policy
            )
            self.client.set_iam_policy(request=set_policy_request)
        except Exception as e:
            print(f"Failed to set IAM policy for {service_name}: {e}")

    def update_service(
        self,
        service_name: str,
        image_uri: str,
        port: int = 8080,
        memory: str = "512Mi",
        cpu: str = "1",
        env_vars: dict = None
    ) -> run_v2.Service:
        service_path = f"projects/{self.project_id}/locations/{self.region}/services/{service_name}"

        service = self.client.get_service(name=service_path)

        service.template.containers[0].image = image_uri
        service.template.containers[0].ports = [run_v2.ContainerPort(container_port=port)]
        service.template.containers[0].resources = run_v2.ResourceRequirements(
            limits={"memory": memory, "cpu": cpu}
        )

        if env_vars:
            service.template.containers[0].env = [
                run_v2.EnvVar(name=k, value=v) for k, v in env_vars.items()
            ]

        request = run_v2.UpdateServiceRequest(service=service)
        operation = self.client.update_service(request=request)
        response = operation.result()

        return response

    def get_service(self, service_name: str) -> run_v2.Service:
        service_path = f"projects/{self.project_id}/locations/{self.region}/services/{service_name}"
        return self.client.get_service(name=service_path)

    def delete_service(self, service_name: str):
        service_path = f"projects/{self.project_id}/locations/{self.region}/services/{service_name}"
        operation = self.client.delete_service(name=service_path)
        operation.result()

    def get_service_url(self, service_name: str) -> str:
        service = self.get_service(service_name)
        return service.uri

    def list_services(self):
        parent = f"projects/{self.project_id}/locations/{self.region}"
        return self.client.list_services(parent=parent)
