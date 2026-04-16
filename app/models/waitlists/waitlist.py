import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Waitlist(Base):
    __tablename__ = "waitlists"
    __table_args__ = (
        Index("idx_waitlists_tenant", "tenant_id"),
        Index("idx_waitlists_target_date", "target_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_date: Mapped[date] = mapped_column(Date(), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
