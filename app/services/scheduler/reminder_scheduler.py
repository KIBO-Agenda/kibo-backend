import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.timezone import now_for_timezone
from app.models.appointments import Appointment, AppointmentStatus
from app.models.tenant import PlanTier, Tenant
from app.repositories.clients import ClientRepository
from app.repositories.services import ServiceRepository
from app.repositories.tenant import TenantRepository
from app.services.whatsapp.evolution_client import EvolutionClient, EvolutionClientError
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

    async def _send_24h_reminders(self, db: Session) -> None:
        """Send 24-hour reminder for appointments tomorrow."""
        client_repo = ClientRepository(db)
        service_repo = ServiceRepository(db)
        resolver = WhatsAppVariableResolver(db)

        # Get all active tenants with plan that supports reminders (PRO or BUSINESS)
        all_tenants = db.query(Tenant).all()

        for tenant in all_tenants:
            if not self._plan_supports_reminders(tenant.plan_tier):
                continue

            if not tenant.whatsapp_instance_id:
                logger.debug(f"Tenant {tenant.id}: no WhatsApp instance configured.")
                continue

            # Get tomorrow's date in tenant timezone
            tz_now = now_for_timezone(tenant.timezone_identifier or "America/Bogota")
            tomorrow = (tz_now + timedelta(days=1)).date()

            # Find appointments for tomorrow that haven't had 24h reminder sent
            appointments = db.query(Appointment).filter(
                Appointment.tenant_id == tenant.id,
                Appointment.appointment_date == tomorrow,
                Appointment.status == AppointmentStatus.PENDING,
                Appointment.last_notification_type != "reminder_24h",
            ).all()

            for appointment in appointments:
                client = client_repo.get_by_id(tenant.id, appointment.client_id)
                service = service_repo.get_by_id(tenant.id, appointment.service_id)
                if not client or not client.phone or client.whatsapp_opt_out:
                    logger.debug(
                        f"Appointment {appointment.id}: client {client.id if client else 'unknown'} "
                        f"missing phone or opted-out."
                    )
                    continue

                try:
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
                    logger.info(
                        f"24h reminder sent: tenant={tenant.id}, appointment={appointment.id}, phone={client.phone}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to send 24h reminder for appointment {appointment.id}: {e}"
                    )

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

            # Get current time in tenant timezone
            tz_now = now_for_timezone(tenant.timezone_identifier or "America/Bogota")
            cutoff_time = tz_now + timedelta(hours=2)

            # Find appointments for today in the next 2 hours that haven't had 2h reminder sent
            today = tz_now.date()
            appointments = db.query(Appointment).filter(
                Appointment.tenant_id == tenant.id,
                Appointment.appointment_date == today,
                Appointment.status == AppointmentStatus.PENDING,
                Appointment.last_notification_type != "reminder_2h",
            ).all()

            for appointment in appointments:
                # Check if appointment is within 2-hour window
                appointment_datetime = datetime.combine(
                    appointment.appointment_date, appointment.time_start, 
                    tzinfo=timezone.utc
                )
                # Normalize to tenant timezone
                appointment_datetime = appointment_datetime.astimezone(
                    ZoneInfo(tenant.timezone_identifier or "America/Bogota")
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
                        logger.error(f"Failed to send 2h reminder for appointment {appointment.id}: {e}")

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
        # Format appointment time in tenant's timezone
        appointment_tz = ZoneInfo(tenant.timezone_identifier or "America/Bogota")
        appointment_datetime = datetime.combine(
            appointment.appointment_date, appointment.time_start, tzinfo=timezone.utc
        ).astimezone(appointment_tz)

        appointment_time_str = appointment_datetime.strftime("%H:%M")

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

        # Normalize phone to 57+number format if needed
        phone = client_phone
        if not phone.startswith("57"):
            phone = f"57{phone.lstrip('0+')}"

        try:
            await self.evolution_client.send_text(
                instance_name=tenant.whatsapp_instance_id,
                phone=phone,
                text=message,
            )
        except EvolutionClientError as e:
            raise e

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

    def _plan_supports_reminders(self, plan_tier: PlanTier) -> bool:
        """Check if plan tier includes automatic reminders."""
        # STARTER: no automatic reminders (manual only)
        # PRO: 24h + 2h reminders
        # BUSINESS: 24h + 2h reminders + extras
        return plan_tier in {PlanTier.PRO, PlanTier.BUSINESS}
