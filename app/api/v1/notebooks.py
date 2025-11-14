from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.db.models import User, Notebook
from app.schemas.notebook import (
    NotebookUploadResponse,
    NotebookResponse,
    NotebookParseResponse,
    NotebookListResponse
)
from app.utils.deps import get_current_active_user
from app.core.notebook_service import NotebookService

router = APIRouter(prefix="/notebooks", tags=["notebooks"])
notebook_service = NotebookService()


@router.post("/upload", response_model=NotebookUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_notebook(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Upload a Jupyter notebook"""
    if not file.filename.endswith('.ipynb'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .ipynb files are allowed"
        )

    content = await file.read()

    notebook = Notebook(
        name=file.filename.replace('.ipynb', ''),
        filename=file.filename,
        file_path="",
        user_id=current_user.id,
        status="uploading"
    )

    db.add(notebook)
    db.commit()
    db.refresh(notebook)

    file_path = notebook_service.save_uploaded_file(
        content,
        file.filename,
        current_user.id,
        notebook.id
    )

    notebook.file_path = file_path
    notebook.status = "uploaded"
    db.commit()
    db.refresh(notebook)

    return notebook


@router.post("/{notebook_id}/parse", response_model=NotebookParseResponse)
def parse_notebook(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Parse notebook and extract dependencies"""
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    if notebook.status not in ["uploaded", "parsed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot parse notebook in status: {notebook.status}"
        )

    try:
        result = notebook_service.parse_notebook(notebook, db)
    except Exception as e:
        notebook.status = "parse_failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse notebook: {str(e)}"
        )

    return NotebookParseResponse(
        id=notebook.id,
        status=notebook.status,
        code_cells_count=notebook.code_cells_count,
        syntax_valid=notebook.syntax_valid,
        dependencies=notebook.dependencies,
        dependencies_count=len(notebook.dependencies) if notebook.dependencies else 0,
        parsed_at=notebook.parsed_at
    )


@router.get("", response_model=List[NotebookListResponse])
def list_notebooks(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all notebooks for current user"""
    notebooks = db.query(Notebook).filter(
        Notebook.user_id == current_user.id
    ).order_by(Notebook.created_at.desc()).all()

    return [
        NotebookListResponse(
            id=nb.id,
            name=nb.name,
            filename=nb.filename,
            status=nb.status,
            code_cells_count=nb.code_cells_count,
            dependencies_count=len(nb.dependencies) if nb.dependencies else None,
            created_at=nb.created_at
        )
        for nb in notebooks
    ]


@router.get("/{notebook_id}", response_model=NotebookResponse)
def get_notebook(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get notebook details"""
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    return notebook


@router.get("/{notebook_id}/files/main.py")
def download_main_py(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Download generated main.py"""
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    if not notebook.main_py_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="main.py not generated yet. Parse the notebook first."
        )

    return FileResponse(
        notebook.main_py_path,
        media_type="text/x-python",
        filename="main.py"
    )


@router.get("/{notebook_id}/files/requirements.txt")
def download_requirements_txt(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Download generated requirements.txt"""
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    if not notebook.requirements_txt_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="requirements.txt not generated yet. Parse the notebook first."
        )

    return FileResponse(
        notebook.requirements_txt_path,
        media_type="text/plain",
        filename="requirements.txt"
    )


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notebook(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a notebook and its files"""
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()

    if not notebook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found"
        )

    notebook_service.delete_notebook_files(notebook)
    db.delete(notebook)
    db.commit()

    return None