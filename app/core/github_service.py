import requests
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from app.config import settings


class GitHubService:
    BASE_URL = "https://api.github.com"

    def __init__(self, access_token: Optional[str] = None):
        self.token = access_token
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        url = "https://github.com/login/oauth/access_token"
        data = {
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "code": code,
            "redirect_uri": settings.github_redirect_uri
        }
        headers = {"Accept": "application/json"}

        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        token_data = response.json()

        if "expires_in" in token_data:
            token_data["expires_at"] = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])

        return token_data

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        url = "https://github.com/login/oauth/access_token"
        data = {
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
        headers = {"Accept": "application/json"}

        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        token_data = response.json()

        if "expires_in" in token_data:
            token_data["expires_at"] = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])

        return token_data

    def get_user(self) -> Dict[str, Any]:
        response = requests.get(f"{self.BASE_URL}/user", headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_token_scopes(self) -> list[str]:
        response = requests.get(f"{self.BASE_URL}/user", headers=self.headers)
        scopes_header = response.headers.get("X-OAuth-Scopes", "")
        return [s.strip() for s in scopes_header.split(",") if s.strip()]

    def create_repo(self, name: str, description: str = "", private: bool = False) -> Dict[str, Any]:
        data = {
            "name": name,
            "description": description,
            "private": private,
            "auto_init": True
        }
        response = requests.post(f"{self.BASE_URL}/user/repos", json=data, headers=self.headers)

        if response.status_code == 403:
            scopes = self.get_token_scopes()
            raise Exception(
                f"GitHub token lacks required permissions. "
                f"Current scopes: {scopes}. Required: 'repo' or 'public_repo'. "
                f"Please reconnect GitHub with proper permissions."
            )

        response.raise_for_status()
        return response.json()

    def upload_file(self, owner: str, repo: str, path: str, content: str, message: str) -> Dict[str, Any]:
        import base64
        encoded_content = base64.b64encode(content.encode()).decode()

        data = {
            "message": message,
            "content": encoded_content
        }

        url = f"{self.BASE_URL}/repos/{owner}/{repo}/contents/{path}"
        response = requests.put(url, json=data, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def create_workflow_file(self, owner: str, repo: str, workflow_content: str) -> Dict[str, Any]:
        return self.upload_file(
            owner, repo,
            ".github/workflows/deploy.yml",
            workflow_content,
            "Add CI/CD workflow"
        )

    def get_repo(self, owner: str, repo: str) -> Dict[str, Any]:
        response = requests.get(f"{self.BASE_URL}/repos/{owner}/{repo}", headers=self.headers)
        response.raise_for_status()
        return response.json()

    def create_webhook(self, owner: str, repo: str, webhook_url: str, secret: str) -> Dict[str, Any]:
        data = {
            "config": {
                "url": webhook_url,
                "content_type": "json",
                "secret": secret
            },
            "events": ["push"],
            "active": True
        }
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/hooks"
        response = requests.post(url, json=data, headers=self.headers)
        response.raise_for_status()
        return response.json()
