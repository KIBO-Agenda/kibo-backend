from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.dependencies import get_super_admin_id_from_token
from app.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate
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
    )
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
    )
    return TenantResponse.model_validate(tenant)
