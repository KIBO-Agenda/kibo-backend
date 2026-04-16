import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.schemas import WHATSAPP_SCHEMA


class WhatsAppOutbox(Base):
    __tablename__ = "whatsapp_outbox"
    __table_args__ = (
        Index("idx_whatsapp_outbox_status_next_attempt", "status", "next_attempt_at"),
        Index("idx_whatsapp_outbox_business_created", "business_id", "created_at"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'sent', 'failed', 'blocked_opt_out')",
            name="ck_whatsapp_outbox_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_whatsapp_outbox_attempts_non_negative"),
        CheckConstraint("jitter_seconds >= 0", name="ck_whatsapp_outbox_jitter_non_negative"),
        {"schema": WHATSAPP_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    template_variant_index: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    rendered_text: Mapped[str] = mapped_column(Text(), nullable=False)
    variables: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    provider_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    jitter_seconds: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
