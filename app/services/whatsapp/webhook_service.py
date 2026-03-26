from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timezone import now_for_timezone
from app.models.appointments import AppointmentStatus
from app.repositories.appointments import AppointmentRepository
from app.repositories.clients import ClientRepository
from app.repositories.tenant import TenantConfigRepository, TenantRepository
from app.repositories.waitlists import WaitlistRepository
from app.repositories.whatsapp_events import ProcessedWebhookRepository
from app.repositories.whatsapp_outbox import WhatsAppOutboxRepository
from app.services.whatsapp.template_engine import TemplateEngineError, select_variant
from app.services.whatsapp.evolution_client import EvolutionClient, EvolutionClientError
from app.services.whatsapp.variable_resolver import WhatsAppVariableResolver

logger = logging.getLogger(__name__)

_CONFIRM = {"1"}
_CANCEL = {"2"}
_RESCHEDULE = {"3"}
_OWNER_APPROVE = {"SI", "S", "OK", "DALE"}


def _normalize_digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _normalize_keyword(value: str | None) -> str:
    return "".join(ch for ch in (value or "").upper().strip() if ch.isalnum())


def _parse_note_payload(notes: str | None) -> dict[str, str]:
    if not notes or not notes.startswith("KIBO_"):
        return {}

    output: dict[str, str] = {}
    parts = notes.split("|")
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        output[key.strip()] = value.strip()
    return output


class WhatsAppWebhookService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self.tenant_repo = TenantRepository(db)
        self.tenant_config_repo = TenantConfigRepository(db)
        self.client_repo = ClientRepository(db)
        self.appointment_repo = AppointmentRepository(db)
        self.waitlist_repo = WaitlistRepository(db)
        self.processed_webhook_repo = ProcessedWebhookRepository(db)
        self.outbox_repo = WhatsAppOutboxRepository(db)
        self.variable_resolver = WhatsAppVariableResolver(db)
        self.evolution_client = EvolutionClient()

    async def process_incoming_message(
        self,
        *,
        instance_name: str,
        sender_phone: str,
        text: str,
        message_id: str | None,
    ) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_whatsapp_instance_id(instance_name)
        if not tenant:
            return {"processed": False, "reason": "tenant_not_found"}

        tenant_config = self.tenant_config_repo.get_or_create(tenant_id=tenant.id)
        if not tenant_config.whatsapp_enabled:
            return {"processed": False, "reason": "whatsapp_disabled"}

        if message_id and self.processed_webhook_repo.exists(message_id=message_id):
            return {"processed": False, "reason": "duplicate_message"}

        normalized_phone = _normalize_digits(sender_phone)
        normalized_text = _normalize_keyword(text)
        if not normalized_phone or not normalized_text:
            return {"processed": False, "reason": "payload_incomplete"}

        action = "none"
        if normalized_text in _CONFIRM:
            action = "confirm"
        elif normalized_text in _CANCEL:
            action = "cancel"
        elif normalized_text in _RESCHEDULE:
            action = "reschedule"
        logger.info("[WH_IN] Tenant: %s | Msg: %s | Action: %s", tenant.id, normalized_text, action)

        if self._is_owner_phone(tenant.phone, normalized_phone) and normalized_text in _OWNER_APPROVE:
            owner_result = await self._handle_owner_approval(tenant_id=tenant.id)
            if message_id:
                self.processed_webhook_repo.register(
                    message_id=message_id,
                    tenant_id=tenant.id,
                    sender_phone=normalized_phone,
                )
            return {"processed": True, "flow": "owner_approval", **owner_result}

        if normalized_text in _CONFIRM:
            waitlist_result = await self._try_waitlist_auto_booking(
                tenant_id=tenant.id,
                sender_phone=normalized_phone,
            )
            if waitlist_result["matched"]:
                if message_id:
                    self.processed_webhook_repo.register(
                        message_id=message_id,
                        tenant_id=tenant.id,
                        sender_phone=normalized_phone,
                    )
                return {"processed": True, "flow": "waitlist_autobooking", **waitlist_result}

            result = await self._handle_appointment_confirmation(
                tenant_id=tenant.id,
                sender_phone=normalized_phone,
            )
            if message_id:
                self.processed_webhook_repo.register(
                    message_id=message_id,
                    tenant_id=tenant.id,
                    sender_phone=normalized_phone,
                )
            return result

        if normalized_text in _CANCEL:
            result = await self._handle_appointment_cancellation(
                tenant_id=tenant.id,
                sender_phone=normalized_phone,
            )
            if message_id:
                self.processed_webhook_repo.register(
                    message_id=message_id,
                    tenant_id=tenant.id,
                    sender_phone=normalized_phone,
                )
            return result

        if normalized_text in _RESCHEDULE:
            result = await self._handle_reschedule_request(
                tenant_id=tenant.id,
                sender_phone=normalized_phone,
            )
            if message_id:
                self.processed_webhook_repo.register(
                    message_id=message_id,
                    tenant_id=tenant.id,
                    sender_phone=normalized_phone,
                )
            return result

        if await self._should_send_welcome_message(tenant_id=tenant.id, sender_phone=normalized_phone):
            await self._send_welcome_message(tenant_id=tenant.id, sender_phone=normalized_phone)
            if message_id:
                self.processed_webhook_repo.register(
                    message_id=message_id,
                    tenant_id=tenant.id,
                    sender_phone=normalized_phone,
                )
            return {"processed": True, "action": "welcome_sent"}

        if message_id:
            self.processed_webhook_repo.register(
                message_id=message_id,
                tenant_id=tenant.id,
                sender_phone=normalized_phone,
            )

        return {"processed": False, "reason": "command_not_supported"}

    @staticmethod
    def _is_owner_phone(owner_phone: str | None, incoming_phone: str) -> bool:
        owner_digits = _normalize_digits(owner_phone)
        if not owner_digits:
            return False
        return incoming_phone.endswith(owner_digits) or owner_digits.endswith(incoming_phone)

    async def _handle_appointment_confirmation(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_phone: str,
    ) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return {"processed": False, "reason": "tenant_not_found"}

        now_local = now_for_timezone(tenant.timezone_identifier)
        appointment = self.appointment_repo.get_nearest_pending_by_client_phone(
            tenant_id=tenant_id,
            phone=sender_phone,
            now=now_local,
        )
        if not appointment:
            return {"processed": False, "reason": "pending_appointment_not_found"}

        self.appointment_repo.update(
            tenant_id,
            appointment.id,
            status=AppointmentStatus.CONFIRMED,
            last_notification_type="none",
        )

        await self._safe_send_text(
            instance_name=tenant.whatsapp_instance_id,
            phone=sender_phone,
            text="Perfecto. Tu cita quedo confirmada. Te esperamos.",
        )
        return {
            "processed": True,
            "action": "appointment_confirmed",
            "appointment_id": str(appointment.id),
        }

    async def _handle_appointment_cancellation(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_phone: str,
    ) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return {"processed": False, "reason": "tenant_not_found"}

        now_local = now_for_timezone(tenant.timezone_identifier)
        appointment = self.appointment_repo.get_nearest_pending_by_client_phone(
            tenant_id=tenant_id,
            phone=sender_phone,
            now=now_local,
        )
        if not appointment:
            return {"processed": False, "reason": "pending_appointment_not_found"}

        self.appointment_repo.update(
            tenant_id,
            appointment.id,
            status=AppointmentStatus.CANCELLED,
            last_notification_type="none",
        )

        await self._safe_send_text(
            instance_name=tenant.whatsapp_instance_id,
            phone=sender_phone,
            text="Listo. Tu cita fue cancelada.",
        )

        waitlist_triggered = await self._trigger_waitlist_flow(
            tenant_id=tenant_id,
            appointment_id=appointment.id,
            appointment_date=appointment.appointment_date,
            service_id=appointment.service_id,
        )

        return {
            "processed": True,
            "action": "appointment_cancelled",
            "appointment_id": str(appointment.id),
            "waitlist_triggered": waitlist_triggered,
        }

    async def _handle_reschedule_request(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_phone: str,
    ) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return {"processed": False, "reason": "tenant_not_found"}

        now_local = now_for_timezone(tenant.timezone_identifier)
        appointment = self.appointment_repo.get_nearest_pending_by_client_phone(
            tenant_id=tenant_id,
            phone=sender_phone,
            now=now_local,
        )
        if not appointment:
            return {"processed": False, "reason": "pending_appointment_not_found"}

        related = self.appointment_repo.get_by_id_with_relations(
            tenant_id=tenant_id,
            appointment_id=appointment.id,
        )

        self.appointment_repo.update(
            tenant_id,
            appointment.id,
            status=AppointmentStatus.RESCHEDULE_REQ,
            last_notification_type="none",
        )
        service_name = related.service_name if related else "tu servicio"
        available_hours = self.variable_resolver.hours_available_today(tenant_id=tenant_id)
        business_link = f"{self.settings.FRONTEND_URL.rstrip('/')}/owner/dashboard"

        await self._safe_send_text(
            instance_name=tenant.whatsapp_instance_id,
            phone=sender_phone,
            text=(
                f"Soy Kibo, el asistente de {tenant.name}. "
                f"Para reagendar {service_name}, usa este link: {business_link}. "
                f"Hoy tenemos disponible: {available_hours}."
            ),
        )

        return {
            "processed": True,
            "action": "reschedule_link_sent",
            "appointment_id": str(appointment.id),
            "horas_disponibles_hoy": available_hours,
        }

    async def _trigger_waitlist_flow(
        self,
        *,
        tenant_id: uuid.UUID,
        appointment_id: uuid.UUID,
        appointment_date,
        service_id: uuid.UUID,
    ) -> bool:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return False

        tenant_config = self.tenant_config_repo.get_or_create(tenant_id=tenant_id)
        waitlist_item = self.waitlist_repo.first_unresolved_by_date(
            tenant_id,
            appointment_date,
            service_id=service_id,
        )
        if not waitlist_item or not waitlist_item.client_phone:
            return False

        manual_approval = bool(tenant_config.waitlist_manual_approval)
        if manual_approval:
            note_payload = f"KIBO_PENDING_OFFER|appointment_id={appointment_id}|target_phone={waitlist_item.client_phone}"
            self.waitlist_repo.update_notes(tenant_id, waitlist_item.id, note_payload)
            if tenant.phone:
                await self._safe_send_text(
                    instance_name=tenant.whatsapp_instance_id,
                    phone=tenant.phone,
                    text=(
                        f"Hueco libre detectado. Quieres ofrecerselo a {waitlist_item.client_name}? "
                        f"Responde SI para enviar."
                    ),
                )
            return True

        await self._offer_waitlist_slot(
            tenant=tenant,
            waitlist_id=waitlist_item.id,
            waitlist_phone=waitlist_item.client_phone,
            waitlist_name=waitlist_item.client_name,
            appointment_id=appointment_id,
        )
        return True

    async def _handle_owner_approval(self, *, tenant_id: uuid.UUID) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return {"matched": False, "reason": "tenant_not_found"}

        waitlist_item = self.waitlist_repo.first_pending_offer(tenant_id)
        if not waitlist_item or not waitlist_item.client_phone:
            if tenant.phone:
                await self._safe_send_text(
                    instance_name=tenant.whatsapp_instance_id,
                    phone=tenant.phone,
                    text="No hay ofertas pendientes de lista de espera.",
                )
            return {"matched": False, "reason": "pending_offer_not_found"}

        payload = _parse_note_payload(waitlist_item.notes)
        appointment_id_raw = payload.get("appointment_id")
        if not appointment_id_raw:
            return {"matched": False, "reason": "appointment_reference_missing"}

        await self._offer_waitlist_slot(
            tenant=tenant,
            waitlist_id=waitlist_item.id,
            waitlist_phone=waitlist_item.client_phone,
            waitlist_name=waitlist_item.client_name,
            appointment_id=uuid.UUID(appointment_id_raw),
        )
        return {"matched": True, "waitlist_id": str(waitlist_item.id)}

    async def _offer_waitlist_slot(
        self,
        *,
        tenant,
        waitlist_id: uuid.UUID,
        waitlist_phone: str,
        waitlist_name: str,
        appointment_id: uuid.UUID,
    ) -> None:
        note_payload = f"KIBO_OFFER_SENT|appointment_id={appointment_id}"
        self.waitlist_repo.update_notes(tenant.id, waitlist_id, note_payload)

        await self._safe_send_text(
            instance_name=tenant.whatsapp_instance_id,
            phone=waitlist_phone,
            text=(
                f"Hola {waitlist_name}. Se libero un espacio. "
                "Quieres tomarlo? Responde 1 para agendar."
            ),
        )

        if tenant.phone:
            await self._safe_send_text(
                instance_name=tenant.whatsapp_instance_id,
                phone=tenant.phone,
                text=f"Invitacion enviada a {waitlist_name}.",
            )

    async def _try_waitlist_auto_booking(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_phone: str,
    ) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return {"matched": False, "reason": "tenant_not_found"}

        waitlist_item = self.waitlist_repo.get_first_unresolved_by_phone(tenant_id, sender_phone)
        if not waitlist_item:
            return {"matched": False, "reason": "waitlist_item_not_found"}

        metadata = _parse_note_payload(waitlist_item.notes)
        appointment_id_raw = metadata.get("appointment_id")
        if not appointment_id_raw:
            return {"matched": False, "reason": "waitlist_offer_not_found"}

        slot_reference = self.appointment_repo.get_by_id(tenant_id, uuid.UUID(appointment_id_raw))
        if not slot_reference:
            return {"matched": False, "reason": "slot_reference_missing"}

        if self.appointment_repo.has_overlap(
            tenant_id=tenant_id,
            user_id=slot_reference.user_id,
            appointment_date=slot_reference.appointment_date,
            time_start=slot_reference.time_start,
            time_end=slot_reference.time_end,
        ):
            await self._safe_send_text(
                instance_name=tenant.whatsapp_instance_id,
                phone=sender_phone,
                text="Ese espacio ya no esta disponible. Te avisamos cuando se libere otro.",
            )
            return {"matched": True, "booked": False, "reason": "slot_not_available"}

        client = self.client_repo.get_by_phone_normalized(tenant_id, sender_phone)
        if not client:
            fallback_phone = waitlist_item.client_phone
            waitlist_digits = _normalize_digits(waitlist_item.client_phone)
            sender_digits = _normalize_digits(sender_phone)
            if sender_digits and waitlist_digits and sender_digits.endswith(waitlist_digits):
                fallback_phone = sender_phone
            client = self.client_repo.create(
                tenant_id=tenant_id,
                name=waitlist_item.client_name,
                phone=fallback_phone,
            )

        self.appointment_repo.create(
            tenant_id=tenant_id,
            client_id=client.id,
            user_id=slot_reference.user_id,
            service_id=slot_reference.service_id,
            appointment_date=slot_reference.appointment_date,
            time_start=slot_reference.time_start,
            time_end=slot_reference.time_end,
            notes="Auto-booked from waitlist",
        )
        self.waitlist_repo.resolve(tenant_id, waitlist_item.id)

        if tenant.phone:
            await self._safe_send_text(
                instance_name=tenant.whatsapp_instance_id,
                phone=tenant.phone,
                text=f"{waitlist_item.client_name} acepto el espacio y ya fue agendado.",
            )

        await self._safe_send_text(
            instance_name=tenant.whatsapp_instance_id,
            phone=sender_phone,
            text="Listo. Tu cita quedo registrada. Te esperamos.",
        )

        return {
            "matched": True,
            "booked": True,
            "waitlist_id": str(waitlist_item.id),
        }

    async def _should_send_welcome_message(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_phone: str,
    ) -> bool:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return False

        now_local = now_for_timezone(tenant.timezone_identifier)
        has_pending = self.appointment_repo.has_pending_in_next_hours_by_client_phone(
            tenant_id=tenant_id,
            phone=sender_phone,
            now=now_local,
            hours=24,
        )
        if has_pending:
            return False

        cutoff = now_local - timedelta(hours=24)
        already_received = self.processed_webhook_repo.exists_recent_by_phone(
            tenant_id=tenant_id,
            sender_phone=sender_phone,
            since=cutoff,
        )
        if already_received:
            return False

        already_sent = self.outbox_repo.has_recent_message(
            business_id=tenant_id,
            phone=sender_phone,
            message_type="welcome_message",
            since=cutoff,
        )
        return not already_sent

    async def _send_welcome_message(self, *, tenant_id: uuid.UUID, sender_phone: str) -> None:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return

        templates = tenant.message_templates or {}
        try:
            _, template = select_variant(templates, "welcome_message")
            message = self.variable_resolver.resolve(
                tenant_id=tenant_id,
                template=template,
                values={"nombre": "Cliente"},
            )
        except TemplateEngineError:
            message = (
                f"Hola, Bienvenido a {tenant.name}. "
                f"Si quieres agendar una cita, tenemos disponible hoy: "
                f"{self.variable_resolver.hours_available_today(tenant_id=tenant_id)}."
            )

        await self._safe_send_text(
            instance_name=tenant.whatsapp_instance_id,
            phone=sender_phone,
            text=message,
        )

    async def _safe_send_text(self, *, instance_name: str | None, phone: str, text: str) -> None:
        if not instance_name:
            return
        try:
            await self.evolution_client.send_text(
                instance_name=instance_name,
                phone=phone,
                text=text,
            )
        except EvolutionClientError as exc:
            logger.warning("WhatsApp send failed: %s", exc)
