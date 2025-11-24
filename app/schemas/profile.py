from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ProfileUpdate(BaseModel):
    """Schema for updating user profile."""
    bio: Optional[str] = Field(None, description="User bio/about section", max_length=2000)
    primary_stack: Optional[str] = Field(None, description="Primary tech stack (e.g., 'PyTorch, TensorFlow, Scikit-learn')", max_length=512)
    research_interests: Optional[str] = Field(None, description="Research interests (e.g., 'Computer Vision, NLP, Reinforcement Learning')", max_length=2000)
    is_profile_public: Optional[bool] = Field(None, description="Toggle to make profile public for portfolio viewing")


class ProfileResponse(BaseModel):
    """Schema for user's own profile response."""
    id: int
    username: str
    email: str
    bio: Optional[str]
    primary_stack: Optional[str]
    research_interests: Optional[str]
    is_profile_public: bool
    github_username: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class PublicNotebookItem(BaseModel):
    """Schema for notebook in public portfolio."""
    id: int
    name: str
    health_score: Optional[int]
    has_deployment: bool
    deployment_url: Optional[str]
    created_at: datetime


class PublicDeploymentItem(BaseModel):
    """Schema for deployment in public portfolio."""
    id: int
    name: str
    notebook_name: str
    service_url: Optional[str]
    status: str
    deployed_at: Optional[datetime]


class PublicProfileStats(BaseModel):
    """Statistics for public profile."""
    total_notebooks: int
    total_deployments: int
    active_deployments: int
    total_models: int
    avg_health_score: float


class PublicProfileResponse(BaseModel):
    """Schema for public profile portfolio view."""
    username: str
    bio: Optional[str]
    primary_stack: Optional[str]
    research_interests: Optional[str]
    github_username: Optional[str]
    created_at: datetime

    # Portfolio data
    stats: PublicProfileStats
    notebooks: List[PublicNotebookItem]
    deployments: List[PublicDeploymentItem]

    class Config:
        from_attributes = True