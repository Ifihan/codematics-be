from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.db.database import get_db
from app.db.models import User, Notebook, Deployment, Analysis, ModelVersion
from app.schemas.metrics import (
    SystemMetricsResponse,
    AdminUserActivityResponse,
    UserActivityItem,
    AdminDeploymentOverviewResponse
)
from app.utils.deps import get_current_superuser
from datetime import datetime, timedelta

router = APIRouter(prefix="/admin/metrics", tags=["admin-metrics"])


@router.get("/system", response_model=SystemMetricsResponse)
def get_system_metrics(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """
    Get system-wide metrics (Admin only).

    Returns:
    - Total counts of all resources
    - Active users in last 30 days
    - Total storage usage
    - Average health score across all notebooks
    """

    # Total counts
    total_users = db.query(User).count()
    total_notebooks = db.query(Notebook).count()
    total_deployments = db.query(Deployment).count()
    total_models = db.query(ModelVersion).count()

    # Active users (created notebook/deployment in last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    active_user_ids = set()

    # Users who created notebooks
    notebook_users = db.query(Notebook.user_id).filter(
        Notebook.created_at >= thirty_days_ago
    ).distinct().all()
    active_user_ids.update([u[0] for u in notebook_users])

    # Users who created deployments
    deployment_users = db.query(Deployment.user_id).filter(
        Deployment.created_at >= thirty_days_ago
    ).distinct().all()
    active_user_ids.update([u[0] for u in deployment_users])

    active_users_last_30_days = len(active_user_ids)

    # Total storage (models)
    total_storage_bytes = db.query(
        func.sum(ModelVersion.size_bytes)
    ).scalar() or 0
    total_storage_mb = float(total_storage_bytes) / (1024.0 * 1024.0)

    # Average health score
    avg_health = db.query(
        func.avg(Analysis.health_score)
    ).scalar() or 0.0

    return SystemMetricsResponse(
        total_users=total_users,
        total_notebooks=total_notebooks,
        total_deployments=total_deployments,
        total_models=total_models,
        active_users_last_30_days=active_users_last_30_days,
        total_storage_mb=round(total_storage_mb, 2),
        avg_health_score=round(float(avg_health), 2)
    )


@router.get("/users/activity", response_model=AdminUserActivityResponse)
def get_user_activity_metrics(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """
    Get user activity metrics (Admin only).

    Returns:
    - List of all users with their activity stats
    - Total/active/inactive user counts
    """

    users = db.query(User).all()
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    user_items = []
    active_count = 0
    inactive_count = 0

    for user in users:
        # Count resources per user
        total_notebooks = db.query(Notebook).filter(
            Notebook.user_id == user.id
        ).count()

        total_deployments = db.query(Deployment).filter(
            Deployment.user_id == user.id
        ).count()

        total_models = db.query(ModelVersion).join(Notebook).filter(
            Notebook.user_id == user.id
        ).count()

        # Get last activity
        last_notebook = db.query(Notebook.created_at).filter(
            Notebook.user_id == user.id
        ).order_by(Notebook.created_at.desc()).first()

        last_deployment = db.query(Deployment.created_at).filter(
            Deployment.user_id == user.id
        ).order_by(Deployment.created_at.desc()).first()

        last_activity = None
        if last_notebook and last_deployment:
            last_activity = max(last_notebook[0], last_deployment[0])
        elif last_notebook:
            last_activity = last_notebook[0]
        elif last_deployment:
            last_activity = last_deployment[0]

        # Determine if active (activity in last 30 days)
        is_active = last_activity and last_activity >= thirty_days_ago
        if is_active:
            active_count += 1
        else:
            inactive_count += 1

        user_items.append(UserActivityItem(
            user_id=user.id,
            username=user.username,
            email=user.email,
            total_notebooks=total_notebooks,
            total_deployments=total_deployments,
            total_models=total_models,
            last_activity=last_activity,
            created_at=user.created_at
        ))

    # Sort by last activity (most recent first)
    user_items.sort(key=lambda x: x.last_activity or datetime.min, reverse=True)

    return AdminUserActivityResponse(
        users=user_items,
        total_users=len(users),
        active_users=active_count,
        inactive_users=inactive_count
    )


@router.get("/deployments/overview", response_model=AdminDeploymentOverviewResponse)
def get_deployments_overview(
    current_user: User = Depends(get_current_superuser),
    db: Session = Depends(get_db)
):
    """
    Get deployment overview metrics (Admin only).

    Returns:
    - Total deployment stats
    - Success rates
    - Build time statistics
    - Recent deployment counts
    """

    # Total counts by status
    total_deployments = db.query(Deployment).count()

    successful_deployments = db.query(Deployment).filter(
        Deployment.status == "deployed"
    ).count()

    failed_deployments = db.query(Deployment).filter(
        Deployment.status == "failed"
    ).count()

    active_deployments = db.query(Deployment).filter(
        Deployment.status == "deployed"
    ).count()

    # Success rate
    success_rate = (float(successful_deployments) / float(total_deployments) * 100.0) if total_deployments > 0 else 0.0

    # Build time stats
    build_stats = db.query(
        func.sum(Deployment.build_duration).label("total"),
        func.avg(Deployment.build_duration).label("average")
    ).filter(
        Deployment.build_duration.isnot(None)
    ).first()

    total_build_time_seconds = build_stats.total or 0
    total_build_time_hours = float(total_build_time_seconds) / 3600.0
    avg_build_time_seconds = build_stats.average or 0

    # Recent deployments
    now = datetime.utcnow()
    deployments_last_24h = db.query(Deployment).filter(
        Deployment.created_at >= now - timedelta(hours=24)
    ).count()

    deployments_last_7d = db.query(Deployment).filter(
        Deployment.created_at >= now - timedelta(days=7)
    ).count()

    deployments_last_30d = db.query(Deployment).filter(
        Deployment.created_at >= now - timedelta(days=30)
    ).count()

    return AdminDeploymentOverviewResponse(
        total_deployments=total_deployments,
        successful_deployments=successful_deployments,
        failed_deployments=failed_deployments,
        active_deployments=active_deployments,
        success_rate=round(success_rate, 2),
        total_build_time_hours=round(total_build_time_hours, 2),
        avg_build_time_seconds=round(float(avg_build_time_seconds), 2),
        deployments_last_24h=deployments_last_24h,
        deployments_last_7d=deployments_last_7d,
        deployments_last_30d=deployments_last_30d
    )