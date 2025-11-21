from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class DeploymentCreate(BaseModel):
    notebook_id: int
    name: str
    region: Optional[str] = None


class DeploymentResponse(BaseModel):
    id: int
    notebook_id: int
    user_id: int
    name: str
    status: str
    build_id: Optional[str] = None
    image_url: Optional[str] = None
    service_url: Optional[str] = None
    region: str
    error_message: Optional[str] = None
    build_logs_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    deployed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
