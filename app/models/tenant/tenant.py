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


class PlanTier(str, Enum):
    STARTER = "starter"
    PRO = "pro"
    BUSINESS = "business"


PLAN_MAX_USERS: dict[PlanTier, int] = {
    PlanTier.STARTER: 2,
    PlanTier.PRO: 6,
    PlanTier.BUSINESS: 99,
}


def max_users_for_plan(plan_tier: PlanTier) -> int:
    return PLAN_MAX_USERS[plan_tier]


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


def default_message_templates() -> dict[str, object]:
    return {
        "reminder_24h": {
            "enabled": True,
            "variants": [
                "Hola {nombre}, soy Kibo, el asistente de {negocio}. Te recuerdo tu cita para {servicio} manana a las {hora}. Responde: 1 para Confirmar, 2 para Cancelar o 3 para Reagendar.",
            ],
        },
        "reminder_2h": {
            "enabled": True,
            "variants": [
                "Hola {nombre}, soy Kibo. Tu cita para {servicio} es hoy a las {hora}. Responde 1 para Confirmar, 2 para Cancelar o 3 para Reagendar.",
            ],
        },
        "welcome_message": {
            "enabled": True,
            "variants": [
                "Hola {nombre}, gracias por agendar en {negocio}.",
            ],
        },
        "waitlist_notification": {
            "enabled": True,
            "variants": [
                "Hola {nombre}, se libero un cupo a las {hora_disponible}. Responde SI para continuar.",
            ],
        },
        "waitlist_manual_approval": True,
    }


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plan_tier: Mapped[PlanTier] = mapped_column(
        SAEnum(
            PlanTier,
            name="plan_tier",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            create_type=False,
        ),
        nullable=False,
        default=PlanTier.STARTER,
        server_default=PlanTier.STARTER.value,
    )
    timezone_identifier: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="America/Bogota"
    )
    whatsapp_instance_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
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
    max_users: Mapped[int] = mapped_column(
        nullable=False,
        default=max_users_for_plan(PlanTier.STARTER),
    )
    business_hours: Mapped[dict[str, dict[str, str | bool]]] = mapped_column(
        JSONB,
        nullable=False,
        default=default_business_hours,
    )
    message_templates: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=default_message_templates,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
