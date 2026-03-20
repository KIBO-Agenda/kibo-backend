import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    SUSPENDED = "suspended"


def default_business_hours() -> dict[str, dict[str, str | bool]]:
    return {
        "monday": {"is_open": True, "open": "08:00", "close": "18:00"},
        "tuesday": {"is_open": True, "open": "08:00", "close": "18:00"},
        "wednesday": {"is_open": True, "open": "08:00", "close": "18:00"},
        "thursday": {"is_open": True, "open": "08:00", "close": "18:00"},
        "friday": {"is_open": True, "open": "08:00", "close": "18:00"},
        "saturday": {"is_open": True, "open": "08:00", "close": "18:00"},
        "sunday": {"is_open": False, "open": "08:00", "close": "18:00"},
    }


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        SAEnum(
            SubscriptionStatus,
            name="subscription_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            create_type=False,
        ),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
    )
    subscription_valid_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    trial_ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    slot_duration: Mapped[int] = mapped_column(
        nullable=False, default=15
    )
    max_users: Mapped[int] = mapped_column(nullable=False, default=5)
    business_hours: Mapped[dict[str, dict[str, str | bool]]] = mapped_column(
        JSONB,
        nullable=False,
        default=default_business_hours,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
