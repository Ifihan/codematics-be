from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta

from app.db.database import get_db
from app.db.models import User, Notebook, Analysis, Deployment
from app.utils.deps import get_current_user
from app.core.github_service import GitHubService
from app.core.export_service import ExportService
from app.config import settings

router = APIRouter(prefix="/github", tags=["github"])
export_service = ExportService()


def get_github_service_with_refresh(user: User, db: Session) -> GitHubService:
    if not user.github_token:
        raise HTTPException(400, "GitHub not connected")

    if user.github_token_expires_at and user.github_refresh_token:
        if datetime.utcnow() >= user.github_token_expires_at - timedelta(minutes=5):
            github = GitHubService()
            token_data = github.refresh_access_token(user.github_refresh_token)

            user.github_token = token_data.get("access_token")
            user.github_refresh_token = token_data.get("refresh_token", user.github_refresh_token)
            user.github_token_expires_at = token_data.get("expires_at")
            db.commit()

    return GitHubService(user.github_token)


class GitHubAuthResponse(BaseModel):
    github_username: str
    connected: bool


class CreateRepoRequest(BaseModel):
    notebook_id: int
    repo_name: str
    description: str = ""
    private: bool = False


@router.get("/oauth/authorize")
def authorize():
    if not settings.github_client_id:
        raise HTTPException(500, "GitHub OAuth not configured")

    auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_redirect_uri}"
        f"&scope=repo,workflow"
    )
    return {"url": auth_url}


@router.get("/oauth/callback")
def callback(
    code: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    github = GitHubService()

    try:
        token_data = github.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_at = token_data.get("expires_at")

        if not access_token:
            raise HTTPException(400, "Failed to get access token")

        github.token = access_token
        github.headers["Authorization"] = f"Bearer {access_token}"

        user_data = github.get_user()

        current_user.github_token = access_token
        current_user.github_refresh_token = refresh_token
        current_user.github_token_expires_at = expires_at
        current_user.github_username = user_data.get("login")
        db.commit()

        return GitHubAuthResponse(
            github_username=current_user.github_username,
            connected=True
        )

    except Exception as e:
        raise HTTPException(400, f"GitHub OAuth failed: {str(e)}")


@router.get("/status", response_model=GitHubAuthResponse)
def get_status(current_user: User = Depends(get_current_user)):
    return GitHubAuthResponse(
        github_username=current_user.github_username or "",
        connected=bool(current_user.github_token)
    )


@router.post("/disconnect")
def disconnect(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    current_user.github_token = None
    current_user.github_username = None
    db.commit()
    return {"message": "GitHub disconnected"}


@router.post("/create-repo")
def create_repo(
    request: CreateRepoRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    get_github_service_with_refresh(current_user, db)

    notebook = db.query(Notebook).filter(
        Notebook.id == request.notebook_id,
        Notebook.user_id == current_user.id
    ).first()
    if not notebook:
        raise HTTPException(404, "Notebook not found")

    analysis = db.query(Analysis).filter_by(notebook_id=request.notebook_id).first()

    try:
        result = export_service.push_to_github(notebook, current_user, analysis, db)

        deployment = db.query(Deployment).filter(
            Deployment.notebook_id == request.notebook_id
        ).order_by(Deployment.created_at.desc()).first()

        if deployment:
            deployment.github_repo_url = result["repo_url"]
            db.commit()

        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to create repo: {str(e)}")


def generate_github_actions_workflow(repo_name: str) -> str:
    return f"""name: Deploy to Cloud Run

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Cloud SDK
      uses: google-github-actions/setup-gcloud@v1
      with:
        service_account_key: ${{{{ secrets.GCP_SA_KEY }}}}
        project_id: ${{{{ secrets.GCP_PROJECT_ID }}}}

    - name: Build and Push
      run: |
        gcloud builds submit --tag gcr.io/${{{{ secrets.GCP_PROJECT_ID }}}}/{repo_name}

    - name: Deploy to Cloud Run
      run: |
        gcloud run deploy {repo_name} \\
          --image gcr.io/${{{{ secrets.GCP_PROJECT_ID }}}}/{repo_name} \\
          --platform managed \\
          --region us-central1 \\
          --allow-unauthenticated
"""
