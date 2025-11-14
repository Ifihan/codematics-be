from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class NotebookUploadResponse(BaseModel):
    """Response after uploading a notebook"""
    id: int
    name: str
    filename: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class NotebookResponse(BaseModel):
    """Full notebook details"""
    id: int
    name: str
    filename: str
    file_path: str
    user_id: int
    status: str
    main_py_path: Optional[str]
    requirements_txt_path: Optional[str]
    dependencies: Optional[List[str]]
    code_cells_count: Optional[int]
    syntax_valid: Optional[bool]
    created_at: datetime
    updated_at: Optional[datetime]
    parsed_at: Optional[datetime]

    class Config:
        from_attributes = True


class NotebookParseResponse(BaseModel):
    """Response after parsing a notebook"""
    id: int
    status: str
    code_cells_count: int
    syntax_valid: bool
    dependencies: List[str]
    dependencies_count: int
    parsed_at: datetime


class NotebookListResponse(BaseModel):
    """List of notebooks"""
    id: int
    name: str
    filename: str
    status: str
    code_cells_count: Optional[int]
    dependencies_count: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True