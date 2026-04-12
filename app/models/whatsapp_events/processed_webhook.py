from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.schemas import WHATSAPP_SCHEMA


class ProcessedWebhook(Base):
    __tablename__ = "processed_webhooks"
    __table_args__ = {"schema": WHATSAPP_SCHEMA}

    message_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    sender_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    remote_jid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
