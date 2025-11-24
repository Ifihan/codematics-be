from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


# Deployment Metrics Schemas
class DeploymentMetricItem(BaseModel):
    deployment_id: int
    name: str
    status: str
    build_duration: Optional[float] = None
    created_at: datetime
    deployed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class DeploymentMetricsAggregates(BaseModel):
    total_deployments: int
    successful: int
    failed: int
    success_rate: float
    avg_build_duration: float


class DeploymentTimeSeriesPoint(BaseModel):
    date: str
    deployments: int
    successes: int
    failures: int


class DeploymentMetricsResponse(BaseModel):
    period: Dict[str, datetime]
    deployments: List[DeploymentMetricItem]
    aggregates: DeploymentMetricsAggregates
    time_series: List[DeploymentTimeSeriesPoint]


# Notebook Health Metrics Schemas
class NotebookHealthItem(BaseModel):
    notebook_id: int
    name: str
    health_score: int
    issues_count: int
    analyzed_at: Optional[datetime] = None
    status: str


class HealthDistribution(BaseModel):
    excellent: int = Field(description="90-100 health score")
    good: int = Field(description="70-89 health score")
    fair: int = Field(description="50-69 health score")
    poor: int = Field(description="<50 health score")


class NotebookHealthMetricsResponse(BaseModel):
    notebooks: List[NotebookHealthItem]
    distribution: HealthDistribution
    total_notebooks: int
    average_health_score: float


# Model Metrics Schemas
class ModelMetricItem(BaseModel):
    model_id: int
    notebook_id: int
    notebook_name: str
    version: int
    accuracy: Optional[float] = None
    file_extension: Optional[str] = None
    size_mb: float
    is_active: bool
    uploaded_at: datetime


class ModelMetricsAggregates(BaseModel):
    total_models: int
    active_models: int
    avg_accuracy: Optional[float] = None
    total_size_mb: float


class ModelMetricsResponse(BaseModel):
    models: List[ModelMetricItem]
    aggregates: ModelMetricsAggregates
    format_breakdown: Dict[str, int]


# Performance Metrics Schemas
class PerformanceMetricItem(BaseModel):
    metric_id: int
    metric_type: str
    value: Dict[str, Any]
    recorded_at: datetime


class PerformanceMetricsResponse(BaseModel):
    resource_type: str
    resource_id: int
    metrics: List[PerformanceMetricItem]
    total_metrics: int


# System Overview Metrics (Admin Only)
class SystemMetricsResponse(BaseModel):
    total_users: int
    total_notebooks: int
    total_deployments: int
    total_models: int
    active_users_last_30_days: int
    total_storage_mb: float
    avg_health_score: float


# Admin User Activity Metrics
class UserActivityItem(BaseModel):
    user_id: int
    username: str
    email: str
    total_notebooks: int
    total_deployments: int
    total_models: int
    last_activity: Optional[datetime] = None
    created_at: datetime


class AdminUserActivityResponse(BaseModel):
    users: List[UserActivityItem]
    total_users: int
    active_users: int
    inactive_users: int


# Admin Deployment Overview
class AdminDeploymentOverviewResponse(BaseModel):
    total_deployments: int
    successful_deployments: int
    failed_deployments: int
    active_deployments: int
    success_rate: float
    total_build_time_hours: float
    avg_build_time_seconds: float
    deployments_last_24h: int
    deployments_last_7d: int
    deployments_last_30d: int