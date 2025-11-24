from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_, extract
from app.db.database import get_db
from app.db.models import User, Notebook, Deployment, Analysis, ModelVersion, DeploymentMetric
from app.schemas.metrics import (
    DeploymentMetricsResponse,
    DeploymentMetricItem,
    DeploymentMetricsAggregates,
    DeploymentTimeSeriesPoint,
    NotebookHealthMetricsResponse,
    NotebookHealthItem,
    HealthDistribution,
    ModelMetricsResponse,
    ModelMetricItem,
    ModelMetricsAggregates,
    PerformanceMetricsResponse,
    PerformanceMetricItem
)
from app.utils.deps import get_current_active_user
from typing import Optional, List
from datetime import datetime, timedelta
from collections import defaultdict

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/deployments", response_model=DeploymentMetricsResponse)
def get_deployment_metrics(
    start_date: Optional[datetime] = Query(None, description="Start date for metrics period"),
    end_date: Optional[datetime] = Query(None, description="End date for metrics period"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed deployment metrics for a specific time period.

    Returns:
    - List of all deployments in the period
    - Aggregate statistics (success rate, avg build time)
    - Time-series data for charts
    """

    # Default to last 30 days if no dates provided
    if not end_date:
        end_date = datetime.utcnow()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Get all deployments in the period
    deployments_query = db.query(Deployment).filter(
        Deployment.user_id == current_user.id,
        Deployment.created_at >= start_date,
        Deployment.created_at <= end_date
    ).order_by(Deployment.created_at.desc())

    deployments = deployments_query.all()

    deployment_items = [
        DeploymentMetricItem(
            deployment_id=d.id,
            name=d.name,
            status=d.status,
            build_duration=float(d.build_duration) if d.build_duration else None,
            created_at=d.created_at,
            deployed_at=d.deployed_at,
            error_message=d.error_message
        )
        for d in deployments
    ]

    # Calculate aggregates
    total_count = len(deployments)
    successful_count = sum(1 for d in deployments if d.status == "deployed")
    failed_count = sum(1 for d in deployments if d.status == "failed")
    success_rate = (successful_count / total_count * 100) if total_count > 0 else 0.0

    build_durations = [d.build_duration for d in deployments if d.build_duration]
    avg_build_duration = sum(build_durations) / len(build_durations) if build_durations else 0.0

    aggregates = DeploymentMetricsAggregates(
        total_deployments=total_count,
        successful=successful_count,
        failed=failed_count,
        success_rate=round(success_rate, 2),
        avg_build_duration=round(avg_build_duration, 2)
    )

    # Generate time-series data (group by date)
    time_series_map = defaultdict(lambda: {"deployments": 0, "successes": 0, "failures": 0})

    for d in deployments:
        date_key = d.created_at.date().isoformat()
        time_series_map[date_key]["deployments"] += 1
        if d.status == "deployed":
            time_series_map[date_key]["successes"] += 1
        elif d.status == "failed":
            time_series_map[date_key]["failures"] += 1

    time_series = [
        DeploymentTimeSeriesPoint(
            date=date_key,
            deployments=data["deployments"],
            successes=data["successes"],
            failures=data["failures"]
        )
        for date_key, data in sorted(time_series_map.items())
    ]

    return DeploymentMetricsResponse(
        period={"start": start_date, "end": end_date},
        deployments=deployment_items,
        aggregates=aggregates,
        time_series=time_series
    )


@router.get("/notebooks/health", response_model=NotebookHealthMetricsResponse)
def get_notebook_health_metrics(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get health metrics for all notebooks.

    Returns:
    - List of notebooks with their health scores
    - Distribution of notebooks by health category
    - Average health score
    """

    # Get all notebooks with their latest analysis
    notebooks = db.query(Notebook).filter(
        Notebook.user_id == current_user.id
    ).all()

    notebook_items = []
    health_scores = []
    distribution = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}

    for notebook in notebooks:
        # Get latest analysis for this notebook
        analysis = db.query(Analysis).filter(
            Analysis.notebook_id == notebook.id
        ).order_by(Analysis.created_at.desc()).first()

        health_score = analysis.health_score if analysis else 0
        issues_count = len(analysis.issues) if analysis else 0

        notebook_items.append(NotebookHealthItem(
            notebook_id=notebook.id,
            name=notebook.name,
            health_score=health_score,
            issues_count=issues_count,
            analyzed_at=analysis.created_at if analysis else None,
            status=notebook.status
        ))

        if analysis:
            health_scores.append(health_score)

            # Categorize health score
            if health_score >= 90:
                distribution["excellent"] += 1
            elif health_score >= 70:
                distribution["good"] += 1
            elif health_score >= 50:
                distribution["fair"] += 1
            else:
                distribution["poor"] += 1

    avg_health_score = sum(health_scores) / len(health_scores) if health_scores else 0.0

    return NotebookHealthMetricsResponse(
        notebooks=notebook_items,
        distribution=HealthDistribution(**distribution),
        total_notebooks=len(notebooks),
        average_health_score=round(avg_health_score, 2)
    )


@router.get("/models", response_model=ModelMetricsResponse)
def get_model_metrics(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get metrics for all model versions.

    Returns:
    - List of all models with metadata
    - Aggregate statistics (total, active, avg accuracy)
    - Breakdown by file format
    """

    # Get all models for user's notebooks
    models = db.query(ModelVersion).join(Notebook).filter(
        Notebook.user_id == current_user.id
    ).order_by(ModelVersion.uploaded_at.desc()).all()

    model_items = []
    format_breakdown = defaultdict(int)
    total_size_bytes = 0
    active_count = 0
    accuracies = []

    for model in models:
        notebook = db.query(Notebook).filter(Notebook.id == model.notebook_id).first()

        size_mb = model.size_bytes / (1024 * 1024) if model.size_bytes else 0.0
        total_size_bytes += model.size_bytes or 0

        if model.is_active:
            active_count += 1

        if model.accuracy:
            accuracies.append(float(model.accuracy))

        if model.file_extension:
            format_breakdown[model.file_extension] += 1

        model_items.append(ModelMetricItem(
            model_id=model.id,
            notebook_id=model.notebook_id,
            notebook_name=notebook.name if notebook else "Unknown",
            version=model.version,
            accuracy=float(model.accuracy) if model.accuracy else None,
            file_extension=model.file_extension,
            size_mb=round(size_mb, 2),
            is_active=model.is_active,
            uploaded_at=model.uploaded_at
        ))

    avg_accuracy = sum(accuracies) / len(accuracies) if accuracies else None
    total_size_mb = total_size_bytes / (1024 * 1024)

    aggregates = ModelMetricsAggregates(
        total_models=len(models),
        active_models=active_count,
        avg_accuracy=round(avg_accuracy, 4) if avg_accuracy else None,
        total_size_mb=round(total_size_mb, 2)
    )

    return ModelMetricsResponse(
        models=model_items,
        aggregates=aggregates,
        format_breakdown=dict(format_breakdown)
    )


@router.get("/performance", response_model=PerformanceMetricsResponse)
def get_performance_metrics(
    resource_type: str = Query(..., description="Type of resource (deployment, notebook)"),
    resource_id: int = Query(..., description="ID of the resource"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed performance metrics for a specific resource.

    Returns:
    - List of all recorded metrics for the resource
    - Supports deployment and notebook resource types
    """

    if resource_type == "deployment":
        # Verify user owns this deployment
        deployment = db.query(Deployment).filter(
            Deployment.id == resource_id,
            Deployment.user_id == current_user.id
        ).first()

        if not deployment:
            raise HTTPException(404, "Deployment not found")

        # Get deployment metrics
        metrics = db.query(DeploymentMetric).filter(
            DeploymentMetric.deployment_id == resource_id
        ).order_by(DeploymentMetric.recorded_at.desc()).all()

        metric_items = [
            PerformanceMetricItem(
                metric_id=m.id,
                metric_type=m.metric_type,
                value=m.value,
                recorded_at=m.recorded_at
            )
            for m in metrics
        ]

    elif resource_type == "notebook":
        # Verify user owns this notebook
        notebook = db.query(Notebook).filter(
            Notebook.id == resource_id,
            Notebook.user_id == current_user.id
        ).first()

        if not notebook:
            raise HTTPException(404, "Notebook not found")

        # Get deployment metrics for all deployments of this notebook
        deployments = db.query(Deployment).filter(
            Deployment.notebook_id == resource_id
        ).all()

        deployment_ids = [d.id for d in deployments]

        metrics = db.query(DeploymentMetric).filter(
            DeploymentMetric.deployment_id.in_(deployment_ids)
        ).order_by(DeploymentMetric.recorded_at.desc()).all()

        metric_items = [
            PerformanceMetricItem(
                metric_id=m.id,
                metric_type=m.metric_type,
                value=m.value,
                recorded_at=m.recorded_at
            )
            for m in metrics
        ]
    else:
        raise HTTPException(400, f"Invalid resource_type: {resource_type}. Must be 'deployment' or 'notebook'")

    return PerformanceMetricsResponse(
        resource_type=resource_type,
        resource_id=resource_id,
        metrics=metric_items,
        total_metrics=len(metric_items)
    )