from fastapi import APIRouter, Request, HTTPException, status, Header, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import json
import hmac
import hashlib
from app.db.database import get_db
from app.db.models import Build, Notebook
from app.config import settings

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/cloud-build")
async def cloud_build_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive Cloud Build status updates"""
    try:
        body = await request.body()
        payload = json.loads(body)

        build_id = payload.get("id")
        status_str = payload.get("status")

        if not build_id or not status_str:
            return {"status": "ignored", "reason": "missing required fields"}

        build = db.query(Build).filter(Build.build_id == build_id).first()

        if not build:
            return {"status": "ignored", "reason": "build not found"}

        status_map = {
            "SUCCESS": "success",
            "FAILURE": "failed",
            "TIMEOUT": "failed",
            "CANCELLED": "failed",
            "INTERNAL_ERROR": "failed"
        }

        new_status = status_map.get(status_str)

        if new_status:
            build.status = new_status
            if new_status == "success":
                build.finished_at = datetime.utcnow()
            elif new_status == "failed":
                build.finished_at = datetime.utcnow()
                build.error_message = f"Build {status_str.lower()}"

            db.commit()

            return {"status": "processed", "build_id": build_id, "new_status": new_status}

        return {"status": "ignored", "reason": "status not terminal"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}"
        )


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Receive GitHub webhook events for auto-deployment"""
    try:
        body = await request.body()

        if settings.github_webhook_secret and x_hub_signature_256:
            expected_signature = "sha256=" + hmac.new(
                settings.github_webhook_secret.encode(),
                body,
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(expected_signature, x_hub_signature_256):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid signature"
                )

        payload = json.loads(body)

        if x_github_event == "push":
            return await handle_github_push(payload, db)
        elif x_github_event == "ping":
            return {"status": "pong"}
        else:
            return {"status": "ignored", "event": x_github_event}

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}"
        )


async def handle_github_push(payload: dict, db: Session):
    """Handle GitHub push events"""
    ref = payload.get("ref")
    repository = payload.get("repository", {})
    repo_name = repository.get("full_name")
    commits = payload.get("commits", [])

    if not ref or not repo_name:
        return {"status": "ignored", "reason": "missing required fields"}

    branch = ref.replace("refs/heads/", "")

    changed_notebooks = []
    for commit in commits:
        added = commit.get("added", [])
        modified = commit.get("modified", [])

        for file_path in added + modified:
            if file_path.endswith(".ipynb"):
                changed_notebooks.append(file_path)

    if not changed_notebooks:
        return {
            "status": "ignored",
            "reason": "no notebook files changed",
            "branch": branch
        }

    return {
        "status": "detected",
        "repository": repo_name,
        "branch": branch,
        "notebooks": list(set(changed_notebooks)),
        "message": "Auto-deployment would be triggered here"
    }


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: Optional[str] = Header(None),
    x_gitlab_event: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """Receive GitLab webhook events"""
    try:
        body = await request.body()

        if settings.gitlab_webhook_secret and x_gitlab_token:
            if not hmac.compare_digest(settings.gitlab_webhook_secret, x_gitlab_token):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid token"
                )

        payload = json.loads(body)

        if x_gitlab_event == "Push Hook":
            return await handle_gitlab_push(payload, db)
        else:
            return {"status": "ignored", "event": x_gitlab_event}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}"
        )


async def handle_gitlab_push(payload: dict, db: Session):
    """Handle GitLab push events"""
    ref = payload.get("ref")
    project = payload.get("project", {})
    project_name = project.get("path_with_namespace")
    commits = payload.get("commits", [])

    if not ref or not project_name:
        return {"status": "ignored", "reason": "missing required fields"}

    branch = ref.replace("refs/heads/", "")

    changed_notebooks = []
    for commit in commits:
        added = commit.get("added", [])
        modified = commit.get("modified", [])

        for file_path in added + modified:
            if file_path.endswith(".ipynb"):
                changed_notebooks.append(file_path)

    if not changed_notebooks:
        return {
            "status": "ignored",
            "reason": "no notebook files changed",
            "branch": branch
        }

    return {
        "status": "detected",
        "project": project_name,
        "branch": branch,
        "notebooks": list(set(changed_notebooks)),
        "message": "Auto-deployment would be triggered here"
    }