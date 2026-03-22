from datetime import date
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import check_plan_permission
from app.db.session import get_db
from app.models.auth import User
from app.models.tenant import PlanTier
from app.schemas.waitlists import WaitlistCreate, WaitlistResponse
from app.services.waitlists import WaitlistService

router = APIRouter(prefix="/waitlists", tags=["waitlists"])


@router.post("", response_model=WaitlistResponse, status_code=status.HTTP_201_CREATED)
def create_waitlist(
    payload: WaitlistCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(check_plan_permission(PlanTier.PRO))],
):
    service = WaitlistService(db)
    entity = service.create_waitlist(
        current_user.tenant_id,
        client_name=payload.client_name,
        client_phone=payload.client_phone,
        target_date=payload.target_date,
        notes=payload.notes,
    )
    return WaitlistResponse.model_validate(entity)


@router.get("", response_model=list[WaitlistResponse])
def list_waitlists(
    target_date: Annotated[date, Query()],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(check_plan_permission(PlanTier.PRO))],
):
    service = WaitlistService(db)
    entities = service.list_waitlists(current_user.tenant_id, target_date=target_date)
    return [WaitlistResponse.model_validate(entity) for entity in entities]


@router.patch("/{waitlist_id}/resolve", response_model=WaitlistResponse)
def resolve_waitlist(
    waitlist_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(check_plan_permission(PlanTier.PRO))],
):
    service = WaitlistService(db)
    entity = service.resolve_waitlist(current_user.tenant_id, waitlist_id)
    return WaitlistResponse.model_validate(entity)
