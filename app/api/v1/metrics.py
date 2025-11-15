from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import Optional
from datetime import datetime, timedelta
from app.db.database import get_db
from app.db.models import User, Notebook, Build, Deployment
from app.utils.deps import get_current_active_user
from pydantic import BaseModel

router = APIRouter(prefix="/metrics", tags=["metrics"])


class BuildMetrics(BaseModel):
    """Build metrics response"""
    total_builds: int
    successful_builds: int
    failed_builds: int
    success_rate: float
    average_build_time_seconds: Optional[float]
    builds_by_status: dict


class DeploymentMetrics(BaseModel):
    """Deployment metrics response"""
    total_deployments: int
    successful_deployments: int
    failed_deployments: int
    active_deployments: int
    success_rate: float
    deployments_by_status: dict


class UserActivityMetrics(BaseModel):
    """User activity metrics"""
    total_notebooks: int
    total_builds: int
    total_deployments: int
    recent_activity: list


class SystemMetrics(BaseModel):
    """System-wide metrics"""
    total_users: int
    total_notebooks: int
    total_builds: int
    total_deployments: int
    builds_last_24h: int
    deployments_last_24h: int


@router.get("/builds", response_model=BuildMetrics)
def get_build_metrics(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get build metrics for current user"""
    start_date = datetime.utcnow() - timedelta(days=days)

    builds = db.query(Build).join(Notebook).filter(
        Notebook.user_id == current_user.id,
        Build.created_at >= start_date
    ).all()

    total_builds = len(builds)
    successful_builds = sum(1 for b in builds if b.status == "success")
    failed_builds = sum(1 for b in builds if b.status == "failed")

    success_rate = (successful_builds / total_builds * 100) if total_builds > 0 else 0.0

    build_times = []
    for build in builds:
        if build.started_at and build.finished_at:
            duration = (build.finished_at - build.started_at).total_seconds()
            build_times.append(duration)

    average_build_time = sum(build_times) / len(build_times) if build_times else None

    status_counts = {}
    for build in builds:
        status_counts[build.status] = status_counts.get(build.status, 0) + 1

    return BuildMetrics(
        total_builds=total_builds,
        successful_builds=successful_builds,
        failed_builds=failed_builds,
        success_rate=round(success_rate, 2),
        average_build_time_seconds=round(average_build_time, 2) if average_build_time else None,
        builds_by_status=status_counts
    )


@router.get("/deployments", response_model=DeploymentMetrics)
def get_deployment_metrics(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get deployment metrics for current user"""
    start_date = datetime.utcnow() - timedelta(days=days)

    deployments = db.query(Deployment).join(Notebook).filter(
        Notebook.user_id == current_user.id,
        Deployment.created_at >= start_date
    ).all()

    total_deployments = len(deployments)
    successful_deployments = sum(1 for d in deployments if d.status == "deployed")
    failed_deployments = sum(1 for d in deployments if d.status == "failed")
    active_deployments = sum(1 for d in deployments if d.status == "deployed" and d.service_url)

    success_rate = (successful_deployments / total_deployments * 100) if total_deployments > 0 else 0.0

    status_counts = {}
    for deployment in deployments:
        status_counts[deployment.status] = status_counts.get(deployment.status, 0) + 1

    return DeploymentMetrics(
        total_deployments=total_deployments,
        successful_deployments=successful_deployments,
        failed_deployments=failed_deployments,
        active_deployments=active_deployments,
        success_rate=round(success_rate, 2),
        deployments_by_status=status_counts
    )


@router.get("/activity", response_model=UserActivityMetrics)
def get_user_activity(
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get user activity metrics"""
    start_date = datetime.utcnow() - timedelta(days=days)

    total_notebooks = db.query(func.count(Notebook.id)).filter(
        Notebook.user_id == current_user.id
    ).scalar()

    total_builds = db.query(func.count(Build.id)).join(Notebook).filter(
        Notebook.user_id == current_user.id
    ).scalar()

    total_deployments = db.query(func.count(Deployment.id)).join(Notebook).filter(
        Notebook.user_id == current_user.id
    ).scalar()

    recent_builds = db.query(Build).join(Notebook).filter(
        Notebook.user_id == current_user.id,
        Build.created_at >= start_date
    ).order_by(Build.created_at.desc()).limit(10).all()

    recent_deployments = db.query(Deployment).join(Notebook).filter(
        Notebook.user_id == current_user.id,
        Deployment.created_at >= start_date
    ).order_by(Deployment.created_at.desc()).limit(10).all()

    recent_activity = []

    for build in recent_builds:
        recent_activity.append({
            "type": "build",
            "id": build.id,
            "status": build.status,
            "notebook_id": build.notebook_id,
            "created_at": build.created_at.isoformat()
        })

    for deployment in recent_deployments:
        recent_activity.append({
            "type": "deployment",
            "id": deployment.id,
            "status": deployment.status,
            "notebook_id": deployment.notebook_id,
            "service_url": deployment.service_url,
            "created_at": deployment.created_at.isoformat()
        })

    recent_activity.sort(key=lambda x: x["created_at"], reverse=True)

    return UserActivityMetrics(
        total_notebooks=total_notebooks,
        total_builds=total_builds,
        total_deployments=total_deployments,
        recent_activity=recent_activity[:20]
    )


@router.get("/system", response_model=SystemMetrics)
def get_system_metrics(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get system-wide metrics (admin only in production)"""
    last_24h = datetime.utcnow() - timedelta(hours=24)

    total_users = db.query(func.count(User.id)).scalar()
    total_notebooks = db.query(func.count(Notebook.id)).scalar()
    total_builds = db.query(func.count(Build.id)).scalar()
    total_deployments = db.query(func.count(Deployment.id)).scalar()

    builds_last_24h = db.query(func.count(Build.id)).filter(
        Build.created_at >= last_24h
    ).scalar()

    deployments_last_24h = db.query(func.count(Deployment.id)).filter(
        Deployment.created_at >= last_24h
    ).scalar()

    return SystemMetrics(
        total_users=total_users,
        total_notebooks=total_notebooks,
        total_builds=total_builds,
        total_deployments=total_deployments,
        builds_last_24h=builds_last_24h,
        deployments_last_24h=deployments_last_24h
    )


@router.get("/timeseries/builds")
def get_build_timeseries(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get build metrics over time"""
    start_date = datetime.utcnow() - timedelta(days=days)

    builds = db.query(
        func.date(Build.created_at).label('date'),
        func.count(Build.id).label('total'),
        func.sum(func.case((Build.status == 'success', 1), else_=0)).label('successful'),
        func.sum(func.case((Build.status == 'failed', 1), else_=0)).label('failed')
    ).join(Notebook).filter(
        Notebook.user_id == current_user.id,
        Build.created_at >= start_date
    ).group_by(func.date(Build.created_at)).order_by(func.date(Build.created_at)).all()

    return {
        "period_days": days,
        "data": [
            {
                "date": str(b.date),
                "total": b.total,
                "successful": b.successful or 0,
                "failed": b.failed or 0,
                "success_rate": round((b.successful or 0) / b.total * 100, 2) if b.total > 0 else 0
            }
            for b in builds
        ]
    }


@router.get("/timeseries/deployments")
def get_deployment_timeseries(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get deployment metrics over time"""
    start_date = datetime.utcnow() - timedelta(days=days)

    deployments = db.query(
        func.date(Deployment.created_at).label('date'),
        func.count(Deployment.id).label('total'),
        func.sum(func.case((Deployment.status == 'deployed', 1), else_=0)).label('successful'),
        func.sum(func.case((Deployment.status == 'failed', 1), else_=0)).label('failed')
    ).join(Notebook).filter(
        Notebook.user_id == current_user.id,
        Deployment.created_at >= start_date
    ).group_by(func.date(Deployment.created_at)).order_by(func.date(Deployment.created_at)).all()

    return {
        "period_days": days,
        "data": [
            {
                "date": str(d.date),
                "total": d.total,
                "successful": d.successful or 0,
                "failed": d.failed or 0,
                "success_rate": round((d.successful or 0) / d.total * 100, 2) if d.total > 0 else 0
            }
            for d in deployments
        ]
    }


@router.get("/logs/builds/{build_id}")
def get_build_logs_aggregated(
    build_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get aggregated logs for a specific build"""
    build = db.query(Build).join(Notebook).filter(
        Build.id == build_id,
        Notebook.user_id == current_user.id
    ).first()

    if not build:
        return {"error": "Build not found"}

    return {
        "build_id": build.id,
        "build_gcp_id": build.build_id,
        "status": build.status,
        "created_at": build.created_at,
        "started_at": build.started_at,
        "finished_at": build.finished_at,
        "duration_seconds": (build.finished_at - build.started_at).total_seconds() if build.started_at and build.finished_at else None,
        "error_message": build.error_message,
        "log_url": build.log_url,
        "image_name": build.image_name,
        "source_bucket": build.source_bucket,
        "source_object": build.source_object
    }


@router.get("/logs/deployments/{deployment_id}")
def get_deployment_logs_aggregated(
    deployment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get aggregated logs for a specific deployment"""
    deployment = db.query(Deployment).join(Notebook).filter(
        Deployment.id == deployment_id,
        Notebook.user_id == current_user.id
    ).first()

    if not deployment:
        return {"error": "Deployment not found"}

    return {
        "deployment_id": deployment.id,
        "service_name": deployment.service_name,
        "service_url": deployment.service_url,
        "status": deployment.status,
        "created_at": deployment.created_at,
        "deployed_at": deployment.deployed_at,
        "duration_seconds": (deployment.deployed_at - deployment.created_at).total_seconds() if deployment.deployed_at else None,
        "error_message": deployment.error_message,
        "image_uri": deployment.image_uri,
        "revision_name": deployment.revision_name,
        "traffic_percent": deployment.traffic_percent
    }