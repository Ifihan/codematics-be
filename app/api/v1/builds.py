from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from pathlib import Path
from app.db.database import get_db
from app.db.models import User, Notebook, Build
from app.schemas.build import BuildResponse, BuildListResponse
from app.utils.deps import get_current_active_user
from app.core.cloud_build import CloudBuildService
from app.core.storage import StorageService
from app.config import settings

router = APIRouter(prefix="/builds", tags=["builds"])


def check_gcp_configured():
    """Check if GCP is properly configured"""
    if not settings.gcp_project_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GCP_PROJECT_ID not configured"
        )
    if not settings.gcp_bucket_name:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GCP_BUCKET_NAME not configured"
        )
    if not settings.gcp_artifact_registry:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GCP_ARTIFACT_REGISTRY not configured"
        )


@router.post("/trigger/{notebook_id}", response_model=BuildResponse, status_code=status.HTTP_201_CREATED)
async def trigger_build(
    notebook_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Trigger Cloud Build for a notebook"""
    check_gcp_configured()

    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    if notebook.status != "parsed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Notebook must be parsed first. Current status: {notebook.status}"
        )

    image_name = f"{settings.gcp_artifact_registry}/{notebook.name}:latest"
    source_dir = Path(notebook.file_path).parent

    storage_service = StorageService()
    source_object = f"builds/notebook-{notebook_id}/source-{datetime.utcnow().timestamp()}.tar.gz"

    try:
        storage_service.upload_source(str(source_dir), source_object)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload source: {str(e)}"
        )

    build = Build(
        notebook_id=notebook.id,
        build_id=f"build-{notebook.id}-{int(datetime.utcnow().timestamp())}",
        status="queued",
        image_name=image_name,
        source_bucket=settings.gcp_bucket_name,
        source_object=source_object
    )

    db.add(build)
    db.commit()
    db.refresh(build)

    background_tasks.add_task(execute_build, build.id, db)

    return build


def execute_build(build_id: int, db: Session):
    """Execute build in background"""
    import time

    build = db.query(Build).filter(Build.id == build_id).first()
    if not build:
        return

    try:
        build.status = "building"
        build.started_at = datetime.utcnow()
        db.commit()

        cloud_build_service = CloudBuildService()

        build_result = cloud_build_service.trigger_build(
            source_bucket=build.source_bucket,
            source_object=build.source_object,
            image_name=build.image_name
        )

        build.build_id = build_result.metadata.build.id
        build.log_url = f"https://console.cloud.google.com/cloud-build/builds/{build_result.metadata.build.id}?project={settings.gcp_project_id}"
        db.commit()

        while True:
            build_status = cloud_build_service.get_build(build_result.metadata.build.id)
            status_value = build_status.status

            if status_value == 1:
                time.sleep(5)
            elif status_value == 2:
                time.sleep(5)
            elif status_value == 3:
                build.status = "success"
                build.finished_at = datetime.utcnow()
                db.commit()
                break
            elif status_value == 4:
                build.status = "failed"
                build.error_message = "Build failed"
                build.finished_at = datetime.utcnow()
                db.commit()
                break
            elif status_value == 5:
                build.status = "failed"
                build.error_message = "Build internal error"
                build.finished_at = datetime.utcnow()
                db.commit()
                break
            elif status_value == 6:
                build.status = "failed"
                build.error_message = "Build timeout"
                build.finished_at = datetime.utcnow()
                db.commit()
                break
            elif status_value == 7:
                build.status = "failed"
                build.error_message = "Build cancelled"
                build.finished_at = datetime.utcnow()
                db.commit()
                break
            else:
                time.sleep(5)

    except Exception as e:
        build.status = "failed"
        build.error_message = str(e)
        build.finished_at = datetime.utcnow()
        db.commit()


@router.get("/{build_id}", response_model=BuildResponse)
def get_build(
    build_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get build details"""
    build = db.query(Build).join(Notebook).filter(
        Build.id == build_id,
        Notebook.user_id == current_user.id
    ).first()

    if not build:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Build not found"
        )

    return build


@router.get("", response_model=List[BuildListResponse])
def list_builds(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all builds for current user"""
    builds = db.query(Build).join(Notebook).filter(
        Notebook.user_id == current_user.id
    ).order_by(Build.created_at.desc()).all()

    return builds


@router.get("/notebook/{notebook_id}", response_model=List[BuildListResponse])
def list_notebook_builds(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List builds for a specific notebook"""
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    builds = db.query(Build).filter(
        Build.notebook_id == notebook_id
    ).order_by(Build.created_at.desc()).all()

    return builds


@router.post("/{build_id}/refresh", response_model=BuildResponse)
def refresh_build_status(
    build_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Manually refresh build status from Cloud Build"""
    check_gcp_configured()

    build = db.query(Build).join(Notebook).filter(
        Build.id == build_id,
        Notebook.user_id == current_user.id
    ).first()

    if not build:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Build not found"
        )

    try:
        cloud_build_service = CloudBuildService()
        build_status = cloud_build_service.get_build(build.build_id)
        status_value = build_status.status

        if status_value == 3:
            build.status = "success"
            build.finished_at = datetime.utcnow()
        elif status_value in [4, 5, 6, 7]:
            build.status = "failed"
            error_messages = {4: "Build failed", 5: "Internal error", 6: "Timeout", 7: "Cancelled"}
            build.error_message = error_messages.get(status_value, "Unknown error")
            build.finished_at = datetime.utcnow()
        elif status_value in [1, 2]:
            build.status = "building"

        db.commit()
        db.refresh(build)

        return build

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh status: {str(e)}"
        )


@router.get("/{build_id}/logs")
def get_build_logs(
    build_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get build logs from Cloud Build"""
    check_gcp_configured()

    build = db.query(Build).join(Notebook).filter(
        Build.id == build_id,
        Notebook.user_id == current_user.id
    ).first()

    if not build:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Build not found"
        )

    try:
        cloud_build_service = CloudBuildService()
        build_details = cloud_build_service.get_build(build.build_id)

        return {
            "build_id": build.build_id,
            "status": build.status,
            "error_message": build.error_message,
            "log_url": build.log_url,
            "gcp_build_status": str(build_details.status) if build_details else None,
            "steps": [
                {
                    "name": step.name,
                    "status": str(step.status) if hasattr(step, 'status') else None
                }
                for step in (build_details.steps if build_details else [])
            ]
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch logs: {str(e)}"
        )