import uuid
from datetime import date, time

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.appointments import Appointment, AppointmentStatus


class AppointmentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        tenant_id: uuid.UUID,
        client_id: uuid.UUID,
        user_id: uuid.UUID,
        service_id: uuid.UUID,
        appointment_date: date,
        time_start: time,
        time_end: time,
        notes: str | None = None,
    ) -> Appointment:
        entity = Appointment(
            tenant_id=tenant_id,
            client_id=client_id,
            user_id=user_id,
            service_id=service_id,
            appointment_date=appointment_date,
            time_start=time_start,
            time_end=time_end,
            notes=notes,
            status=AppointmentStatus.PENDING,
        )
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def get_by_id(self, tenant_id: uuid.UUID, appointment_id: uuid.UUID) -> Appointment | None:
        stmt = select(Appointment).where(
            and_(Appointment.tenant_id == tenant_id, Appointment.id == appointment_id)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_by_tenant(self, tenant_id: uuid.UUID, *, appointment_date: date | None = None) -> list[Appointment]:
        stmt = select(Appointment).where(Appointment.tenant_id == tenant_id)
        if appointment_date is not None:
            stmt = stmt.where(Appointment.appointment_date == appointment_date)
        stmt = stmt.order_by(Appointment.appointment_date.desc(), Appointment.time_start.asc())
        return list(self.db.execute(stmt).scalars().all())

    def list_by_user(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        appointment_date: date | None = None,
    ) -> list[Appointment]:
        stmt = select(Appointment).where(
            and_(Appointment.tenant_id == tenant_id, Appointment.user_id == user_id)
        )
        if appointment_date is not None:
            stmt = stmt.where(Appointment.appointment_date == appointment_date)
        stmt = stmt.order_by(Appointment.appointment_date.desc(), Appointment.time_start.asc())
        return list(self.db.execute(stmt).scalars().all())

    def has_overlap(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        appointment_date: date,
        time_start: time,
        time_end: time,
        exclude_appointment_id: uuid.UUID | None = None,
    ) -> bool:
        stmt = select(Appointment.id).where(
            Appointment.tenant_id == tenant_id,
            Appointment.user_id == user_id,
            Appointment.appointment_date == appointment_date,
            Appointment.status != AppointmentStatus.CANCELLED,
            Appointment.time_start < time_end,
            Appointment.time_end > time_start,
        )
        if exclude_appointment_id is not None:
            stmt = stmt.where(Appointment.id != exclude_appointment_id)
        return self.db.execute(stmt).first() is not None

    def update(
        self,
        tenant_id: uuid.UUID,
        appointment_id: uuid.UUID,
        *,
        client_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        service_id: uuid.UUID | None = None,
        appointment_date: date | None = None,
        time_start: time | None = None,
        time_end: time | None = None,
        status: AppointmentStatus | None = None,
        notes: str | None = None,
    ) -> Appointment | None:
        entity = self.get_by_id(tenant_id, appointment_id)
        if not entity:
            return None

        if client_id is not None:
            entity.client_id = client_id
        if user_id is not None:
            entity.user_id = user_id
        if service_id is not None:
            entity.service_id = service_id
        if appointment_date is not None:
            entity.appointment_date = appointment_date
        if time_start is not None:
            entity.time_start = time_start
        if time_end is not None:
            entity.time_end = time_end
        if status is not None:
            entity.status = status
        if notes is not None:
            entity.notes = notes

        self.db.commit()
        self.db.refresh(entity)
        return entity

    def cancel(self, tenant_id: uuid.UUID, appointment_id: uuid.UUID) -> bool:
        entity = self.get_by_id(tenant_id, appointment_id)
        if not entity:
            return False
        entity.status = AppointmentStatus.CANCELLED
        self.db.commit()
        return True
