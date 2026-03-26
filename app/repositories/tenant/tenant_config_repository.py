import uuid

from sqlalchemy.orm import Session

from app.models.tenant import TenantConfig


class TenantConfigRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create(self, *, tenant_id: uuid.UUID) -> TenantConfig:
        entity = self.db.get(TenantConfig, tenant_id)
        if entity:
            return entity

        entity = TenantConfig(tenant_id=tenant_id)
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity
