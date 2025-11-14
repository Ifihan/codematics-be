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
    build = db.query(Build).filter(Build.id == build_id).first()
    if not build:
        return

    try:
        build.status = "building"
        build.started_at = datetime.utcnow()
        db.commit()

        cloud_build_service = CloudBuildService()

        operation = cloud_build_service.trigger_build(
            source_bucket=build.source_bucket,
            source_object=build.source_object,
            image_name=build.image_name
        )

        build.build_id = operation.id
        build.log_url = operation.log_url if hasattr(operation, 'log_url') else None
        db.commit()

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