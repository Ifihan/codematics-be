from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class BuildTriggerRequest(BaseModel):
    """Request to trigger a build"""
    notebook_id: int
    image_tag: Optional[str] = "latest"


class BuildResponse(BaseModel):
    """Build response"""
    id: int
    notebook_id: int
    build_id: str
    status: str
    image_name: str
    log_url: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    class Config:
        from_attributes = True


class BuildListResponse(BaseModel):
    """Build list item"""
    id: int
    notebook_id: int
    build_id: str
    status: str
    image_name: str
    created_at: datetime

    class Config:
        from_attributes = True