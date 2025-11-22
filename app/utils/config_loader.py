from app.config import settings
from app.core.secrets_manager import SecretsManager
from typing import Optional


class ConfigLoader:
    def __init__(self):
        self.secrets_manager = None
        if settings.use_secret_manager:
            try:
                self.secrets_manager = SecretsManager()
            except Exception as e:
                print(f"Failed to initialize Secret Manager: {e}")

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if self.secrets_manager:
            secret = self.secrets_manager.get_secret(key)
            if secret:
                return secret

        return default or getattr(settings, key, None)


config_loader = ConfigLoader()
