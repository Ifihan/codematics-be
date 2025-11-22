from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import TypeVar, Type

T = TypeVar('T')

def get_or_404(db: Session, model: Type[T], **filters) -> T:
    """Get model instance or raise 404"""
    instance = db.query(model).filter_by(**filters).first()
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{model.__name__} not found"
        )
    return instance
