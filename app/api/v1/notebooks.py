from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from pathlib import Path
from fastapi.responses import FileResponse, Response

from app.db.database import get_db
from app.utils.deps import get_current_active_user
from app.db.models import User, Notebook, Analysis, Deployment
from app.schemas.notebook import (
    NotebookUploadResponse, NotebookParseResponse, 
    NotebookListResponse, NotebookResponse
)
from app.schemas.analysis import AnalysisResponse
from app.core.notebook_service import NotebookService
from app.core.gemini import GeminiService
from app.core.export_service import ExportService
from app.core.monitoring import MonitoringService

router = APIRouter(prefix="/notebooks", tags=["notebooks"])
service = NotebookService()
gemini = GeminiService()
export_service = ExportService()
monitoring = MonitoringService()

def get_user_notebook(db: Session, notebook_id: int, user_id: int) -> Notebook:
    notebook = db.query(Notebook).filter(Notebook.id == notebook_id, Notebook.user_id == user_id).first()
    if not notebook:
        raise HTTPException(status_code=404, detail="Notebook not found")
    return notebook

@router.post("/upload", response_model=NotebookUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_notebook(
    notebook_file: UploadFile = File(...),
    model_file: UploadFile = File(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if not notebook_file.filename.endswith('.ipynb'):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only .ipynb files allowed")

    content = await notebook_file.read()
    notebook = Notebook(
        name=notebook_file.filename.replace('.ipynb', ''),
        filename=notebook_file.filename,
        file_path="",
        user_id=current_user.id,
        status="uploading"
    )
    db.add(notebook)
    db.commit()
    db.refresh(notebook)

    notebook.file_path = service.save_uploaded_file(content, notebook_file.filename, current_user.id, notebook.id)
    notebook.status = "uploaded"
    db.commit()
    db.refresh(notebook)

    if model_file:
        from app.api.v1.model_versions import upload_model_version_internal
        await upload_model_version_internal(notebook.id, model_file, None, current_user, db)

    return notebook

@router.post("/{notebook_id}/parse", response_model=NotebookParseResponse)
def parse_notebook(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
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
    return get_user_notebook(db, notebook_id, current_user.id)

@router.get("/{notebook_id}/files/{file_type}")
def download_file(
    notebook_id: int,
    file_type: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    notebook = get_user_notebook(db, notebook_id, current_user.id)

    file_map = {
        "main.py": (notebook.main_py_path, "text/x-python", "main.py"),
        "requirements.txt": (notebook.requirements_txt_path, "text/plain", "requirements.txt")
    }

    if file_type not in file_map:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid file type")

    file_path, media_type, filename = file_map[file_type]

    if not file_path:
         raise HTTPException(status.HTTP_404_NOT_FOUND, f"{file_type} not generated. Parse notebook first.")

    if file_path.startswith("gs://"):
        try:
            blob_name = service.storage.parse_gcs_uri(file_path)
            content = service.storage.download_as_string(blob_name)
            return Response(
                content=content,
                media_type=media_type,
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )
        except Exception as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"File not found in storage: {str(e)}")

    if not Path(file_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{file_type} not found on server.")

    return FileResponse(file_path, media_type=media_type, filename=filename)

@router.post("/{notebook_id}/analyze", response_model=AnalysisResponse)
def analyze_notebook(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    notebook = get_user_notebook(db, notebook_id, current_user.id)

    if notebook.status not in ["parsed"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Notebook must be parsed before analysis")

    existing_analysis = db.query(Analysis).filter_by(notebook_id=notebook_id).first()
    if existing_analysis:
        return existing_analysis

    if notebook.main_py_path:
        if notebook.main_py_path.startswith("gs://"):
            blob_name = service.storage.parse_gcs_uri(notebook.main_py_path)
            notebook_content = service.storage.download_as_string(blob_name)
        elif Path(notebook.main_py_path).exists():
            notebook_content = Path(notebook.main_py_path).read_text()
        else:
            notebook_content = ""
    else:
        notebook_content = ""
    analysis_result = gemini.analyze_notebook(notebook_content, notebook.dependencies or [])
    health_score = gemini.calculate_health_score(analysis_result)

    analysis = Analysis(
        notebook_id=notebook_id,
        health_score=health_score,
        cell_classifications=analysis_result.get('cell_classifications', []),
        issues=analysis_result.get('issues', []),
        recommendations=analysis_result.get('recommendations'),
        resource_estimates=analysis_result.get('resource_estimates')
    )

    db.add(analysis)
    notebook.status = "analyzed"
    db.commit()
    db.refresh(analysis)

    monitoring.track_analysis(health_score)

    return analysis


@router.get("/{notebook_id}/export")
def export_notebook(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    notebook = get_user_notebook(db, notebook_id, current_user.id)

    if notebook.status not in ["parsed", "analyzed"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Notebook must be parsed before export")

    analysis = db.query(Analysis).filter_by(notebook_id=notebook_id).first()
    deployment = db.query(Deployment).filter_by(notebook_id=notebook_id).order_by(Deployment.created_at.desc()).first()

    zip_path = export_service.create_export_package(notebook, analysis, deployment, db)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{notebook.name}.zip"
    )


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notebook(
    notebook_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    notebook = get_user_notebook(db, notebook_id, current_user.id)
    service.delete_notebook_files(notebook)
    db.delete(notebook)
    db.commit()
