import uuid
from datetime import date, time

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.models.appointments import Appointment, AppointmentStatus
from app.models.auth import User
from app.models.clients import Client
from app.models.services import Service


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

    def get_agenda_summary(
        self,
        *,
        tenant_id: uuid.UUID,
        start_date: date,
        end_date: date,
        user_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        stmt = select(
            func.count(Appointment.id).label("total"),
            func.coalesce(
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.CONFIRMED, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("confirmed"),
            func.coalesce(
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.PENDING, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("pending"),
            func.coalesce(
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.CANCELLED, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("cancelled"),
            func.coalesce(
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.ATTENDED, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("attended"),
        ).where(
            Appointment.tenant_id == tenant_id,
            Appointment.appointment_date >= start_date,
            Appointment.appointment_date <= end_date,
        )

        if user_id is not None:
            stmt = stmt.where(Appointment.user_id == user_id)

        row = self.db.execute(stmt).one()
        return {
            "total": int(row.total or 0),
            "confirmed": int(row.confirmed or 0),
            "pending": int(row.pending or 0),
            "cancelled": int(row.cancelled or 0),
            "attended": int(row.attended or 0),
        }

    def get_weekly_summary(
        self,
        *,
        tenant_id: uuid.UUID,
        start_date: date,
        end_date: date,
        user_id: uuid.UUID | None = None,
    ) -> dict[str, int]:
        stmt = select(
            func.count(Appointment.id).label("total"),
            func.coalesce(
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.CONFIRMED, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("confirmed"),
            func.coalesce(
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.PENDING, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("pending"),
            func.coalesce(
                func.sum(
                    case(
                        (Appointment.status == AppointmentStatus.CANCELLED, 1),
                        else_=0,
                    )
                ),
                0,
            ).label("cancelled"),
        ).where(
            Appointment.tenant_id == tenant_id,
            Appointment.appointment_date >= start_date,
            Appointment.appointment_date <= end_date,
        )

        if user_id is not None:
            stmt = stmt.where(Appointment.user_id == user_id)

        row = self.db.execute(stmt).one()
        return {
            "total": int(row.total or 0),
            "confirmed": int(row.confirmed or 0),
            "pending": int(row.pending or 0),
            "cancelled": int(row.cancelled or 0),
        }

    def list_agenda_appointments(
        self,
        *,
        tenant_id: uuid.UUID,
        start_date: date,
        end_date: date,
        user_id: uuid.UUID | None = None,
    ):
        stmt = (
            select(
                Appointment.id.label("id"),
                Appointment.appointment_date.label("appointment_date"),
                Appointment.time_start.label("time_start"),
                Appointment.time_end.label("time_end"),
                Client.name.label("client_name"),
                Appointment.status.label("status"),
                User.name.label("staff_name"),
                Service.name.label("service_name"),
            )
            .select_from(Appointment)
            .join(
                Client,
                and_(
                    Client.id == Appointment.client_id,
                    Client.tenant_id == Appointment.tenant_id,
                ),
            )
            .join(
                User,
                and_(
                    User.id == Appointment.user_id,
                    User.tenant_id == Appointment.tenant_id,
                ),
            )
            .join(
                Service,
                and_(
                    Service.id == Appointment.service_id,
                    Service.tenant_id == Appointment.tenant_id,
                ),
            )
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.appointment_date >= start_date,
                Appointment.appointment_date <= end_date,
            )
            .order_by(Appointment.appointment_date.asc(), Appointment.time_start.asc())
        )

        if user_id is not None:
            stmt = stmt.where(Appointment.user_id == user_id)

        return list(self.db.execute(stmt).all())
