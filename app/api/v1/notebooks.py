from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from pathlib import Path

from app.db.database import get_db
from app.db.models import User, Notebook
from app.schemas.notebook import NotebookUploadResponse, NotebookResponse, NotebookParseResponse, NotebookListResponse
from app.utils.deps import get_current_active_user
from app.utils.helpers import get_or_404
from app.core.notebook_service import NotebookService

router = APIRouter(prefix="/notebooks", tags=["notebooks"])
service = NotebookService()


def get_user_notebook(db: Session, notebook_id: int, user_id: int) -> Notebook:
    """Get notebook belonging to user or raise 404"""
    return get_or_404(db, Notebook, id=notebook_id, user_id=user_id)


@router.post("/upload", response_model=NotebookUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_notebook(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Upload a Jupyter notebook"""
    if not file.filename.endswith('.ipynb'):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only .ipynb files allowed")

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

    notebook.file_path = service.save_uploaded_file(content, file.filename, current_user.id, notebook.id)
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
    notebook = get_user_notebook(db, notebook_id, current_user.id)

    if notebook.status not in ["uploaded", "parsed"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cannot parse notebook in status: {notebook.status}")

    try:
        service.parse_notebook(notebook, db)
    except Exception as e:
        notebook.status = "parse_failed"
        db.commit()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Parse failed: {str(e)}")

    return NotebookParseResponse(
        id=notebook.id,
        status=notebook.status,
        code_cells_count=notebook.code_cells_count,
        syntax_valid=notebook.syntax_valid,
        dependencies=notebook.dependencies,
        dependencies_count=len(notebook.dependencies or []),
        parsed_at=notebook.parsed_at
    )


@router.get("", response_model=List[NotebookListResponse])
def list_notebooks(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all notebooks for current user"""
    notebooks = db.query(Notebook).filter_by(user_id=current_user.id).order_by(Notebook.created_at.desc()).all()
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
    return get_user_notebook(db, notebook_id, current_user.id)


@router.get("/{notebook_id}/files/{file_type}")
def download_file(
    notebook_id: int,
    file_type: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Download generated files (main.py or requirements.txt)"""
    notebook = get_user_notebook(db, notebook_id, current_user.id)

    file_map = {
        "main.py": (notebook.main_py_path, "text/x-python", "main.py"),
        "requirements.txt": (notebook.requirements_txt_path, "text/plain", "requirements.txt")
    }

    if file_type not in file_map:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid file type")

    file_path, media_type, filename = file_map[file_type]

    if not file_path or not Path(file_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{file_type} not generated. Parse notebook first.")

    return FileResponse(file_path, media_type=media_type, filename=filename)


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notebook(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a notebook and its files"""
    notebook = get_user_notebook(db, notebook_id, current_user.id)
    service.delete_notebook_files(notebook)
    db.delete(notebook)
    db.commit()
