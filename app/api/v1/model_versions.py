from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from sqlalchemy.orm import Session
from typing import Optional
from decimal import Decimal
import struct

from app.db.database import get_db
from app.db.models import User, Notebook, ModelVersion
from app.schemas.model_version import ModelVersionCreate, ModelVersionResponse, ModelVersionList
from app.utils.deps import get_current_user
from app.core.storage import StorageService

router = APIRouter()
storage = StorageService()

ALLOWED_EXTENSIONS = {'.pkl', '.h5', '.pt', '.joblib'}
MAX_SIZE = 500 * 1024 * 1024

MAGIC_BYTES = {
    '.pkl': [b'\x80\x03', b'\x80\x04', b'\x80\x05'],
    '.h5': [b'\x89HDF'],
    '.pt': [b'PK\x03\x04'],
    '.joblib': [b'\x80\x03', b'\x80\x04']
}


def validate_magic_bytes(content: bytes, ext: str) -> bool:
    if ext not in MAGIC_BYTES:
        return True
    for magic in MAGIC_BYTES[ext]:
        if content.startswith(magic):
            return True
    return False


async def upload_model_version_internal(
    notebook_id: int,
    file: UploadFile,
    accuracy: Optional[float],
    current_user: User,
    db: Session
) -> ModelVersion:
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()
    if not notebook:
        raise HTTPException(404, "Notebook not found")

    file_ext = '.' + file.filename.split('.')[-1] if '.' in file.filename else ''
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(400, "File too large. Max 500MB")

    if not validate_magic_bytes(content, file_ext):
        raise HTTPException(400, f"Invalid file format. File does not match {file_ext} signature")

    max_version = db.query(ModelVersion.version).filter(
        ModelVersion.notebook_id == notebook_id
    ).order_by(ModelVersion.version.desc()).first()

    version = (max_version[0] + 1) if max_version else 1

    gcs_path = storage.upload_model_version(
        current_user.id,
        notebook_id,
        version,
        content,
        file_ext
    )

    model_version = ModelVersion(
        notebook_id=notebook_id,
        version=version,
        gcs_path=gcs_path,
        size_bytes=len(content),
        accuracy=Decimal(str(accuracy)) if accuracy else None,
        is_active=True
    )
    db.add(model_version)
    db.commit()
    db.refresh(model_version)

    storage.create_latest_pointer(current_user.id, notebook_id, version)

    return model_version


@router.post("/notebooks/{notebook_id}/models", response_model=ModelVersionResponse)
async def upload_model_version(
    notebook_id: int,
    file: UploadFile = File(...),
    accuracy: Optional[float] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return await upload_model_version_internal(notebook_id, file, accuracy, current_user, db)


@router.get("/notebooks/{notebook_id}/models", response_model=ModelVersionList)
def list_model_versions(
    notebook_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()
    if not notebook:
        raise HTTPException(404, "Notebook not found")

    versions = db.query(ModelVersion).filter(
        ModelVersion.notebook_id == notebook_id
    ).order_by(ModelVersion.version.desc()).all()

    return ModelVersionList(versions=versions, total=len(versions))


@router.post("/notebooks/{notebook_id}/models/{version}/activate", response_model=ModelVersionResponse)
def activate_model_version(
    notebook_id: int,
    version: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()
    if not notebook:
        raise HTTPException(404, "Notebook not found")

    model_version = db.query(ModelVersion).filter(
        ModelVersion.notebook_id == notebook_id,
        ModelVersion.version == version
    ).first()
    if not model_version:
        raise HTTPException(404, "Model version not found")

    db.query(ModelVersion).filter(
        ModelVersion.notebook_id == notebook_id
    ).update({"is_active": False})

    model_version.is_active = True
    db.commit()
    db.refresh(model_version)

    storage.create_latest_pointer(current_user.id, notebook_id, version)

    return model_version


@router.put("/notebooks/{notebook_id}/models/replace", response_model=ModelVersionResponse)
async def replace_active_model(
    notebook_id: int,
    file: UploadFile = File(...),
    accuracy: Optional[float] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()
    if not notebook:
        raise HTTPException(404, "Notebook not found")

    new_version = await upload_model_version_internal(notebook_id, file, accuracy, current_user, db)
    return new_version


@router.delete("/notebooks/{notebook_id}/models/{version}")
def delete_model_version(
    notebook_id: int,
    version: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    notebook = db.query(Notebook).filter(
        Notebook.id == notebook_id,
        Notebook.user_id == current_user.id
    ).first()
    if not notebook:
        raise HTTPException(404, "Notebook not found")

    model_version = db.query(ModelVersion).filter(
        ModelVersion.notebook_id == notebook_id,
        ModelVersion.version == version
    ).first()
    if not model_version:
        raise HTTPException(404, "Model version not found")

    if model_version.is_active:
        raise HTTPException(400, "Cannot delete active version")

    storage.delete_model_version(current_user.id, notebook_id, version)
    db.delete(model_version)
    db.commit()

    return {"message": "Model version deleted"}
