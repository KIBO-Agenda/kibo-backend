import uuid
from datetime import date, datetime, time
from enum import Enum

from sqlalchemy import Date, DateTime, Enum as SAEnum, Index, String, Text, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppointmentStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    ATTENDED = "attended"
    CANCELLED = "cancelled"


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        Index("idx_appointments_tenant", "tenant_id"),
        Index("idx_appointments_date", "appointment_date"),
        Index("idx_appointments_tenant_date", "tenant_id", "appointment_date"),
        Index(
            "idx_prevent_overlap",
            "user_id",
            "appointment_date",
            "time_start",
            "time_end",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_date: Mapped[date] = mapped_column(Date(), nullable=False)
    time_start: Mapped[time] = mapped_column(Time(), nullable=False)
    time_end: Mapped[time] = mapped_column(Time(), nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        SAEnum(
            AppointmentStatus,
            name="appointment_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            create_type=False,
        ),
        nullable=False,
        default=AppointmentStatus.PENDING,
    )
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
