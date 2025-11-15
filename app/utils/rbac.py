from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import User, Role
from app.utils.deps import get_current_active_user
from typing import List


class Permissions:
    """Permission constants"""
    NOTEBOOK_CREATE = "notebook:create"
    NOTEBOOK_READ = "notebook:read"
    NOTEBOOK_UPDATE = "notebook:update"
    NOTEBOOK_DELETE = "notebook:delete"

    BUILD_TRIGGER = "build:trigger"
    BUILD_READ = "build:read"
    BUILD_CANCEL = "build:cancel"

    DEPLOY_CREATE = "deploy:create"
    DEPLOY_READ = "deploy:read"
    DEPLOY_UPDATE = "deploy:update"
    DEPLOY_DELETE = "deploy:delete"

    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"

    ADMIN_ALL = "admin:all"


class Roles:
    """Default role names"""
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


DEFAULT_ROLES = {
    Roles.ADMIN: {
        "description": "Full system access",
        "permissions": [Permissions.ADMIN_ALL]
    },
    Roles.DEVELOPER: {
        "description": "Can create and deploy notebooks",
        "permissions": [
            Permissions.NOTEBOOK_CREATE,
            Permissions.NOTEBOOK_READ,
            Permissions.NOTEBOOK_UPDATE,
            Permissions.NOTEBOOK_DELETE,
            Permissions.BUILD_TRIGGER,
            Permissions.BUILD_READ,
            Permissions.BUILD_CANCEL,
            Permissions.DEPLOY_CREATE,
            Permissions.DEPLOY_READ,
            Permissions.DEPLOY_UPDATE,
            Permissions.DEPLOY_DELETE,
        ]
    },
    Roles.VIEWER: {
        "description": "Read-only access",
        "permissions": [
            Permissions.NOTEBOOK_READ,
            Permissions.BUILD_READ,
            Permissions.DEPLOY_READ,
        ]
    }
}


def has_permission(user: User, permission: str, db: Session) -> bool:
    """Check if user has a specific permission"""
    if user.is_superuser:
        return True

    user_roles = db.query(Role).join(Role.users).filter(User.id == user.id).all()

    for role in user_roles:
        if Permissions.ADMIN_ALL in (role.permissions or []):
            return True

        if permission in (role.permissions or []):
            return True

    return False


def require_permission(permission: str):
    """Dependency to require a specific permission"""
    def permission_checker(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ):
        if not has_permission(current_user, permission, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission} required"
            )
        return current_user

    return permission_checker


def require_any_permission(permissions: List[str]):
    """Dependency to require any of the specified permissions"""
    def permission_checker(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ):
        for permission in permissions:
            if has_permission(current_user, permission, db):
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: one of {permissions} required"
        )

    return permission_checker


def require_role(role_name: str):
    """Dependency to require a specific role"""
    def role_checker(
        current_user: User = Depends(get_current_active_user),
        db: Session = Depends(get_db)
    ):
        if current_user.is_superuser:
            return current_user

        user_roles = db.query(Role).join(Role.users).filter(User.id == current_user.id).all()

        if not any(role.name == role_name for role in user_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: {role_name}"
            )

        return current_user

    return role_checker


def init_default_roles(db: Session):
    """Initialize default roles in database"""
    for role_name, role_data in DEFAULT_ROLES.items():
        existing_role = db.query(Role).filter(Role.name == role_name).first()

        if not existing_role:
            role = Role(
                name=role_name,
                description=role_data["description"],
                permissions=role_data["permissions"]
            )
            db.add(role)

    db.commit()