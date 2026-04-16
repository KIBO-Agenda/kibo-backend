import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.whatsapp_outbox import WhatsAppOutbox


class WhatsAppOutboxRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        business_id: uuid.UUID,
        phone: str,
        message_type: str,
        rendered_text: str,
        idempotency_key: str,
        template_variant_index: int | None = None,
        client_id: uuid.UUID | None = None,
        appointment_id: uuid.UUID | None = None,
        variables: dict | None = None,
    ) -> WhatsAppOutbox:
        entity = WhatsAppOutbox(
            business_id=business_id,
            client_id=client_id,
            appointment_id=appointment_id,
            phone=phone,
            message_type=message_type,
            template_variant_index=template_variant_index,
            rendered_text=rendered_text,
            variables=variables or {},
            idempotency_key=idempotency_key,
            status="pending",
        )
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def claim_pending_batch(self, *, now: datetime, limit: int) -> list[WhatsAppOutbox]:
        stmt = (
            select(WhatsAppOutbox)
            .where(
                WhatsAppOutbox.status == "pending",
                WhatsAppOutbox.next_attempt_at <= now,
            )
            .order_by(WhatsAppOutbox.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list(self.db.execute(stmt).scalars().all())
        if not rows:
            return []

        for row in rows:
            row.status = "processing"

        self.db.commit()
        for row in rows:
            self.db.refresh(row)
        return rows

    def mark_sent(
        self,
        *,
        message_id: uuid.UUID,
        sent_at: datetime,
        provider_message_id: str | None,
        provider_payload: dict | None,
    ) -> None:
        entity = self.db.get(WhatsAppOutbox, message_id)
        if not entity:
            return

        entity.status = "sent"
        entity.sent_at = sent_at
        entity.provider_message_id = provider_message_id
        entity.provider_payload = provider_payload
        entity.error_message = None
        self.db.commit()

    def mark_blocked_opt_out(self, *, message_id: uuid.UUID, error_message: str) -> None:
        entity = self.db.get(WhatsAppOutbox, message_id)
        if not entity:
            return

        entity.status = "blocked_opt_out"
        entity.error_message = error_message
        self.db.commit()

    def retry_or_fail(
        self,
        *,
        message_id: uuid.UUID,
        now: datetime,
        error_message: str,
        max_attempts: int,
        base_delay_seconds: int,
    ) -> None:
        entity = self.db.get(WhatsAppOutbox, message_id)
        if not entity:
            return

        next_attempts = entity.attempts + 1
        entity.attempts = next_attempts
        entity.error_message = error_message

        if next_attempts >= max_attempts:
            entity.status = "failed"
        else:
            entity.status = "pending"
            backoff = base_delay_seconds * next_attempts
            entity.next_attempt_at = now + timedelta(seconds=backoff)

        self.db.commit()

    def count_by_status(self, *, business_id: uuid.UUID) -> dict[str, int]:
        stmt = select(WhatsAppOutbox.status)
        stmt = stmt.where(WhatsAppOutbox.business_id == business_id)
        rows = list(self.db.execute(stmt).scalars().all())

        counters = {"pending": 0, "processing": 0, "sent": 0, "failed": 0, "blocked_opt_out": 0}
        for status in rows:
            if status in counters:
                counters[status] += 1
        return counters

    def list_recent(self, *, business_id: uuid.UUID, limit: int = 50) -> list[WhatsAppOutbox]:
        stmt = (
            select(WhatsAppOutbox)
            .where(WhatsAppOutbox.business_id == business_id)
            .order_by(WhatsAppOutbox.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars().all())

    def has_recent_message(
        self,
        *,
        business_id: uuid.UUID,
        phone: str,
        message_type: str,
        since: datetime,
    ) -> bool:
        digits = "".join(ch for ch in (phone or "") if ch.isdigit())
        if not digits:
            return False

        rows = (
            self.db.execute(
                select(WhatsAppOutbox.phone)
                .where(
                    WhatsAppOutbox.business_id == business_id,
                    WhatsAppOutbox.message_type == message_type,
                    WhatsAppOutbox.created_at >= since,
                )
                .order_by(WhatsAppOutbox.created_at.desc())
                .limit(200)
            )
            .scalars()
            .all()
        )

        for candidate in rows:
            candidate_digits = "".join(ch for ch in (candidate or "") if ch.isdigit())
            if not candidate_digits:
                continue
            if digits == candidate_digits or digits.endswith(candidate_digits) or candidate_digits.endswith(digits):
                return True
        return False

    def reset_for_retry(self, *, business_id: uuid.UUID, message_id: uuid.UUID, now: datetime) -> WhatsAppOutbox | None:
        entity = self.db.get(WhatsAppOutbox, message_id)
        if not entity or entity.business_id != business_id:
            return None

        entity.status = "pending"
        entity.error_message = None
        entity.next_attempt_at = now
        self.db.commit()
        self.db.refresh(entity)
        return entity
