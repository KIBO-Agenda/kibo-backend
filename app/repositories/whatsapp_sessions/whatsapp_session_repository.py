import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.whatsapp_sessions import WhatsAppSession


class WhatsAppSessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_latest_by_tenant(self, tenant_id: uuid.UUID) -> WhatsAppSession | None:
        stmt = (
            select(WhatsAppSession)
            .where(WhatsAppSession.tenant_id == tenant_id)
            .order_by(WhatsAppSession.created_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def get_by_tenant_and_instance(self, tenant_id: uuid.UUID, instance_name: str) -> WhatsAppSession | None:
        stmt = (
            select(WhatsAppSession)
            .where(
                WhatsAppSession.tenant_id == tenant_id,
                WhatsAppSession.instance_name == instance_name,
            )
            .order_by(WhatsAppSession.created_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def upsert_status(
        self,
        *,
        tenant_id: uuid.UUID,
        instance_name: str,
        status: str,
        last_seen_at: datetime | None,
    ) -> WhatsAppSession:
        stmt = (
            select(WhatsAppSession)
            .where(
                WhatsAppSession.tenant_id == tenant_id,
                WhatsAppSession.instance_name == instance_name,
            )
            .order_by(WhatsAppSession.created_at.desc())
        )
        entities = self.db.execute(stmt).scalars().all()

        if not entities:
            entity = WhatsAppSession(
                tenant_id=tenant_id,
                instance_name=instance_name,
                status=status,
                last_seen_at=last_seen_at,
            )
            self.db.add(entity)
        else:
            entity = entities[0]
            entity.status = status
            entity.last_seen_at = last_seen_at

            # Self-heal historical duplicates to avoid future crashes.
            for duplicate in entities[1:]:
                self.db.delete(duplicate)

        self.db.commit()
        self.db.refresh(entity)
        return entity
