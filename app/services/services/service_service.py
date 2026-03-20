import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.services import ServiceRepository


class ServiceService:
    def __init__(self, db: Session) -> None:
        self.service_repo = ServiceRepository(db)

    def create_service(self, tenant_id: uuid.UUID, *, name: str, duration: int, price):
        return self.service_repo.create(
            tenant_id=tenant_id,
            name=name,
            duration=duration,
            price=price,
        )

    def get_service(self, tenant_id: uuid.UUID, service_id: uuid.UUID):
        entity = self.service_repo.get_by_id(tenant_id, service_id)
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        return entity

    def list_services(self, tenant_id: uuid.UUID):
        return self.service_repo.list_by_tenant(tenant_id, only_active=True)

    def update_service(
        self,
        tenant_id: uuid.UUID,
        service_id: uuid.UUID,
        *,
        name: str | None = None,
        duration: int | None = None,
        price=None,
    ):
        entity = self.service_repo.update(
            tenant_id,
            service_id,
            name=name,
            duration=duration,
            price=price,
        )
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
        return entity

    def soft_delete_service(self, tenant_id: uuid.UUID, service_id: uuid.UUID):
        success = self.service_repo.soft_delete(tenant_id, service_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
