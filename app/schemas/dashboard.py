from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class UserSummary(BaseModel):
    id: int
    username: str
    email: str
    created_at: datetime


class Summary(BaseModel):
    total_notebooks: int
    total_deployments: int
    active_deployments: int
    failed_deployments: int
    total_models: int
    total_analyses: int


class RecentActivity(BaseModel):
    type: str  # "notebook", "deployment", "analysis", "model"
    action: str  # "created", "updated", "deployed", "failed", "analyzed"
    resource_id: int
    resource_name: str
    status: Optional[str] = None
    timestamp: datetime


class HealthOverview(BaseModel):
    average_health_score: float
    notebooks_with_issues: int
    notebooks_analyzed: int


class DeploymentStats(BaseModel):
    success_rate: float
    average_build_time: float  # seconds
    total_build_time: float  # seconds
    fastest_deployment: Optional[float] = None
    slowest_deployment: Optional[float] = None


class DashboardResponse(BaseModel):
    user: UserSummary
    summary: Summary
    recent_activity: List[RecentActivity]
    health_overview: HealthOverview
    deployment_stats: DeploymentStats