from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import require_owner
from app.db.session import get_db
from app.core.dependencies import get_super_admin_id_from_token
from app.models.auth import User
from app.schemas.tenant import TenantCreate, TenantResponse, TenantSettingsUpdate, TenantUpdate
from app.services.tenant import TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_super_admin_id_from_token)],
):
    """Create new tenant (super_admin only)."""
    service = TenantService(db)
    tenant = service.create_tenant(
        name=payload.name,
        phone=payload.phone,
        slot_duration=payload.slot_duration,
        max_users=payload.max_users,
    )
    return TenantResponse.model_validate(tenant)


@router.patch("/settings")
def update_tenant_settings(
    payload: TenantSettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = TenantService(db)
    tenant = service.update_owner_settings(
        owner_user.tenant_id,
        name=payload.name,
        phone=payload.phone,
        slot_duration=payload.slot_duration,
        business_hours=payload.business_hours,
    )
    return TenantResponse.model_validate(tenant)


@router.get("/settings", response_model=TenantResponse)
def get_tenant_settings(
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = TenantService(db)
    tenant = service.get_owner_settings(owner_user.tenant_id)
    return TenantResponse.model_validate(tenant)


@router.get("/{tenant_id}")
def get_tenant(
    tenant_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_super_admin_id_from_token)],
):
    """Get tenant details (super_admin only)."""
    service = TenantService(db)
    tenant = service.get_tenant(tenant_id)
    return TenantResponse.model_validate(tenant)


@router.get("")
def list_tenants(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_super_admin_id_from_token)],
):
    """List all tenants (super_admin only)."""
    service = TenantService(db)
    tenants = service.list_tenants()
    return [TenantResponse.model_validate(t) for t in tenants]


@router.patch("/{tenant_id}")
def update_tenant(
    tenant_id: uuid.UUID,
    payload: TenantUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[str, Depends(get_super_admin_id_from_token)],
):
    """Update tenant (super_admin only)."""
    service = TenantService(db)
    tenant = service.update_tenant(
        tenant_id,
        name=payload.name,
        phone=payload.phone,
        slot_duration=payload.slot_duration,
        max_users=payload.max_users,
        business_hours=payload.business_hours,
    )
    return TenantResponse.model_validate(tenant)
