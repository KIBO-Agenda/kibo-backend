import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.clients import Client


class ClientRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        phone: str | None = None,
        notes: str | None = None,
    ) -> Client:
        entity = Client(tenant_id=tenant_id, name=name, phone=phone, notes=notes)
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def get_by_id(self, tenant_id: uuid.UUID, client_id: uuid.UUID) -> Client | None:
        stmt = select(Client).where(and_(Client.tenant_id == tenant_id, Client.id == client_id))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_phone(self, tenant_id: uuid.UUID, phone: str) -> Client | None:
        stmt = select(Client).where(and_(Client.tenant_id == tenant_id, Client.phone == phone))
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_name_without_phone(self, tenant_id: uuid.UUID, name: str) -> Client | None:
        normalized_name = name.strip()
        stmt = select(Client).where(
            and_(
                Client.tenant_id == tenant_id,
                Client.phone.is_(None),
                func.lower(Client.name) == normalized_name.lower(),
            )
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_tenant(self, tenant_id: uuid.UUID) -> list[Client]:
        stmt = select(Client).where(Client.tenant_id == tenant_id).order_by(Client.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def update(
        self,
        tenant_id: uuid.UUID,
        client_id: uuid.UUID,
        *,
        name: str | None = None,
        phone: str | None = None,
        notes: str | None = None,
    ) -> Client | None:
        entity = self.get_by_id(tenant_id, client_id)
        if not entity:
            return None

        if name is not None:
            entity.name = name
        if phone is not None:
            entity.phone = phone
        if notes is not None:
            entity.notes = notes

        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, tenant_id: uuid.UUID, client_id: uuid.UUID) -> bool:
        entity = self.get_by_id(tenant_id, client_id)
        if not entity:
            return False
        self.db.delete(entity)
        self.db.commit()
        return True
