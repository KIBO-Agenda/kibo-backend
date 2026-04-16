import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_tenant_user, require_owner
from app.db.session import get_db
from app.models.auth import User
from app.schemas.services import ServiceCreate, ServiceResponse, ServiceUpdate
from app.services.services import ServiceService

router = APIRouter(prefix="/services", tags=["services"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_service(
    payload: ServiceCreate,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = ServiceService(db)
    entity = service.create_service(
        owner_user.tenant_id,
        name=payload.name,
        duration=payload.duration,
        price=payload.price,
    )
    return ServiceResponse.model_validate(entity)


@router.get("/{service_id}")
def get_service(
    service_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = ServiceService(db)
    entity = service.get_service(current_user.tenant_id, service_id)
    return ServiceResponse.model_validate(entity)


@router.get("")
def list_services(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = ServiceService(db)
    entities = service.list_services(current_user.tenant_id)
    return [ServiceResponse.model_validate(entity) for entity in entities]


@router.patch("/{service_id}")
def update_service(
    service_id: uuid.UUID,
    payload: ServiceUpdate,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = ServiceService(db)
    entity = service.update_service(
        owner_user.tenant_id,
        service_id,
        name=payload.name,
        duration=payload.duration,
        price=payload.price,
    )
    return ServiceResponse.model_validate(entity)


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete_service(
    service_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = ServiceService(db)
    service.soft_delete_service(owner_user.tenant_id, service_id)
