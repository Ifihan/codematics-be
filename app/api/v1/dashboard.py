from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from app.db.database import get_db
from app.db.models import User, Notebook, Deployment, Analysis, ModelVersion
from app.schemas.dashboard import (
    DashboardResponse,
    UserSummary,
    Summary,
    RecentActivity,
    HealthOverview,
    DeploymentStats
)
from app.utils.deps import get_current_active_user
from typing import List
from datetime import datetime, timedelta

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive dashboard data for the current user.

    Returns:
    - User summary
    - Resource counts (notebooks, deployments, models, analyses)
    - Recent activity (last 10 items)
    - Health overview (average health score, issues count)
    - Deployment statistics (success rate, build times)
    """

    # User summary
    user_summary = UserSummary(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        created_at=current_user.created_at
    )

    # Count summaries
    total_notebooks = db.query(Notebook).filter(
        Notebook.user_id == current_user.id
    ).count()

    total_deployments = db.query(Deployment).filter(
        Deployment.user_id == current_user.id
    ).count()

    active_deployments = db.query(Deployment).filter(
        Deployment.user_id == current_user.id,
        Deployment.status == "deployed"
    ).count()

    failed_deployments = db.query(Deployment).filter(
        Deployment.user_id == current_user.id,
        Deployment.status == "failed"
    ).count()

    total_models = db.query(ModelVersion).join(Notebook).filter(
        Notebook.user_id == current_user.id
    ).count()

    total_analyses = db.query(Analysis).join(Notebook).filter(
        Notebook.user_id == current_user.id
    ).count()

    summary = Summary(
        total_notebooks=total_notebooks,
        total_deployments=total_deployments,
        active_deployments=active_deployments,
        failed_deployments=failed_deployments,
        total_models=total_models,
        total_analyses=total_analyses
    )

    # Recent activity (last 10 items across notebooks, deployments, and models)
    recent_activity: List[RecentActivity] = []

    # Recent notebooks
    recent_notebooks = db.query(Notebook).filter(
        Notebook.user_id == current_user.id
    ).order_by(Notebook.created_at.desc()).limit(3).all()

    for notebook in recent_notebooks:
        recent_activity.append(RecentActivity(
            type="notebook",
            action="created",
            resource_id=notebook.id,
            resource_name=notebook.name,
            status=notebook.status,
            timestamp=notebook.created_at
        ))

    # Recent deployments
    recent_deployments = db.query(Deployment).filter(
        Deployment.user_id == current_user.id
    ).order_by(Deployment.created_at.desc()).limit(4).all()

    for deployment in recent_deployments:
        action = "deployed" if deployment.status == "deployed" else "failed" if deployment.status == "failed" else "created"
        recent_activity.append(RecentActivity(
            type="deployment",
            action=action,
            resource_id=deployment.id,
            resource_name=deployment.name,
            status=deployment.status,
            timestamp=deployment.deployed_at or deployment.created_at
        ))

    # Recent models
    recent_models = db.query(ModelVersion).join(Notebook).filter(
        Notebook.user_id == current_user.id
    ).order_by(ModelVersion.uploaded_at.desc()).limit(3).all()

    for model in recent_models:
        notebook = db.query(Notebook).filter(Notebook.id == model.notebook_id).first()
        recent_activity.append(RecentActivity(
            type="model",
            action="uploaded",
            resource_id=model.id,
            resource_name=f"{notebook.name} v{model.version}" if notebook else f"Model v{model.version}",
            status="active" if model.is_active else "inactive",
            timestamp=model.uploaded_at
        ))

    # Sort by timestamp and limit to 10
    recent_activity.sort(key=lambda x: x.timestamp, reverse=True)
    recent_activity = recent_activity[:10]

    # Health overview
    health_stats = db.query(
        func.avg(Analysis.health_score).label("avg_health"),
        func.count(Analysis.id).label("total_analyzed"),
        func.sum(case((Analysis.health_score < 70, 1), else_=0)).label("with_issues")
    ).join(Notebook).filter(
        Notebook.user_id == current_user.id
    ).first()

    health_overview = HealthOverview(
        average_health_score=float(health_stats.avg_health) if health_stats.avg_health else 0.0,
        notebooks_analyzed=health_stats.total_analyzed or 0,
        notebooks_with_issues=health_stats.with_issues or 0
    )

    # Deployment statistics
    deployment_stats_query = db.query(
        func.count(Deployment.id).label("total"),
        func.sum(case((Deployment.status == "deployed", 1), else_=0)).label("successful"),
        func.avg(Deployment.build_duration).label("avg_build_time"),
        func.sum(Deployment.build_duration).label("total_build_time"),
        func.min(Deployment.build_duration).label("fastest"),
        func.max(Deployment.build_duration).label("slowest")
    ).filter(
        Deployment.user_id == current_user.id,
        Deployment.build_duration.isnot(None)
    ).first()

    total_deps = deployment_stats_query.total or 0
    successful_deps = deployment_stats_query.successful or 0
    success_rate = (successful_deps / total_deps * 100) if total_deps > 0 else 0.0

    deployment_stats = DeploymentStats(
        success_rate=round(success_rate, 2),
        average_build_time=float(deployment_stats_query.avg_build_time) if deployment_stats_query.avg_build_time else 0.0,
        total_build_time=float(deployment_stats_query.total_build_time) if deployment_stats_query.total_build_time else 0.0,
        fastest_deployment=float(deployment_stats_query.fastest) if deployment_stats_query.fastest else None,
        slowest_deployment=float(deployment_stats_query.slowest) if deployment_stats_query.slowest else None
    )

    return DashboardResponse(
        user=user_summary,
        summary=summary,
        recent_activity=recent_activity,
        health_overview=health_overview,
        deployment_stats=deployment_stats
    )