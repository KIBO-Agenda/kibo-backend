from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.timezone import now_for_timezone, today_for_timezone
from app.models.auth import UserRole
from app.repositories.appointments import AppointmentRepository
from app.repositories.tenant import TenantRepository
from app.repositories.users import UserRepository
from app.services.whatsapp.template_engine import resolve_variables


class WhatsAppVariableResolver:
    """Resolve template variables for outbound WhatsApp messages."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.tenant_repo = TenantRepository(db)
        self.user_repo = UserRepository(db)
        self.appointment_repo = AppointmentRepository(db)

    def resolve(
        self,
        *,
        tenant_id: uuid.UUID,
        template: str,
        values: dict[str, object] | None = None,
    ) -> str:
        merged = self.build_values(tenant_id=tenant_id, values=values or {})
        return resolve_variables(template, merged)

    def build_values(self, *, tenant_id: uuid.UUID, values: dict[str, object]) -> dict[str, object]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return dict(values)

        resolved = dict(values)
        resolved.setdefault("negocio", tenant.name)
        resolved.setdefault("horas_disponibles_hoy", self.hours_available_today(tenant_id=tenant_id))
        return resolved

    def hours_available_today(self, *, tenant_id: uuid.UUID) -> str:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return "sin horarios disponibles"

        target_date = today_for_timezone(tenant.timezone_identifier)
        weekday_key = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ][target_date.weekday()]

        business_hours = getattr(tenant, "business_hours", {}) or {}
        day = business_hours.get(weekday_key) or {}
        if not day.get("is_open"):
            return "sin horarios disponibles"

        open_raw = day.get("open")
        close_raw = day.get("close")
        if not open_raw or not close_raw:
            return "sin horarios disponibles"

        try:
            open_time = datetime.strptime(open_raw, "%H:%M").time()
            close_time = datetime.strptime(close_raw, "%H:%M").time()
        except ValueError:
            return "sin horarios disponibles"

        slot_minutes = max(int(getattr(tenant, "slot_duration", 15) or 15), 5)
        now_local = now_for_timezone(tenant.timezone_identifier)
        slots: set[str] = set()

        staff_users = [
            item
            for item in self.user_repo.list_by_tenant(tenant_id)
            if item.is_active and item.role in {UserRole.OWNER, UserRole.STAFF}
        ]

        for staff in staff_users:
            occupied = self.appointment_repo.list_active_by_user_on_date(
                tenant_id=tenant_id,
                user_id=staff.id,
                appointment_date=target_date,
            )

            cursor = datetime.combine(target_date, open_time)
            close_dt = datetime.combine(target_date, close_time)
            step = timedelta(minutes=slot_minutes)
            while cursor + step <= close_dt:
                slot_end = cursor + step
                if target_date == now_local.date() and cursor.time() < now_local.time():
                    cursor += step
                    continue

                has_conflict = False
                for appt in occupied:
                    appt_start = datetime.combine(target_date, appt.time_start)
                    appt_end = datetime.combine(target_date, appt.time_end)
                    if appt_start < slot_end and appt_end > cursor:
                        has_conflict = True
                        break

                if not has_conflict:
                    slots.add(cursor.strftime("%H:%M"))
                cursor += step

        if not slots:
            return "sin horarios disponibles"

        preview = sorted(slots)[:6]
        return ", ".join(self._to_12h(item) for item in preview)

    @staticmethod
    def _to_12h(value: str) -> str:
        try:
            parsed = datetime.strptime(value, "%H:%M")
        except ValueError:
            return value
        formatted = parsed.strftime("%I:%M %p").lower()
        return formatted[1:] if formatted.startswith("0") else formatted
