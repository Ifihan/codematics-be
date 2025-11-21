from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db.database import get_db
from app.db.models import User, Role, Organization, user_roles
from app.utils.rbac import require_role, Roles, Permissions, init_default_roles, DEFAULT_ROLES
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/admin", tags=["admin"])


class UserResponse(BaseModel):
    """User response"""
    id: int
    email: str
    username: str
    is_active: bool
    is_superuser: bool
    organization_id: int | None
    roles: List[str]

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Update user"""
    is_active: bool | None = None
    is_superuser: bool | None = None
    organization_id: int | None = None


class RoleResponse(BaseModel):
    """Role response"""
    id: int
    name: str
    description: str | None
    permissions: List[str]

    class Config:
        from_attributes = True


class RoleCreate(BaseModel):
    """Create role"""
    name: str
    description: str | None = None
    permissions: List[str]


class AssignRoleRequest(BaseModel):
    """Assign role to user"""
    user_id: int
    role_id: int


class OrganizationResponse(BaseModel):
    """Organization response"""
    id: int
    name: str
    owner_id: int
    is_active: bool

    class Config:
        from_attributes = True


class OrganizationCreate(BaseModel):
    """Create organization"""
    name: str
    owner_id: int


@router.get("/users", response_model=List[UserResponse])
def list_all_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_role(Roles.ADMIN)),
    db: Session = Depends(get_db)
):
    """List all users (admin only)"""
    users = db.query(User).offset(skip).limit(limit).all()

    return [
        UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            organization_id=user.organization_id,
            roles=[role.name for role in user.roles]
        )
        for user in users
    ]


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: User = Depends(require_role(Roles.ADMIN)),
    db: Session = Depends(get_db)
):
    """Update user (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user_update.is_active is not None:
        user.is_active = user_update.is_active

    if user_update.is_superuser is not None:
        user.is_superuser = user_update.is_superuser

    if user_update.organization_id is not None:
        user.organization_id = user_update.organization_id

    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        organization_id=user.organization_id,
        roles=[role.name for role in user.roles]
    )


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(require_role(Roles.ADMIN)),
    db: Session = Depends(get_db)
):
    """Delete user (admin only)"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself"
        )

    db.delete(user)
    db.commit()

    return {"status": "deleted", "user_id": user_id}


@router.get("/roles", response_model=List[RoleResponse])
def list_roles(
    current_user: User = Depends(require_role(Roles.ADMIN)),
    db: Session = Depends(get_db)
):
    """List all roles"""
    roles = db.query(Role).all()
    return roles


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    role_data: RoleCreate,
    current_user: User = Depends(require_role(Roles.ADMIN)),
    db: Session = Depends(get_db)
):
    """Create a new role"""
    existing_role = db.query(Role).filter(Role.name == role_data.name).first()

    if existing_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role already exists"
        )

    role = Role(
        name=role_data.name,
        description=role_data.description,
        permissions=role_data.permissions
    )

    db.add(role)
    db.commit()
    db.refresh(role)

    return role


@router.post("/roles/assign")
def assign_role_to_user(
    assign_data: AssignRoleRequest,
    current_user: User = Depends(require_role(Roles.ADMIN)),
    db: Session = Depends(get_db)
):
    """Assign role to user"""
    user = db.query(User).filter(User.id == assign_data.user_id).first()
    role = db.query(Role).filter(Role.id == assign_data.role_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    if role in user.roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has this role"
        )

    user.roles.append(role)
    db.commit()

    return {
        "status": "assigned",
        "user_id": user.id,
        "role_id": role.id,
        "role_name": role.name
    }


@router.delete("/roles/assign")
def remove_role_from_user(
    assign_data: AssignRoleRequest,
    current_user: User = Depends(require_role(Roles.ADMIN)),
    db: Session = Depends(get_db)
):
    """Remove role from user"""
    user = db.query(User).filter(User.id == assign_data.user_id).first()
    role = db.query(Role).filter(Role.id == assign_data.role_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    if role not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User does not have this role"
        )

    user.roles.remove(role)
    db.commit()

    return {
        "status": "removed",
        "user_id": user.id,
        "role_id": role.id
    }


@router.get("/organizations", response_model=List[OrganizationResponse])
def list_organizations(
    current_user: User = Depends(require_role(Roles.ADMIN)),
    db: Session = Depends(get_db)
):
    """List all organizations"""
    orgs = db.query(Organization).all()
    return orgs


@router.post("/organizations", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(
    org_data: OrganizationCreate,
    current_user: User = Depends(require_role(Roles.ADMIN)),
    db: Session = Depends(get_db)
):
    """Create organization"""
    existing_org = db.query(Organization).filter(Organization.name == org_data.name).first()

    if existing_org:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization already exists"
        )

    owner = db.query(User).filter(User.id == org_data.owner_id).first()

    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Owner user not found"
        )

    org = Organization(
        name=org_data.name,
        owner_id=org_data.owner_id
    )

    db.add(org)
    db.commit()
    db.refresh(org)

    return org


@router.post("/init-roles")
def initialize_default_roles(
    current_user: User = Depends(require_role(Roles.ADMIN)),
    db: Session = Depends(get_db)
):
    """Initialize default roles"""
    init_default_roles(db)

    return {
        "status": "initialized",
        "roles": list(DEFAULT_ROLES.keys())
    }