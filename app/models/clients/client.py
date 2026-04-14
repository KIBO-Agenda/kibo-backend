import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        Index("idx_clients_tenant", "tenant_id"),
        Index("idx_clients_phone", "phone"),
        Index("idx_clients_tenant_whatsapp_lid", "tenant_id", "whatsapp_lid"),
        UniqueConstraint("tenant_id", "phone", name="idx_clients_tenant_phone_unique"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    whatsapp_lid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    whatsapp_opt_out: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, server_default=text("false")
    )
    whatsapp_opt_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
