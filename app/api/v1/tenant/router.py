from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import check_plan_permission, has_min_plan_tier, require_owner
from app.db.session import get_db
from app.core.dependencies import get_super_admin_id_from_token
from app.models.auth import User
from app.models.tenant import PlanTier
from app.schemas.tenant import (
    AssignPlanRequest,
    MessageTemplates,
    TenantCreate,
    TenantResponse,
    TenantSettingsUpdate,
    TenantUpdate,
)
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
        plan_tier=payload.plan_tier,
        slot_duration=payload.slot_duration,
        max_users=payload.max_users,
        timezone_identifier=payload.timezone_identifier,
    )
    return TenantResponse.model_validate(tenant)


@router.patch("/settings")
def update_tenant_settings(
    payload: TenantSettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = TenantService(db)
    tenant = service.get_owner_settings(owner_user.tenant_id)
    if payload.message_templates is not None and not has_min_plan_tier(tenant.plan_tier, PlanTier.PRO):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="This feature is available in the pro plan. Please upgrade to continue.",
        )

    tenant = service.update_owner_settings(
        owner_user.tenant_id,
        name=payload.name,
        phone=payload.phone,
        slot_duration=payload.slot_duration,
        timezone_identifier=payload.timezone_identifier,
        business_hours=payload.business_hours,
        message_templates=payload.message_templates,
    )
    return TenantResponse.model_validate(tenant)


@router.patch("/assign-plan", response_model=TenantResponse)
def assign_plan(
    payload: AssignPlanRequest,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    """Assign plan tier to tenant (owner only, typically after registration)."""
    service = TenantService(db)
    tenant = service.assign_plan(owner_user.tenant_id, plan_tier=payload.plan_tier)
    return TenantResponse.model_validate(tenant)


@router.get("/settings", response_model=TenantResponse)
def get_tenant_settings(
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = TenantService(db)
    tenant = service.get_owner_settings(owner_user.tenant_id)
    return TenantResponse.model_validate(tenant)


@router.get(
    "/settings/message-templates",
    response_model=MessageTemplates,
)
def get_message_templates(
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
    __: Annotated[User, Depends(check_plan_permission(PlanTier.PRO))],
):
    service = TenantService(db)
    tenant = service.get_owner_settings(owner_user.tenant_id)
    return MessageTemplates.model_validate(getattr(tenant, "message_templates", {}))


@router.patch(
    "/settings/message-templates",
    response_model=MessageTemplates,
)
def update_message_templates(
    payload: MessageTemplates,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
    __: Annotated[User, Depends(check_plan_permission(PlanTier.PRO))],
):
    service = TenantService(db)
    tenant = service.update_owner_settings(
        owner_user.tenant_id,
        message_templates=payload,
    )
    return MessageTemplates.model_validate(getattr(tenant, "message_templates", {}))


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
        plan_tier=payload.plan_tier,
        slot_duration=payload.slot_duration,
        max_users=payload.max_users,
        timezone_identifier=payload.timezone_identifier,
        business_hours=payload.business_hours,
        message_templates=payload.message_templates,
    )
    return TenantResponse.model_validate(tenant)
