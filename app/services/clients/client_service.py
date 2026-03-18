import uuid

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories.clients import ClientRepository


class ClientService:
    def __init__(self, db: Session) -> None:
        self.client_repo = ClientRepository(db)

    def create_client(self, tenant_id: uuid.UUID, *, name: str, phone: str, notes: str | None = None):
        try:
            return self.client_repo.create(tenant_id=tenant_id, name=name, phone=phone, notes=notes)
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Client phone already exists for this tenant",
            ) from exc

    def get_client(self, tenant_id: uuid.UUID, client_id: uuid.UUID):
        entity = self.client_repo.get_by_id(tenant_id, client_id)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
        return entity

    def list_clients(self, tenant_id: uuid.UUID):
        return self.client_repo.list_by_tenant(tenant_id)

    def update_client(
        self,
        tenant_id: uuid.UUID,
        client_id: uuid.UUID,
        *,
        name: str | None = None,
        phone: str | None = None,
        notes: str | None = None,
    ):
        try:
            entity = self.client_repo.update(
                tenant_id,
                client_id,
                name=name,
                phone=phone,
                notes=notes,
            )
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Client phone already exists for this tenant",
            ) from exc

        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
        return entity

    def delete_client(self, tenant_id: uuid.UUID, client_id: uuid.UUID):
        success = self.client_repo.delete(tenant_id, client_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
