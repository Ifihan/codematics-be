from fastapi import APIRouter, Request, HTTPException, Header
from sqlalchemy.orm import Session
import hmac
import hashlib
from typing import Optional

from app.db.database import get_db
from app.db.models import Deployment, Notebook
from app.config import settings
from app.core.cloud_run import CloudRunService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
cloud_run = CloudRunService()


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not signature or not signature.startswith("sha256="):
        return False

    expected_signature = "sha256=" + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected_signature)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None)
):
    payload = await request.body()

    webhook_secret = settings.github_webhook_secret
    if webhook_secret and not verify_github_signature(payload, x_hub_signature_256, webhook_secret):
        raise HTTPException(401, "Invalid signature")

    if x_github_event != "push":
        return {"message": "Event ignored"}

    data = await request.json()

    repo_full_name = data.get("repository", {}).get("full_name")
    ref = data.get("ref")

    if ref != "refs/heads/main":
        return {"message": "Non-main branch push ignored"}

    db: Session = next(get_db())
    try:
        deployment = db.query(Deployment).filter(
            Deployment.github_repo_url.contains(repo_full_name)
        ).first()

        if not deployment:
            return {"message": "No deployment found for this repo"}

        notebook = db.query(Notebook).filter(
            Notebook.id == deployment.notebook_id
        ).first()

        if not notebook:
            return {"message": "Notebook not found"}

        deployment.status = "building"
        db.commit()

        try:
            result = cloud_run.deploy(
                notebook_id=notebook.id,
                notebook_name=notebook.name,
                main_py_path=notebook.main_py_path,
                requirements_txt_path=notebook.requirements_txt_path,
                dependencies=notebook.dependencies or [],
                user_id=notebook.user_id
            )

            deployment.status = "deployed"
            deployment.service_url = result.get("url")
            deployment.build_id = result.get("build_id")
            db.commit()

            return {
                "message": "Deployment triggered",
                "deployment_id": deployment.id,
                "status": "building"
            }

        except Exception as e:
            deployment.status = "failed"
            deployment.error_message = str(e)
            db.commit()
            raise HTTPException(500, f"Deployment failed: {str(e)}")

    finally:
        db.close()
