from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from decimal import Decimal


class ModelVersionCreate(BaseModel):
    accuracy: Optional[Decimal] = Field(None, ge=0, le=100)


class ModelVersionResponse(BaseModel):
    id: int
    notebook_id: int
    version: int
    gcs_path: str
    size_bytes: Optional[int]
    accuracy: Optional[Decimal]
    is_active: bool
    uploaded_at: datetime

    class Config:
        from_attributes = True


class ModelVersionList(BaseModel):
    versions: list[ModelVersionResponse]
    total: int
