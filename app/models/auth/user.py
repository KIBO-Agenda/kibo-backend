import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(str, Enum):
    OWNER = "owner"
    STAFF = "staff"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("idx_users_tenant", "tenant_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            create_constraint=False,
            create_type=False,
        ),
        nullable=False,
        default=UserRole.STAFF,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
