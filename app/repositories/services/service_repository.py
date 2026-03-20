import uuid

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.services import Service


class ServiceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, *, tenant_id: uuid.UUID, name: str, duration: int, price) -> Service:
        entity = Service(tenant_id=tenant_id, name=name, duration=duration, price=price)
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def get_by_id(self, tenant_id: uuid.UUID, service_id: uuid.UUID) -> Service | None:
        stmt = select(Service).where(and_(Service.tenant_id == tenant_id, Service.id == service_id))
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_tenant(self, tenant_id: uuid.UUID, *, only_active: bool = True) -> list[Service]:
        stmt = select(Service).where(Service.tenant_id == tenant_id)
        if only_active:
            stmt = stmt.where(Service.is_active.is_(True))
        stmt = stmt.order_by(Service.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def update(
        self,
        tenant_id: uuid.UUID,
        service_id: uuid.UUID,
        *,
        name: str | None = None,
        duration: int | None = None,
        price=None,
    ) -> Service | None:
        entity = self.get_by_id(tenant_id, service_id)
        if not entity:
            return None

        if name is not None:
            entity.name = name
        if duration is not None:
            entity.duration = duration
        if price is not None:
            entity.price = price

        self.db.commit()
        self.db.refresh(entity)
        return entity

    def soft_delete(self, tenant_id: uuid.UUID, service_id: uuid.UUID) -> bool:
        entity = self.get_by_id(tenant_id, service_id)
        if not entity:
            return False
        entity.is_active = False
        self.db.commit()
        return True
