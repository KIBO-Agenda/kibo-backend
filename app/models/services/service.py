import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Service(Base):
    __tablename__ = "services"
    __table_args__ = (Index("idx_services_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    duration: Mapped[int] = mapped_column(nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
