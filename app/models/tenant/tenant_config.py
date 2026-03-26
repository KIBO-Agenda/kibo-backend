import uuid

from sqlalchemy import Boolean, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TenantConfig(Base):
    __tablename__ = "tenant_configs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    waitlist_manual_approval: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, server_default=text("true")
    )
    whatsapp_enabled: Mapped[bool] = mapped_column(
        Boolean(), nullable=False, server_default=text("true")
    )
