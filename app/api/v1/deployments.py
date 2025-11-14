from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from app.db.database import get_db
from app.db.models import User, Notebook, Build, Deployment
from app.schemas.deployment import (
    DeploymentCreate,
    DeploymentResponse,
    DeploymentListResponse,
    TrafficUpdate
)
from app.utils.deps import get_current_active_user
from app.core.cloud_run import CloudRunService
from app.config import settings

router = APIRouter(prefix="/deployments", tags=["deployments"])


def check_gcp_configured():
    """Check if GCP is properly configured"""
    if not settings.gcp_project_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GCP_PROJECT_ID not configured"
        )
    if not settings.gcp_region:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GCP_REGION not configured"
        )


@router.post("", response_model=DeploymentResponse, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    deployment_data: DeploymentCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Deploy a notebook to Cloud Run"""
    check_gcp_configured()

    notebook = db.query(Notebook).filter(
        Notebook.id == deployment_data.notebook_id,
        Notebook.user_id == current_user.id
    ).first()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    build = None
    if deployment_data.build_id:
        build = db.query(Build).filter(
            Build.id == deployment_data.build_id,
            Build.notebook_id == notebook.id
        ).first()

        if not build:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Build not found"
            )

        if build.status != "success":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Build must be successful. Current status: {build.status}"
            )

        image_uri = build.image_name
    else:
        latest_build = db.query(Build).filter(
            Build.notebook_id == notebook.id,
            Build.status == "success"
        ).order_by(Build.created_at.desc()).first()

        if not latest_build:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No successful build found for this notebook"
            )

        image_uri = latest_build.image_name
        build = latest_build

    service_name = f"notebook-{notebook.id}-{current_user.id}"

    deployment = Deployment(
        notebook_id=notebook.id,
        build_id=build.id if build else None,
        service_name=service_name,
        status="deploying",
        image_uri=image_uri
    )

    db.add(deployment)
    db.commit()
    db.refresh(deployment)

    background_tasks.add_task(
        execute_deployment,
        deployment.id,
        deployment_data.cpu,
        deployment_data.memory,
        deployment_data.min_instances,
        deployment_data.max_instances,
        db
    )

    return deployment


def execute_deployment(
    deployment_id: int,
    cpu: str,
    memory: str,
    min_instances: int,
    max_instances: int,
    db: Session
):
    """Execute deployment in background"""
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    if not deployment:
        return

    try:
        cloud_run_service = CloudRunService()

        service = cloud_run_service.create_or_update_service(
            service_name=deployment.service_name,
            image_uri=deployment.image_uri,
            cpu=cpu,
            memory=memory,
            min_instances=min_instances,
            max_instances=max_instances,
            allow_unauthenticated=True
        )

        cloud_run_service.set_iam_policy(deployment.service_name, allow_public=True)

        deployment.status = "deployed"
        deployment.service_url = service.uri
        deployment.revision_name = service.latest_created_revision if hasattr(service, 'latest_created_revision') else None
        deployment.deployed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        deployment.status = "failed"
        deployment.error_message = str(e)
        db.commit()


@router.get("/{deployment_id}", response_model=DeploymentResponse)
def get_deployment(
    deployment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get deployment details"""
    deployment = db.query(Deployment).join(Notebook).filter(
        Deployment.id == deployment_id,
        Notebook.user_id == current_user.id
    ).first()

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found"
        )

    return deployment


@router.get("", response_model=List[DeploymentListResponse])
def list_deployments(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all deployments for current user"""
    deployments = db.query(Deployment).join(Notebook).filter(
        Notebook.user_id == current_user.id
    ).order_by(Deployment.created_at.desc()).all()

    return deployments


@router.get("/notebook/{notebook_id}", response_model=List[DeploymentListResponse])
def list_notebook_deployments(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List deployments for a specific notebook"""
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    deployments = db.query(Deployment).filter(
        Deployment.notebook_id == notebook_id
    ).order_by(Deployment.created_at.desc()).all()

    return deployments


@router.post("/{deployment_id}/traffic", response_model=DeploymentResponse)
def update_traffic(
    deployment_id: int,
    traffic_data: TrafficUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update traffic distribution for a deployment"""
    check_gcp_configured()

    deployment = db.query(Deployment).join(Notebook).filter(
        Deployment.id == deployment_id,
        Notebook.user_id == current_user.id
    ).first()

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found"
        )

    try:
        cloud_run_service = CloudRunService()
        cloud_run_service.set_traffic(
            service_name=deployment.service_name,
            revision_name=traffic_data.revision_name,
            traffic_percent=traffic_data.traffic_percent
        )

        deployment.revision_name = traffic_data.revision_name
        deployment.traffic_percent = traffic_data.traffic_percent
        db.commit()
        db.refresh(deployment)

        return deployment

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update traffic: {str(e)}"
        )


@router.post("/{deployment_id}/rollback", response_model=DeploymentResponse)
def rollback_deployment(
    deployment_id: int,
    revision_name: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Rollback deployment to a previous revision"""
    check_gcp_configured()

    deployment = db.query(Deployment).join(Notebook).filter(
        Deployment.id == deployment_id,
        Notebook.user_id == current_user.id
    ).first()

    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deployment not found"
        )

    try:
        cloud_run_service = CloudRunService()
        cloud_run_service.rollback_to_revision(
            service_name=deployment.service_name,
            revision_name=revision_name
        )

        deployment.revision_name = revision_name
        deployment.status = "rolled_back"
        db.commit()
        db.refresh(deployment)

        return deployment

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback: {str(e)}"
        )