from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.database import get_db
from app.db.models import User, Notebook, Deployment, Analysis, ModelVersion
from app.schemas.profile import (
    ProfileUpdate,
    ProfileResponse,
    PublicProfileResponse,
    PublicNotebookItem,
    PublicDeploymentItem,
    PublicProfileStats
)
from app.utils.deps import get_current_active_user
from typing import List

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/me", response_model=ProfileResponse)
def get_my_profile(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's profile.

    Returns:
    - Full profile information including private fields (email)
    - Portfolio visibility status
    """
    return ProfileResponse.from_orm(current_user)


@router.put("/me", response_model=ProfileResponse)
def update_my_profile(
    profile_update: ProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's profile.

    Allows updating:
    - bio: Professional bio/about section
    - primary_stack: Tech stack (e.g., "PyTorch, TensorFlow")
    - research_interests: Research focus areas
    - is_profile_public: Toggle public portfolio visibility
    """
    # Update only provided fields
    update_data = profile_update.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)

    return ProfileResponse.from_orm(current_user)


@router.get("/{username}/public", response_model=PublicProfileResponse)
def get_public_profile(
    username: str,
    db: Session = Depends(get_db)
):
    """
    Get public profile portfolio for a user.

    Returns:
    - Professional dossier (bio, primary stack, research interests)
    - Portfolio statistics
    - List of notebooks with health scores
    - List of active deployments with URLs

    Requirements:
    - User must have is_profile_public=True
    - Only shows successfully deployed models and healthy notebooks
    """
    # Find user by username
    user = db.query(User).filter(User.username == username).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_profile_public:
        raise HTTPException(
            status_code=403,
            detail="This profile is not public. User has not enabled portfolio visibility."
        )

    # Get user's notebooks with health scores
    notebooks = db.query(Notebook).filter(
        Notebook.user_id == user.id
    ).order_by(Notebook.created_at.desc()).all()

    notebook_items = []
    for notebook in notebooks:
        # Get health score
        analysis = db.query(Analysis).filter(
            Analysis.notebook_id == notebook.id
        ).first()

        health_score = analysis.health_score if analysis else None

        # Check if has deployment
        deployment = db.query(Deployment).filter(
            Deployment.notebook_id == notebook.id,
            Deployment.status == "deployed"
        ).first()

        notebook_items.append(PublicNotebookItem(
            id=notebook.id,
            name=notebook.name,
            health_score=health_score,
            has_deployment=deployment is not None,
            deployment_url=deployment.service_url if deployment else None,
            created_at=notebook.created_at
        ))

    # Get user's active deployments
    deployments = db.query(Deployment).filter(
        Deployment.user_id == user.id,
        Deployment.status == "deployed"
    ).order_by(Deployment.deployed_at.desc()).all()

    deployment_items = []
    for deployment in deployments:
        notebook = db.query(Notebook).filter(
            Notebook.id == deployment.notebook_id
        ).first()

        deployment_items.append(PublicDeploymentItem(
            id=deployment.id,
            name=deployment.name,
            notebook_name=notebook.name if notebook else "Unknown",
            service_url=deployment.service_url,
            status=deployment.status,
            deployed_at=deployment.deployed_at
        ))

    # Calculate statistics
    total_notebooks = len(notebooks)
    total_deployments = db.query(Deployment).filter(
        Deployment.user_id == user.id
    ).count()

    active_deployments = len(deployment_items)

    total_models = db.query(ModelVersion).join(Notebook).filter(
        Notebook.user_id == user.id
    ).count()

    # Average health score
    avg_health_query = db.query(
        func.avg(Analysis.health_score)
    ).join(Notebook).filter(
        Notebook.user_id == user.id
    ).scalar()

    avg_health_score = round(float(avg_health_query), 2) if avg_health_query else 0.0

    stats = PublicProfileStats(
        total_notebooks=total_notebooks,
        total_deployments=total_deployments,
        active_deployments=active_deployments,
        total_models=total_models,
        avg_health_score=avg_health_score
    )

    return PublicProfileResponse(
        username=user.username,
        bio=user.bio,
        primary_stack=user.primary_stack,
        research_interests=user.research_interests,
        github_username=user.github_username,
        created_at=user.created_at,
        stats=stats,
        notebooks=notebook_items,
        deployments=deployment_items
    )