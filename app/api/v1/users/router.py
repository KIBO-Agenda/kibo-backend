from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.dependencies import get_tenant_id_from_token, require_owner
from app.schemas.users import (
    UserActivationResponse,
    UserCreate,
    UserResponse,
    UserStaffCreate,
    UserUpdate,
)
from app.services.users import UserService
from app.models.auth import User

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    """Create user in tenant (owner only)."""
    service = UserService(db)
    user = service.create_user(
        owner_user.tenant_id,
        email=payload.email,
        name=payload.name,
        password=payload.password,
        role=payload.role,
    )
    return UserResponse.model_validate(user)


@router.post("/staff", status_code=status.HTTP_201_CREATED)
def create_staff_user(
    payload: UserStaffCreate,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = UserService(db)
    user = service.create_staff_user(
        owner_user.tenant_id,
        email=payload.email,
        name=payload.name,
        password=payload.password,
    )
    return UserResponse.model_validate(user)


@router.patch("/{user_id}/activate", response_model=UserActivationResponse)
def activate_staff_user(
    user_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = UserService(db)
    user = service.activate_staff_user(owner_user.tenant_id, user_id)
    return UserActivationResponse.model_validate(user)


@router.get("/{user_id}")
def get_user(
    user_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant_id_str: Annotated[str, Depends(get_tenant_id_from_token)],
):
    """Get user details (multi-tenant enforced)."""
    tenant_id = uuid.UUID(tenant_id_str)
    
    service = UserService(db)
    user = service.get_user(tenant_id, user_id)
    return UserResponse.model_validate(user)


@router.get("")
def list_users(
    db: Annotated[Session, Depends(get_db)],
    tenant_id_str: Annotated[str, Depends(get_tenant_id_from_token)],
):
    """List users in tenant."""
    tenant_id = uuid.UUID(tenant_id_str)
    
    service = UserService(db)
    users = service.list_users(tenant_id)
    return [UserResponse.model_validate(u) for u in users]


@router.patch("/{user_id}")
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
    tenant_id_str: Annotated[str, Depends(get_tenant_id_from_token)],
):
    """Update user (multi-tenant enforced)."""
    tenant_id = uuid.UUID(tenant_id_str)
    
    service = UserService(db)
    user = service.update_user(
        tenant_id,
        user_id,
        name=payload.name,
        role=payload.role,
        is_active=payload.is_active,
    )
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    tenant_id_str: Annotated[str, Depends(get_tenant_id_from_token)],
):
    """Delete (soft) user (multi-tenant enforced)."""
    tenant_id = uuid.UUID(tenant_id_str)
    
    service = UserService(db)
    service.delete_user(tenant_id, user_id)
