from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DeploymentCreate(BaseModel):
    """Request to create a deployment"""
    notebook_id: int
    build_id: Optional[int] = None
    cpu: str = "1"
    memory: str = "512Mi"
    min_instances: int = 0
    max_instances: int = 10


class DeploymentResponse(BaseModel):
    """Deployment details"""
    id: int
    notebook_id: int
    build_id: Optional[int]
    service_name: str
    service_url: Optional[str]
    revision_name: Optional[str]
    status: str
    image_uri: str
    traffic_percent: int
    error_message: Optional[str]
    created_at: datetime
    deployed_at: Optional[datetime]

    class Config:
        from_attributes = True


class DeploymentListResponse(BaseModel):
    """List of deployments"""
    id: int
    notebook_id: int
    service_name: str
    service_url: Optional[str]
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TrafficUpdate(BaseModel):
    """Update traffic distribution"""
    revision_name: str
    traffic_percent: int