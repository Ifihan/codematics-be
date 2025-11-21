from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class CellClassification(BaseModel):
    cell_index: int
    cell_type: str
    classification: str
    reasoning: str


class Issue(BaseModel):
    severity: str
    category: str
    description: str
    cell_index: Optional[int] = None
    suggestion: str


class ResourceEstimate(BaseModel):
    cpu: str
    memory: str
    estimated_cold_start_ms: int


class AnalysisResponse(BaseModel):
    id: int
    notebook_id: int
    health_score: int
    cell_classifications: list[CellClassification]
    issues: list[Issue]
    recommendations: Optional[list[str]] = None
    resource_estimates: Optional[ResourceEstimate] = None
    created_at: datetime

    class Config:
        from_attributes = True
