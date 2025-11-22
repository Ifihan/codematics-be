from google.cloud.devtools import cloudbuild_v1
from google.oauth2 import service_account
from google.auth import default
from app.config import settings
import json
import base64


class CloudBuildService:
    def __init__(self):
        if settings.gcp_service_account_key:
            decoded = base64.b64decode(settings.gcp_service_account_key).decode('utf-8')
            service_account_info = json.loads(decoded)
            credentials = service_account.Credentials.from_service_account_info(service_account_info)
            self.client = cloudbuild_v1.CloudBuildClient(credentials=credentials)
        else:
            credentials, _ = default()
            self.client = cloudbuild_v1.CloudBuildClient(credentials=credentials)

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
        build = self.get_build(build_id)
        return build.log_url
