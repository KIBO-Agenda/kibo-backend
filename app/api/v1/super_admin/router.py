from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.super_admin import SuperAdminCreate, SuperAdminResponse
from app.services.super_admin.super_admin_service import SuperAdminService

router = APIRouter(prefix="/super-admins", tags=["super_admin"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_super_admin(
    payload: SuperAdminCreate,
    db: Annotated[Session, Depends(get_db)],
):
    service = SuperAdminService(db)
    entity = service.create_super_admin(payload)
    return SuperAdminResponse.model_validate(entity)


@router.get("")
def list_super_admins(
    db: Annotated[Session, Depends(get_db)],
):
    service = SuperAdminService(db)
    entities = service.list_super_admins()
    return [SuperAdminResponse.model_validate(entity) for entity in entities]
