from google.cloud.devtools import cloudbuild_v1
from google.cloud.devtools.cloudbuild_v1.types import Build, BuildStep, BuildOptions
from google.auth import default
from google.oauth2 import service_account
from typing import Optional, Dict, List
from pathlib import Path
from app.config import settings
import yaml


class CloudBuildService:
    """Service for Google Cloud Build operations"""

    def __init__(self):
        """Initialize Cloud Build client"""
        self.project_id = settings.gcp_project_id
        self.region = settings.gcp_region

        if settings.gcp_service_account_key:
            credentials = service_account.Credentials.from_service_account_file(
                settings.gcp_service_account_key
            )
            self.client = cloudbuild_v1.CloudBuildClient(credentials=credentials)
        else:
            credentials, _ = default()
            self.client = cloudbuild_v1.CloudBuildClient(credentials=credentials)

    def create_cloudbuild_yaml(
        self,
        notebook_id: int,
        image_name: str,
        source_dir: str
    ) -> str:
        """Generate cloudbuild.yaml configuration"""
        config = {
            'steps': [
                {
                    'name': 'gcr.io/cloud-builders/gcloud',
                    'args': [
                        'builds', 'submit',
                        '--pack',
                        f'image={image_name}',
                        '--default-buckets-behavior=regional-user-owned-bucket'
                    ]
                }
            ],
            'options': {
                'logging': 'CLOUD_LOGGING_ONLY',
                'machineType': 'E2_HIGHCPU_8'
            },
            'timeout': '1200s'
        }

        cloudbuild_path = Path(source_dir) / 'cloudbuild.yaml'
        with open(cloudbuild_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)

        return str(cloudbuild_path)

    def trigger_build(
        self,
        source_bucket: str,
        source_object: str,
        image_name: str,
        substitutions: Optional[Dict[str, str]] = None
    ) -> Build:
        """Trigger a Cloud Build"""
        build = Build(
            steps=[
                BuildStep(
                    name='gcr.io/cloud-builders/gcloud',
                    args=[
                        'builds', 'submit',
                        '--pack',
                        f'image={image_name}',
                    ]
                )
            ],
            source={
                'storage_source': {
                    'bucket': source_bucket,
                    'object': source_object
                }
            },
            options=BuildOptions(
                logging='CLOUD_LOGGING_ONLY',
                machine_type='E2_HIGHCPU_8'
            ),
            timeout='1200s',
            substitutions=substitutions or {}
        )

        operation = self.client.create_build(project_id=self.project_id, build=build)

        return operation

    def get_build(self, build_id: str) -> Build:
        """Get build status"""
        request = cloudbuild_v1.GetBuildRequest(
            project_id=self.project_id,
            id=build_id
        )
        return self.client.get_build(request=request)

    def list_builds(self, limit: int = 10) -> List[Build]:
        """List recent builds"""
        parent = f"projects/{self.project_id}/locations/{self.region}"
        request = cloudbuild_v1.ListBuildsRequest(
            parent=parent,
            page_size=limit
        )

        builds = []
        for build in self.client.list_builds(request=request):
            builds.append(build)
            if len(builds) >= limit:
                break

        return builds

    def cancel_build(self, build_id: str) -> Build:
        """Cancel a running build"""
        name = f"projects/{self.project_id}/locations/{self.region}/builds/{build_id}"
        return self.client.cancel_build(name=name)