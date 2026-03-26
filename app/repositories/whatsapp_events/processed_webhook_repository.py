import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.whatsapp_events import ProcessedWebhook


class ProcessedWebhookRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def exists(self, *, message_id: str) -> bool:
        stmt = select(ProcessedWebhook.message_id).where(ProcessedWebhook.message_id == message_id)
        return self.db.execute(stmt).first() is not None

    def exists_recent_by_phone(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_phone: str,
        since,
    ) -> bool:
        digits = "".join(ch for ch in (sender_phone or "") if ch.isdigit())
        if not digits:
            return False

        rows = self.db.execute(
            select(ProcessedWebhook.sender_phone)
            .where(
                ProcessedWebhook.tenant_id == tenant_id,
                ProcessedWebhook.processed_at >= since,
            )
            .order_by(ProcessedWebhook.processed_at.desc())
            .limit(200)
        ).scalars().all()

        for candidate in rows:
            candidate_digits = "".join(ch for ch in (candidate or "") if ch.isdigit())
            if not candidate_digits:
                continue
            if digits == candidate_digits or digits.endswith(candidate_digits) or candidate_digits.endswith(digits):
                return True
        return False

    def register(self, *, message_id: str, tenant_id: uuid.UUID, sender_phone: str | None = None) -> bool:
        entity = ProcessedWebhook(message_id=message_id, tenant_id=tenant_id, sender_phone=sender_phone)
        self.db.add(entity)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return False
        return True
