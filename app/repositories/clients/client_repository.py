import uuid
from datetime import datetime

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

    @staticmethod
    def _normalize_phone(phone: str | None) -> str:
        return "".join(ch for ch in (phone or "") if ch.isdigit())

    def get_by_phone_normalized(self, tenant_id: uuid.UUID, phone: str) -> Client | None:
        target = self._normalize_phone(phone)
        if not target:
            return None

        exact = self.get_by_phone(tenant_id, phone)
        if exact:
            return exact

        candidates = self.list_by_tenant(tenant_id)
        for candidate in candidates:
            if self._normalize_phone(candidate.phone) == target:
                return candidate
        return None

    def set_whatsapp_opt_out(self, tenant_id: uuid.UUID, client_id: uuid.UUID, *, at: datetime) -> Client | None:
        entity = self.get_by_id(tenant_id, client_id)
        if not entity:
            return None
        entity.whatsapp_opt_out = True
        entity.whatsapp_opt_out_at = at
        self.db.commit()
        self.db.refresh(entity)
        return entity

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
        whatsapp_lid: str | None = None,
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
        if whatsapp_lid is not None:
            entity.whatsapp_lid = whatsapp_lid

        self.db.commit()
        self.db.refresh(entity)
        return entity

    def get_by_whatsapp_lid(self, tenant_id: uuid.UUID, whatsapp_lid: str) -> Client | None:
        stmt = select(Client).where(
            and_(
                Client.tenant_id == tenant_id,
                Client.whatsapp_lid == whatsapp_lid,
            )
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def delete(self, tenant_id: uuid.UUID, client_id: uuid.UUID) -> bool:
        entity = self.get_by_id(tenant_id, client_id)
        if not entity:
            return False
        self.db.delete(entity)
        self.db.commit()
        return True
