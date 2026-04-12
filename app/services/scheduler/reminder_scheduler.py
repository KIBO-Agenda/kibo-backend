import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
import uuid
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.timezone import now_for_timezone
from app.models.appointments import Appointment, AppointmentStatus
from app.models.tenant import PlanTier, Tenant
from app.repositories.clients import ClientRepository
from app.repositories.services import ServiceRepository
from app.services.whatsapp.evolution_client import EvolutionClient
from app.services.whatsapp.template_engine import TemplateEngineError, select_variant
from app.services.whatsapp.variable_resolver import WhatsAppVariableResolver

logger = logging.getLogger(__name__)


class ReminderScheduler:
    """Sends appointment reminders via WhatsApp based on appointment timing and plan tier."""

    def __init__(self, db_sessionmaker) -> None:
        self.db_sessionmaker = db_sessionmaker
        self.evolution_client = EvolutionClient()

    async def process_reminders(self) -> None:
        """Execute reminder job: find appointments and send WhatsApp reminders."""
        db = self.db_sessionmaker()
        try:
            await self._send_24h_reminders(db)
            await self._send_2h_reminders(db)
        except Exception as e:
            logger.exception(f"Error processing reminders: {e}")
        finally:
            db.close()

    async def _send_24h_reminders(
        self,
        db: Session,
        *,
        force: bool = False,
        tenant_id: uuid.UUID | None = None,
        dry_run: bool = False,
    ) -> dict[str, int]:
        """Send 24-hour reminder for appointments tomorrow."""
        client_repo = ClientRepository(db)
        service_repo = ServiceRepository(db)
        resolver = WhatsAppVariableResolver(db)

        all_tenants = db.query(Tenant).all()
        counters = {"tenants": 0, "evaluated": 0, "sent": 0, "errors": 0}

        for tenant in all_tenants:
            if tenant_id and tenant.id != tenant_id:
                continue
            if not self._plan_supports_reminders(tenant.plan_tier):
                continue
            counters["tenants"] += 1

            if not tenant.whatsapp_instance_id:
                logger.debug(f"Tenant {tenant.id}: no WhatsApp instance configured.")
                continue

            tz_now = now_for_timezone(tenant.timezone_identifier or "America/Bogota")
            tomorrow = (tz_now + timedelta(days=1)).date()

            query = db.query(Appointment).filter(
                Appointment.tenant_id == tenant.id,
                Appointment.appointment_date == tomorrow,
                Appointment.status == AppointmentStatus.PENDING,
            )
            if not force:
                query = query.filter(Appointment.reminder_24h_sent.is_(False))

            appointments = query.all()

            for appointment in appointments:
                counters["evaluated"] += 1
                client = client_repo.get_by_id(tenant.id, appointment.client_id)
                service = service_repo.get_by_id(tenant.id, appointment.service_id)
                if not client or not client.phone or client.whatsapp_opt_out:
                    logger.debug(
                        f"Appointment {appointment.id}: client {client.id if client else 'unknown'} "
                        f"missing phone or opted-out."
                    )
                    continue

                try:
                    if dry_run:
                        logger.info(
                            "[DRY_RUN] Eligible tomorrow reminder: tenant=%s appointment=%s phone=%s",
                            tenant.id,
                            appointment.id,
                            client.phone,
                        )
                        counters["sent"] += 1
                        continue

                    await self._send_reminder_message(
                        tenant=tenant,
                        client_phone=client.phone,
                        appointment=appointment,
                        client_name=client.name,
                        service_name=service.name if service else "tu servicio",
                        resolver=resolver,
                        reminder_type="24h",
                    )
                    appointment.reminder_24h_sent = True
                    appointment.last_notification_type = "reminder_24h"
                    db.commit()
                    counters["sent"] += 1
                    logger.info(
                        f"24h reminder sent: tenant={tenant.id}, appointment={appointment.id}, phone={client.phone}"
                    )
                except Exception as e:
                    counters["errors"] += 1
                    db.rollback()
                    logger.error(
                        "Failed to send 24h reminder: tenant=%s appointment=%s error=%s",
                        tenant.id,
                        appointment.id,
                        e,
                    )

        return counters

    async def _send_2h_reminders(self, db: Session) -> None:
        """Send 2-hour reminder for appointments starting in next 2 hours."""
        client_repo = ClientRepository(db)
        service_repo = ServiceRepository(db)
        resolver = WhatsAppVariableResolver(db)

        all_tenants = db.query(Tenant).all()

        for tenant in all_tenants:
            if not self._plan_supports_reminders(tenant.plan_tier):
                continue

            if not tenant.whatsapp_instance_id:
                logger.debug(f"Tenant {tenant.id}: no WhatsApp instance configured.")
                continue

            tz_now = now_for_timezone(tenant.timezone_identifier or "America/Bogota")
            cutoff_time = tz_now + timedelta(hours=2)

            today = tz_now.date()
            appointments = db.query(Appointment).filter(
                Appointment.tenant_id == tenant.id,
                Appointment.appointment_date == today,
                Appointment.status == AppointmentStatus.PENDING,
                Appointment.reminder_2h_sent.is_(False),
            ).all()

            for appointment in appointments:
                appointment_datetime = self._appointment_datetime_for_tenant(
                    tenant=tenant,
                    appointment=appointment,
                )

                if tz_now < appointment_datetime <= cutoff_time:
                    client = client_repo.get_by_id(tenant.id, appointment.client_id)
                    service = service_repo.get_by_id(tenant.id, appointment.service_id)
                    if not client or not client.phone or client.whatsapp_opt_out:
                        logger.debug(f"Appointment {appointment.id}: client skipped (no phone or opted-out).")
                        continue

                    try:
                        await self._send_reminder_message(
                            tenant=tenant,
                            client_phone=client.phone,
                            appointment=appointment,
                            client_name=client.name,
                            service_name=service.name if service else "tu servicio",
                            resolver=resolver,
                            reminder_type="2h",
                        )
                        appointment.reminder_2h_sent = True
                        appointment.last_notification_type = "reminder_2h"
                        db.commit()
                        logger.info(
                            f"2h reminder sent: tenant={tenant.id}, appointment={appointment.id}, phone={client.phone}"
                        )
                    except Exception as e:
                        db.rollback()
                        logger.error(
                            "Failed to send 2h reminder: tenant=%s appointment=%s error=%s",
                            tenant.id,
                            appointment.id,
                            e,
                        )

    async def _send_reminder_message(
        self,
        *,
        tenant,
        client_phone: str,
        appointment,
        client_name: str,
        service_name: str,
        resolver: WhatsAppVariableResolver,
        reminder_type: str,
    ) -> None:
        """Send a reminder message via Evolution API."""
        appointment_time_str = appointment.time_start.strftime("%H:%M")

        values = {
            "nombre": client_name,
            "negocio": tenant.name,
            "hora": appointment_time_str,
            "servicio": service_name,
            "fecha": appointment.appointment_date.isoformat(),
        }

        message_type = "reminder_24h" if reminder_type == "24h" else "reminder_2h"
        try:
            _, template = select_variant(tenant.message_templates or {}, message_type)
            message = resolver.resolve(
                tenant_id=tenant.id,
                template=template,
                values=values,
            )
        except TemplateEngineError:
            if reminder_type == "24h":
                message = (
                    f"Hola {client_name}, soy Kibo, el asistente de {tenant.name}. "
                    f"Te recuerdo tu cita para {service_name} manana a las {appointment_time_str}. "
                    "Responde 1 para Confirmar, 2 para Cancelar o 3 para Reagendar."
                )
            else:
                message = (
                    f"Hola {client_name}, soy Kibo. Tu cita para {service_name} en {tenant.name} "
                    f"es hoy a las {appointment_time_str}. Responde 1 para confirmar, 2 para cancelar o 3 para reagendar."
                )

        phone = client_phone
        if not phone.startswith("57"):
            phone = f"57{phone.lstrip('0+')}"

        response = await self.evolution_client.send_text(
            instance_name=tenant.whatsapp_instance_id,
            phone=phone,
            text=message,
        )

        remote_id = self._extract_remote_id(response)
        logger.info(
            "[WA_REMINDER] Evolution response captured",
            extra={
                "tenant_id": str(tenant.id),
                "appointment_id": str(appointment.id),
                "reminder_type": reminder_type,
                "remote_id": remote_id,
            },
        )

        if remote_id:
            appointment.whatsapp_remote_id = remote_id
        else:
            logger.warning(
                "[WA_REMINDER] remote_id missing in provider response",
                extra={
                    "tenant_id": str(tenant.id),
                    "appointment_id": str(appointment.id),
                    "reminder_type": reminder_type,
                    "provider_response": response,
                },
            )

    @staticmethod
    def _appointment_datetime_for_tenant(*, tenant: Tenant, appointment: Appointment) -> datetime:
        appointment_tz = ZoneInfo(tenant.timezone_identifier or "America/Bogota")
        return datetime.combine(
            appointment.appointment_date,
            appointment.time_start,
            tzinfo=appointment_tz,
        )

    @staticmethod
    def _extract_remote_id(response: Any) -> str | None:
        """
        Extract remoteJid from Evolution API response.
        Expected format: {"key": {"remoteJid": "573008862735@s.whatsapp.net", ...}, ...}
        """
        if not isinstance(response, Mapping):
            return None

        key_data = response.get("key")
        if isinstance(key_data, Mapping):
            remote_jid = key_data.get("remoteJid")
            if isinstance(remote_jid, str):
                return remote_jid

        data = response.get("data")
        if isinstance(data, Mapping):
            key_data = data.get("key")
            if isinstance(key_data, Mapping):
                remote_jid = key_data.get("remoteJid")
                if isinstance(remote_jid, str):
                    return remote_jid

        return None

    async def process_24h_reminders(self) -> None:
        db = self.db_sessionmaker()
        try:
            await self._send_24h_reminders(db)
        finally:
            db.close()

    async def process_2h_reminders(self) -> None:
        db = self.db_sessionmaker()
        try:
            await self._send_2h_reminders(db)
        finally:
            db.close()

    async def process_tomorrow_reminders(
        self,
        *,
        force: bool = False,
        tenant_id: uuid.UUID | None = None,
        dry_run: bool = False,
    ) -> dict[str, int]:
        db = self.db_sessionmaker()
        try:
            return await self._send_24h_reminders(
                db,
                force=force,
                tenant_id=tenant_id,
                dry_run=dry_run,
            )
        finally:
            db.close()

    def _plan_supports_reminders(self, plan_tier: PlanTier) -> bool:
        """Check if plan tier includes automatic reminders."""
        return plan_tier in {PlanTier.PRO, PlanTier.BUSINESS}
