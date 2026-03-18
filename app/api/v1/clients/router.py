from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_tenant_user
from app.db.session import get_db
from app.models.auth import User
from app.schemas.clients import ClientCreate, ClientResponse, ClientUpdate
from app.services.clients import ClientService

router = APIRouter(prefix="/clients", tags=["clients"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = ClientService(db)
    entity = service.create_client(
        current_user.tenant_id,
        name=payload.name,
        phone=payload.phone,
        notes=payload.notes,
    )
    return ClientResponse.model_validate(entity)


@router.get("/{client_id}")
def get_client(
    client_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = ClientService(db)
    entity = service.get_client(current_user.tenant_id, client_id)
    return ClientResponse.model_validate(entity)


@router.get("")
def list_clients(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = ClientService(db)
    entities = service.list_clients(current_user.tenant_id)
    return [ClientResponse.model_validate(entity) for entity in entities]


@router.patch("/{client_id}")
def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = ClientService(db)
    entity = service.update_client(
        current_user.tenant_id,
        client_id,
        name=payload.name,
        phone=payload.phone,
        notes=payload.notes,
    )
    return ClientResponse.model_validate(entity)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(
    client_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_tenant_user)],
):
    service = ClientService(db)
    service.delete_client(current_user.tenant_id, client_id)
