import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, case, func, select, update
from sqlalchemy.orm import Session

from app.core.timezone import now_for_timezone
from app.models.appointments import Appointment, AppointmentStatus
from app.models.auth import User
from app.models.clients import Client
from app.models.services import Service
from app.models.tenant import Tenant


def _normalize_digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _phone_variants(digits: str) -> set[str]:
    variants = {digits}
    if digits.startswith("57") and len(digits) > 10:
        variants.add(digits[2:])
    if len(digits) > 10:
        variants.add(digits[-10:])
    if len(digits) == 10 and digits.startswith("3"):
        variants.add(f"57{digits}")
    return {variant for variant in variants if variant}


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

    def list_active_by_user_on_date(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        appointment_date: date,
    ) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.user_id == user_id,
                Appointment.appointment_date == appointment_date,
                Appointment.status != AppointmentStatus.CANCELLED,
            )
            .order_by(Appointment.time_start.asc())
        )
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
        last_notification_type: str | None = None,
        whatsapp_remote_id: str | None = None,
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
        if last_notification_type is not None:
            entity.last_notification_type = last_notification_type
        if whatsapp_remote_id is not None:
            entity.whatsapp_remote_id = whatsapp_remote_id
        if notes is not None:
            entity.notes = notes

        self.db.commit()
        self.db.refresh(entity)
        return entity

    def update_whatsapp_remote_id(
        self,
        *,
        tenant_id: uuid.UUID,
        appointment_id: uuid.UUID,
        whatsapp_remote_id: str,
    ) -> Appointment | None:
        entity = self.get_by_id(tenant_id, appointment_id)
        if not entity:
            return None
        entity.whatsapp_remote_id = whatsapp_remote_id
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
        stmt = (
            select(
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
            )
            .select_from(Appointment)
            .join(
                User,
                and_(
                    User.id == Appointment.user_id,
                    User.tenant_id == Appointment.tenant_id,
                ),
            )
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.appointment_date >= start_date,
                Appointment.appointment_date <= end_date,
                User.is_active.is_(True),
            )
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
        stmt = (
            select(
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
            )
            .select_from(Appointment)
            .join(
                User,
                and_(
                    User.id == Appointment.user_id,
                    User.tenant_id == Appointment.tenant_id,
                ),
            )
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.appointment_date >= start_date,
                Appointment.appointment_date <= end_date,
                User.is_active.is_(True),
            )
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
                Client.phone.label("client_phone"),
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
                User.is_active.is_(True),
            )
            .order_by(Appointment.appointment_date.asc(), Appointment.time_start.asc())
        )

        if user_id is not None:
            stmt = stmt.where(Appointment.user_id == user_id)

        return list(self.db.execute(stmt).all())

    def mark_past_confirmed_as_attended(self, tenant_id: uuid.UUID) -> int:
        """
        Marks all past confirmed appointments as attended.
        
        An appointment is considered past if:
        - Its appointment_date is before today, OR
        - Its appointment_date is today AND its time_end has passed
        
        Returns the number of appointments updated.
        """
        tenant_timezone = self.db.execute(
            select(Tenant.timezone_identifier).where(Tenant.id == tenant_id)
        ).scalar_one_or_none()
        now = now_for_timezone(tenant_timezone)
        today = now.date()
        current_time = now.time()
        
        # Update confirmed appointments from before today
        stmt_past_days = (
            update(Appointment)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.status == AppointmentStatus.CONFIRMED,
                Appointment.appointment_date < today,
            )
            .values(status=AppointmentStatus.ATTENDED)
        )
        result_past_days = self.db.execute(stmt_past_days)

        # Update confirmed appointments from today that have already ended
        stmt_today = (
            update(Appointment)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.status == AppointmentStatus.CONFIRMED,
                Appointment.appointment_date == today,
                Appointment.time_end <= current_time,
            )
            .values(status=AppointmentStatus.ATTENDED)
        )
        result_today = self.db.execute(stmt_today)
        
        self.db.commit()

        past_count = result_past_days.rowcount if hasattr(result_past_days, "rowcount") else 0
        today_count = result_today.rowcount if hasattr(result_today, "rowcount") else 0
        total_updated = past_count + today_count
        return total_updated

    def get_nearest_pending_by_client_phone(
        self,
        *,
        tenant_id: uuid.UUID,
        phone: str,
        now: datetime,
    ) -> Appointment | None:
        """Return nearest pending appointment for a sender phone."""
        sender_digits = _normalize_digits(phone)
        if not sender_digits:
            return None

        sender_variants = _phone_variants(sender_digits)

        def _is_same_phone(client_phone: str | None) -> bool:
            client_digits = _normalize_digits(client_phone)
            if not client_digits:
                return False
            client_variants = _phone_variants(client_digits)
            return bool(sender_variants & client_variants)

        base_stmt = (
            select(Appointment, Client.phone.label("client_phone"))
            .join(
                Client,
                and_(
                    Client.id == Appointment.client_id,
                    Client.tenant_id == Appointment.tenant_id,
                ),
            )
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.status == AppointmentStatus.PENDING,
            )
        )

        upcoming_rows = self.db.execute(
            base_stmt
            .where(
                (Appointment.appointment_date > now.date())
                | (
                    (Appointment.appointment_date == now.date())
                    & (Appointment.time_start >= now.time())
                )
            )
            .order_by(Appointment.appointment_date.asc(), Appointment.time_start.asc())
            .limit(300)
        ).all()

        for appointment, client_phone in upcoming_rows:
            if _is_same_phone(client_phone):
                return appointment

        recent_rows = self.db.execute(
            base_stmt
            .order_by(Appointment.appointment_date.desc(), Appointment.time_start.desc())
            .limit(300)
        ).all()

        for appointment, client_phone in recent_rows:
            if _is_same_phone(client_phone):
                return appointment

        return None

    def has_pending_in_next_hours_by_client_phone(
        self,
        *,
        tenant_id: uuid.UUID,
        phone: str,
        now: datetime,
        hours: int,
    ) -> bool:
        sender_digits = _normalize_digits(phone)
        if not sender_digits:
            return False

        sender_variants = _phone_variants(sender_digits)

        now_naive = now.replace(tzinfo=None)
        end_window = now_naive + timedelta(hours=hours)

        rows = self.db.execute(
            select(Appointment, Client.phone.label("client_phone"))
            .join(
                Client,
                and_(
                    Client.id == Appointment.client_id,
                    Client.tenant_id == Appointment.tenant_id,
                ),
            )
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.status == AppointmentStatus.PENDING,
            )
            .order_by(Appointment.appointment_date.asc(), Appointment.time_start.asc())
            .limit(200)
        ).all()

        for appointment, client_phone in rows:
            client_digits = _normalize_digits(client_phone)
            if not client_digits:
                continue
            client_variants = _phone_variants(client_digits)
            if not (sender_variants & client_variants):
                continue

            appt_dt = datetime.combine(appointment.appointment_date, appointment.time_start)
            if now_naive <= appt_dt <= end_window:
                return True

        return False

    def get_nearest_pending_by_remote_id(
        self,
        *,
        tenant_id: uuid.UUID,
        remote_id: str,
        now: datetime,
    ) -> Appointment | None:
        stmt = (
            select(Appointment)
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.status == AppointmentStatus.PENDING,
                Appointment.whatsapp_remote_id == remote_id,
            )
            .order_by(Appointment.appointment_date.asc(), Appointment.time_start.asc())
            .limit(50)
        )
        upcoming = self.db.execute(
            stmt.where(
                (Appointment.appointment_date > now.date())
                | (
                    (Appointment.appointment_date == now.date())
                    & (Appointment.time_start >= now.time())
                )
            )
        ).scalars().first()
        if upcoming:
            return upcoming

        recent = self.db.execute(
            stmt
            .order_by(Appointment.appointment_date.desc(), Appointment.time_start.desc())
            .limit(50)
        ).scalars().first()
        return recent

    def get_by_id_with_relations(
        self,
        *,
        tenant_id: uuid.UUID,
        appointment_id: uuid.UUID,
    ):
        stmt = (
            select(
                Appointment,
                Client.name.label("client_name"),
                Client.phone.label("client_phone"),
                Service.name.label("service_name"),
                User.name.label("staff_name"),
            )
            .join(
                Client,
                and_(
                    Client.id == Appointment.client_id,
                    Client.tenant_id == Appointment.tenant_id,
                ),
            )
            .join(
                Service,
                and_(
                    Service.id == Appointment.service_id,
                    Service.tenant_id == Appointment.tenant_id,
                ),
            )
            .join(
                User,
                and_(
                    User.id == Appointment.user_id,
                    User.tenant_id == Appointment.tenant_id,
                ),
            )
            .where(
                Appointment.tenant_id == tenant_id,
                Appointment.id == appointment_id,
            )
            .limit(1)
        )
        return self.db.execute(stmt).first()
