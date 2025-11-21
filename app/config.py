from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional
import base64
import json
import tempfile
import os


class Settings(BaseSettings):
    app_name: str = "Notebook to Cloud"
    app_version: str = "0.1.0"
    debug: bool = False

    host: str = "0.0.0.0"
    port: int = 8080

    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://user:password@localhost:5432/notebook_to_cloud",
    )

    gcp_project_id: Optional[str] = None
    gcp_service_account_key: Optional[str] = None
    gcp_service_account_key_base64: Optional[str] = None
    gcp_bucket_name: Optional[str] = None

    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    @field_validator("gcp_service_account_key", mode="before")
    @classmethod
    def decode_service_account_key(cls, v, info):
        """Decode base64 service account key if base64 version is provided"""
        base64_key = info.data.get("gcp_service_account_key_base64")

        if base64_key and not v:
            try:
                decoded = base64.b64decode(base64_key)
                key_data = json.loads(decoded)

                temp_file = tempfile.NamedTemporaryFile(
                    mode="w", delete=False, suffix=".json"
                )
                json.dump(key_data, temp_file)
                temp_file.close()

                return temp_file.name
            except Exception as e:
                print(f"Failed to decode base64 service account key: {e}")
                return v

        return v


settings = Settings()
