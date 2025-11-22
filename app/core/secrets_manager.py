from google.cloud import secretmanager
from google.oauth2 import service_account
from google.auth import default
from app.config import settings
from typing import Optional
import json
import base64


class SecretsManager:
    def __init__(self):
        if settings.gcp_service_account_key:
            decoded = base64.b64decode(settings.gcp_service_account_key).decode('utf-8')
            service_account_info = json.loads(decoded)
            credentials = service_account.Credentials.from_service_account_info(service_account_info)
            self.client = secretmanager.SecretManagerServiceClient(credentials=credentials)
        else:
            credentials, _ = default()
            self.client = secretmanager.SecretManagerServiceClient(credentials=credentials)

        self.project_id = settings.gcp_project_id

    def get_secret(self, secret_id: str, version: str = "latest") -> Optional[str]:
        name = f"projects/{self.project_id}/secrets/{secret_id}/versions/{version}"
        try:
            response = self.client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            print(f"Failed to get secret {secret_id}: {e}")
            return None

    def create_secret(self, secret_id: str, secret_value: str) -> bool:
        parent = f"projects/{self.project_id}"

        try:
            secret = self.client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": secret_id,
                    "secret": {
                        "replication": {"automatic": {}},
                    },
                }
            )

            self.client.add_secret_version(
                request={
                    "parent": secret.name,
                    "payload": {"data": secret_value.encode("UTF-8")},
                }
            )
            return True
        except Exception as e:
            print(f"Failed to create secret {secret_id}: {e}")
            return False

    def update_secret(self, secret_id: str, secret_value: str) -> bool:
        parent = f"projects/{self.project_id}/secrets/{secret_id}"

        try:
            self.client.add_secret_version(
                request={
                    "parent": parent,
                    "payload": {"data": secret_value.encode("UTF-8")},
                }
            )
            return True
        except Exception as e:
            print(f"Failed to update secret {secret_id}: {e}")
            return False

    def delete_secret(self, secret_id: str) -> bool:
        name = f"projects/{self.project_id}/secrets/{secret_id}"

        try:
            self.client.delete_secret(request={"name": name})
            return True
        except Exception as e:
            print(f"Failed to delete secret {secret_id}: {e}")
            return False

    def list_secrets(self) -> list:
        parent = f"projects/{self.project_id}"

        try:
            secrets = self.client.list_secrets(request={"parent": parent})
            return [secret.name.split("/")[-1] for secret in secrets]
        except Exception as e:
            print(f"Failed to list secrets: {e}")
            return []
