from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timezone import now_for_timezone
from app.models.appointments import Appointment, AppointmentStatus
from app.repositories.appointments import AppointmentRepository
from app.repositories.clients import ClientRepository
from app.repositories.tenant import TenantConfigRepository, TenantRepository
from app.repositories.waitlists import WaitlistRepository
from app.repositories.whatsapp_events import ProcessedWebhookRepository
from app.repositories.whatsapp_outbox import WhatsAppOutboxRepository
from app.services.whatsapp.evolution_client import EvolutionClient, EvolutionClientError
from app.services.whatsapp.template_engine import TemplateEngineError, select_variant
from app.services.whatsapp.variable_resolver import WhatsAppVariableResolver

logger = logging.getLogger(__name__)

_CONFIRM = {
    "1",
    "SI",
    "S",
    "OK",
    "DALE",
    "CONFIRMO",
    "YAVOY",
    "YAVOYAMIGO",
    "VOY",
    "LISTO",
}
_CANCEL = {"2"}
_RESCHEDULE = {"3"}
_OWNER_APPROVE = {"SI", "S", "OK", "DALE"}


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
        sender_name: str | None = None,
        remote_jid: str | None = None,
        sender_jid: str | None = None,
        sender_pn_jid: str | None = None,
    ) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_whatsapp_instance_id(instance_name)
        if not tenant:
            return {"processed": False, "reason": "tenant_not_found"}

        tenant_config = self.tenant_config_repo.get_or_create(tenant_id=tenant.id)
        if not tenant_config.whatsapp_enabled:
            return {"processed": False, "reason": "whatsapp_disabled"}

        scoped_message_id = self._scoped_message_id(
            message_id=message_id,
            tenant_id=tenant.id,
        )
        if scoped_message_id and self.processed_webhook_repo.exists(message_id=scoped_message_id):
            logger.info(
                "[WH_DEDUPE] Duplicate webhook skipped: tenant=%s raw_message_id=%s scoped_message_id=%s",
                tenant.id,
                message_id,
                scoped_message_id,
            )
            return {"processed": False, "reason": "duplicate_message"}

        normalized_phone = _normalize_digits(sender_phone)
        incoming_phone_variants = _phone_variants(normalized_phone)
        normalized_text = _normalize_keyword(text)
        if not normalized_text:
            return {"processed": False, "reason": "payload_incomplete"}

        resolved_reply_jid = self._resolve_reply_jid(
            sender_pn_jid=sender_pn_jid,
            sender_jid=sender_jid,
            remote_jid=remote_jid,
        )
        remote_lid = remote_jid if remote_jid and remote_jid.endswith("@lid") else None

        logger.info(
            "[WH_IDENT] tenant=%s instance=%s sender_phone=%s sender_jid=%s sender_pn=%s remote_jid=%s reply_jid=%s",
            tenant.id,
            instance_name,
            normalized_phone,
            sender_jid,
            sender_pn_jid,
            remote_jid,
            resolved_reply_jid,
        )

        # Priority matching logic: first try remote_id, then fallback to phone
        match_source = "phone_number"
        appointment = None

        if remote_jid:
            logger.info(f"[WH_MATCH] Buscando cita por RemoteID: {remote_jid} para tenant {tenant.id}")
            now_local = now_for_timezone(tenant.timezone_identifier)
            appointment = self.appointment_repo.get_nearest_pending_by_remote_id(
                tenant_id=tenant.id,
                remote_id=remote_jid,
                now=now_local,
            )

            if appointment:
                # Verify the appointment has a valid client
                if appointment.client_id:
                    client = self.client_repo.get_by_id(tenant.id, appointment.client_id)
                    if client and client.phone:
                        matched_phone = _normalize_digits(client.phone)
                        if matched_phone:
                            normalized_phone = matched_phone
                            incoming_phone_variants = _phone_variants(matched_phone)
                        match_source = "remote_id"
                        logger.info(
                            f"[WH_MATCH] Cita encontrada por RemoteID: appointment_id={appointment.id}, "
                            f"client_phone={client.phone}"
                        )
                    else:
                        logger.warning(
                            f"[WH_MATCH] RemoteID encontrado pero cliente sin teléfono válido: "
                            f"appointment_id={appointment.id}, client_id={appointment.client_id}"
                        )
                        appointment = None
                else:
                    logger.warning(
                        f"[WH_MATCH] RemoteID encontrado pero cita sin cliente: " f"appointment_id={appointment.id}"
                    )
                    appointment = None
            else:
                logger.info(f"[WH_MATCH] No se encontró cita para RemoteID: {remote_jid}")

        if not appointment and remote_lid:
            now_local = now_for_timezone(tenant.timezone_identifier)
            appointment = self.appointment_repo.get_nearest_pending_by_client_lid(
                tenant_id=tenant.id,
                whatsapp_lid=remote_lid,
                now=now_local,
            )
            if appointment:
                match_source = "client_lid"
                logger.info(
                    "[WH_MATCH] Pending appointment resolved by client whatsapp_lid: tenant=%s appointment=%s lid=%s",
                    tenant.id,
                    appointment.id,
                    remote_lid,
                )

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
            if scoped_message_id:
                self.processed_webhook_repo.register(
                    message_id=scoped_message_id,
                    tenant_id=tenant.id,
                    sender_phone=normalized_phone,
                    remote_jid=remote_jid,
                )
            return {"processed": True, "status": "success", "flow": "owner_approval", **owner_result}

        if normalized_text in _CONFIRM:
            logger.info(
                "[WH_ACTION] Confirmation keyword matched: tenant=%s text=%s",
                tenant.id,
                normalized_text,
            )
            waitlist_result = await self._try_waitlist_auto_booking(
                tenant_id=tenant.id,
                sender_phone=normalized_phone,
            )
            if waitlist_result["matched"]:
                if scoped_message_id:
                    self.processed_webhook_repo.register(
                        message_id=scoped_message_id,
                        tenant_id=tenant.id,
                        sender_phone=normalized_phone,
                        remote_jid=remote_jid,
                    )
                return {
                    "processed": True,
                    "status": "success",
                    "flow": "waitlist_autobooking",
                    **waitlist_result,
                }

            result = await self._handle_appointment_confirmation(
                tenant_id=tenant.id,
                sender_phone=normalized_phone,
                sender_name=sender_name,
                sender_phone_variants=incoming_phone_variants,
                remote_matched_appointment=appointment,
                remote_jid=remote_jid,
                reply_jid=resolved_reply_jid,
                remote_lid=remote_lid,
            )
            if scoped_message_id:
                self.processed_webhook_repo.register(
                    message_id=scoped_message_id,
                    tenant_id=tenant.id,
                    sender_phone=normalized_phone,
                    remote_jid=remote_jid,
                )
            result["matched_by"] = match_source
            return result

        if normalized_text in _CANCEL:
            result = await self._handle_appointment_cancellation(
                tenant_id=tenant.id,
                sender_phone=normalized_phone,
                sender_name=sender_name,
                sender_phone_variants=incoming_phone_variants,
                remote_matched_appointment=appointment,
                remote_jid=remote_jid,
                reply_jid=resolved_reply_jid,
                remote_lid=remote_lid,
            )
            if scoped_message_id:
                self.processed_webhook_repo.register(
                    message_id=scoped_message_id,
                    tenant_id=tenant.id,
                    sender_phone=normalized_phone,
                    remote_jid=remote_jid,
                )
            result["matched_by"] = match_source
            return result

        if normalized_text in _RESCHEDULE:
            result = await self._handle_reschedule_request(
                tenant_id=tenant.id,
                sender_phone=normalized_phone,
                sender_name=sender_name,
                sender_phone_variants=incoming_phone_variants,
                remote_matched_appointment=appointment,
                remote_jid=remote_jid,
                reply_jid=resolved_reply_jid,
                remote_lid=remote_lid,
            )
            if scoped_message_id:
                self.processed_webhook_repo.register(
                    message_id=scoped_message_id,
                    tenant_id=tenant.id,
                    sender_phone=normalized_phone,
                    remote_jid=remote_jid,
                )
            result["matched_by"] = match_source
            return result

        if await self._should_send_welcome_message(tenant_id=tenant.id, sender_phone=normalized_phone):
            await self._send_welcome_message(tenant_id=tenant.id, sender_phone=normalized_phone)
            if scoped_message_id:
                self.processed_webhook_repo.register(
                    message_id=scoped_message_id,
                    tenant_id=tenant.id,
                    sender_phone=normalized_phone,
                    remote_jid=remote_jid,
                )
            return {"processed": True, "status": "success", "action": "welcome_sent"}

        # Handle unrecognized commands
        if scoped_message_id:
            self.processed_webhook_repo.register(
                message_id=scoped_message_id,
                tenant_id=tenant.id,
                sender_phone=normalized_phone,
                remote_jid=remote_jid,
            )

        # For commands 1, 2, 3 without appointments, provide helpful response
        if normalized_text in (_CONFIRM.union(_CANCEL).union(_RESCHEDULE)):
            return {"processed": False, "reason": "no_pending_appointments"}

        # For other messages, simply ignore without error
        return {"processed": False, "reason": "event_ignored"}

    @staticmethod
    def _is_owner_phone(owner_phone: str | None, incoming_phone: str) -> bool:
        owner_digits = _normalize_digits(owner_phone)
        incoming_digits = _normalize_digits(incoming_phone)
        if not owner_digits or not incoming_digits:
            return False
        return incoming_digits.endswith(owner_digits) or owner_digits.endswith(incoming_digits)

    async def _handle_appointment_confirmation(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_phone: str,
        sender_name: str | None = None,
        sender_phone_variants: set[str] | None = None,
        remote_matched_appointment=None,
        remote_jid: str | None = None,
        reply_jid: str | None = None,
        remote_lid: str | None = None,
    ) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return {"processed": False, "reason": "tenant_not_found"}

        now_local = now_for_timezone(tenant.timezone_identifier)
        matched_by = "remote_id_or_pre_matched" if remote_matched_appointment else None
        appointment = remote_matched_appointment or self.appointment_repo.get_nearest_pending_by_client_phone(
            tenant_id=tenant_id,
            phone=sender_phone,
            now=now_local,
        )
        if appointment and not matched_by:
            matched_by = "phone"
        if not appointment and sender_name:
            appointment = self.appointment_repo.get_nearest_pending_by_client_name(
                tenant_id=tenant_id,
                client_name=sender_name,
                now=now_local,
            )
            if appointment:
                matched_by = "sender_name"
                logger.info(
                    "[WH_MATCH] Pending appointment resolved by sender_name: tenant=%s appointment=%s sender_name=%s",
                    tenant_id,
                    appointment.id,
                    sender_name,
                )
        if not appointment and sender_phone_variants:
            appointment = self.appointment_repo.get_nearest_pending_by_conversation_context_phone(
                tenant_id=tenant_id,
                sender_phone_variants=sender_phone_variants,
                now=now_local,
            )
            if appointment:
                matched_by = "conversation_context"
                logger.info(
                    "[WH_MATCH] Pending appointment resolved by conversation_context: tenant=%s appointment=%s",
                    tenant_id,
                    appointment.id,
                )
        if not appointment:
            logger.info(
                "[WH_MATCH] Pending appointment not found: tenant=%s phone=%s remote_jid=%s",
                tenant_id,
                sender_phone,
                remote_jid,
            )
            return {"processed": False, "reason": "pending_appointment_not_found"}

        # Prevent blind confirmations when there are several pending appointments and
        # the match was not deterministic by remote identifier.
        if matched_by in {"phone", "sender_name", "conversation_context"}:
            if self._has_multiple_pending_candidates(
                tenant_id=tenant_id,
                sender_phone=sender_phone,
                sender_name=sender_name,
                sender_phone_variants=sender_phone_variants,
            ):
                logger.warning(
                    (
                        "[WH_MATCH] Ambiguous pending appointment, confirmation skipped: "
                        "tenant=%s match_by=%s phone=%s sender_name=%s"
                    ),
                    tenant_id,
                    matched_by,
                    sender_phone,
                    sender_name,
                )
                return {"processed": False, "reason": "ambiguous_pending_appointments"}

        phone_to_reply = sender_phone or self._resolve_reply_phone(
            tenant_id=tenant_id,
            appointment=appointment,
            sender_phone=sender_phone,
            sender_phone_variants=sender_phone_variants,
        )

        self.appointment_repo.update(
            tenant_id,
            appointment.id,
            status=AppointmentStatus.CONFIRMED,
            last_notification_type="none",
            whatsapp_remote_id=reply_jid or remote_jid or appointment.whatsapp_remote_id,
        )

        self._persist_client_lid_if_available(
            tenant_id=tenant_id,
            appointment=appointment,
            remote_lid=remote_lid,
        )

        # Send personalized confirmation message
        confirmation_message = f"¡Confirmado! Gracias por elegir {tenant.name}. Nos vemos pronto."

        await self._safe_send_text(
            instance_name=tenant.whatsapp_instance_id,
            tenant_apikey=tenant.whatsapp_apikey or self.settings.EVOLUTION_API_KEY,
            phone=phone_to_reply,
            text=confirmation_message,
        )
        logger.info(
            "[WH_OUT] Confirmation sent: tenant=%s appointment=%s phone=%s",
            tenant_id,
            appointment.id,
            phone_to_reply,
        )
        logger.info(
            "[WH] Respuesta enviada desde Instancia: %s hacia Cliente: %s.",
            tenant.whatsapp_instance_id,
            phone_to_reply,
        )
        return {
            "processed": True,
            "status": "success",
            "action": "appointment_confirmed",
            "appointment_id": str(appointment.id),
        }

    async def _handle_appointment_cancellation(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_phone: str,
        sender_name: str | None = None,
        sender_phone_variants: set[str] | None = None,
        remote_matched_appointment=None,
        remote_jid: str | None = None,
        reply_jid: str | None = None,
        remote_lid: str | None = None,
    ) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return {"processed": False, "reason": "tenant_not_found"}

        now_local = now_for_timezone(tenant.timezone_identifier)
        appointment = remote_matched_appointment or self.appointment_repo.get_nearest_pending_by_client_phone(
            tenant_id=tenant_id,
            phone=sender_phone,
            now=now_local,
        )
        if not appointment and sender_name:
            appointment = self.appointment_repo.get_nearest_pending_by_client_name(
                tenant_id=tenant_id,
                client_name=sender_name,
                now=now_local,
            )
        if not appointment and sender_phone_variants:
            appointment = self.appointment_repo.get_nearest_pending_by_conversation_context_phone(
                tenant_id=tenant_id,
                sender_phone_variants=sender_phone_variants,
                now=now_local,
            )
        if not appointment:
            return {"processed": False, "reason": "pending_appointment_not_found"}

        phone_to_reply = self._resolve_reply_phone(
            tenant_id=tenant_id,
            appointment=appointment,
            sender_phone=sender_phone,
            sender_phone_variants=sender_phone_variants,
        )

        self.appointment_repo.update(
            tenant_id,
            appointment.id,
            status=AppointmentStatus.CANCELLED,
            last_notification_type="none",
            whatsapp_remote_id=reply_jid or remote_jid or appointment.whatsapp_remote_id,
        )

        self._persist_client_lid_if_available(
            tenant_id=tenant_id,
            appointment=appointment,
            remote_lid=remote_lid,
        )

        await self._safe_send_text(
            instance_name=tenant.whatsapp_instance_id,
            tenant_apikey=tenant.whatsapp_apikey or self.settings.EVOLUTION_API_KEY,
            phone=phone_to_reply,
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
            "status": "success",
            "action": "appointment_cancelled",
            "appointment_id": str(appointment.id),
            "waitlist_triggered": waitlist_triggered,
        }

    async def _handle_reschedule_request(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_phone: str,
        sender_name: str | None = None,
        sender_phone_variants: set[str] | None = None,
        remote_matched_appointment=None,
        remote_jid: str | None = None,
        reply_jid: str | None = None,
        remote_lid: str | None = None,
    ) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return {"processed": False, "reason": "tenant_not_found"}

        now_local = now_for_timezone(tenant.timezone_identifier)
        appointment = remote_matched_appointment or self.appointment_repo.get_nearest_pending_by_client_phone(
            tenant_id=tenant_id,
            phone=sender_phone,
            now=now_local,
        )
        if not appointment and sender_name:
            appointment = self.appointment_repo.get_nearest_pending_by_client_name(
                tenant_id=tenant_id,
                client_name=sender_name,
                now=now_local,
            )
        if not appointment and sender_phone_variants:
            appointment = self.appointment_repo.get_nearest_pending_by_conversation_context_phone(
                tenant_id=tenant_id,
                sender_phone_variants=sender_phone_variants,
                now=now_local,
            )
        if not appointment:
            return {"processed": False, "reason": "pending_appointment_not_found"}

        phone_to_reply = self._resolve_reply_phone(
            tenant_id=tenant_id,
            appointment=appointment,
            sender_phone=sender_phone,
            sender_phone_variants=sender_phone_variants,
        )

        related = self.appointment_repo.get_by_id_with_relations(
            tenant_id=tenant_id,
            appointment_id=appointment.id,
        )

        self.appointment_repo.update(
            tenant_id,
            appointment.id,
            status=AppointmentStatus.RESCHEDULE_REQ,
            last_notification_type="none",
            whatsapp_remote_id=reply_jid or remote_jid or appointment.whatsapp_remote_id,
        )

        self._persist_client_lid_if_available(
            tenant_id=tenant_id,
            appointment=appointment,
            remote_lid=remote_lid,
        )
        service_name = related.service_name if related else "tu servicio"
        available_hours = self.variable_resolver.hours_available_today(tenant_id=tenant_id)
        business_link = f"{self.settings.FRONTEND_URL.rstrip('/')}/owner/dashboard"

        await self._safe_send_text(
            instance_name=tenant.whatsapp_instance_id,
            tenant_apikey=tenant.whatsapp_apikey or self.settings.EVOLUTION_API_KEY,
            phone=phone_to_reply,
            text=(
                f"Soy Kibo, el asistente de {tenant.name}. "
                f"Para reagendar {service_name}, usa este link: {business_link}. "
                f"Hoy tenemos disponible: {available_hours}."
            ),
        )

        return {
            "processed": True,
            "status": "success",
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
            note_payload = (
                f"KIBO_PENDING_OFFER|appointment_id={appointment_id}|target_phone={waitlist_item.client_phone}"
            )
            self.waitlist_repo.update_notes(tenant_id, waitlist_item.id, note_payload)
            if tenant.phone:
                await self._safe_send_text(
                    instance_name=tenant.whatsapp_instance_id,
                    tenant_apikey=tenant.whatsapp_apikey or self.settings.EVOLUTION_API_KEY,
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
                    tenant_apikey=tenant.whatsapp_apikey or self.settings.EVOLUTION_API_KEY,
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
            tenant_apikey=tenant.whatsapp_apikey or self.settings.EVOLUTION_API_KEY,
            phone=waitlist_phone,
            text=(f"Hola {waitlist_name}. Se libero un espacio. " "Quieres tomarlo? Responde 1 para agendar."),
        )

        if tenant.phone:
            await self._safe_send_text(
                instance_name=tenant.whatsapp_instance_id,
                tenant_apikey=tenant.whatsapp_apikey or self.settings.EVOLUTION_API_KEY,
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
                tenant_apikey=tenant.whatsapp_apikey or self.settings.EVOLUTION_API_KEY,
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
                tenant_apikey=tenant.whatsapp_apikey or self.settings.EVOLUTION_API_KEY,
                phone=tenant.phone,
                text=f"{waitlist_item.client_name} acepto el espacio y ya fue agendado.",
            )

        await self._safe_send_text(
            instance_name=tenant.whatsapp_instance_id,
            tenant_apikey=tenant.whatsapp_apikey or self.settings.EVOLUTION_API_KEY,
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
            tenant_apikey=tenant.whatsapp_apikey or self.settings.EVOLUTION_API_KEY,
            phone=sender_phone,
            text=message,
        )

    async def _safe_send_text(
        self,
        *,
        instance_name: str | None,
        tenant_apikey: str | None,
        phone: str,
        text: str,
    ) -> None:
        if not instance_name or not tenant_apikey:
            logger.warning(
                "WhatsApp send skipped: instance=%s has missing credentials (tenant_apikey and EVOLUTION_API_KEY)",
                instance_name,
            )
            return
        try:
            normalized_phone = "".join(ch for ch in phone if ch.isdigit())
            target_phone = normalized_phone or phone
            await self.evolution_client.send_message(
                tenant_instance_id=instance_name,
                tenant_apikey=tenant_apikey,
                target_number=target_phone,
                text=text,
            )
        except EvolutionClientError as exc:
            logger.warning(
                "WhatsApp send failed: instance=%s phone=%s error=%s",
                instance_name,
                phone,
                exc,
            )

    def _resolve_reply_phone(
        self,
        *,
        tenant_id: uuid.UUID,
        appointment: Appointment,
        sender_phone: str,
        sender_phone_variants: set[str] | None,
    ) -> str:
        client = self.client_repo.get_by_id(tenant_id, appointment.client_id)
        if client and client.phone:
            client_digits = _normalize_digits(client.phone)
            if client_digits:
                return client_digits

        remote_digits = _normalize_digits(appointment.whatsapp_remote_id)
        if remote_digits:
            return remote_digits

        return sender_phone

    @staticmethod
    def _resolve_reply_jid(
        *,
        sender_pn_jid: str | None,
        sender_jid: str | None,
        remote_jid: str | None,
    ) -> str | None:
        for candidate in (sender_pn_jid, sender_jid):
            if isinstance(candidate, str) and candidate and not candidate.endswith("@lid"):
                return candidate
        if isinstance(remote_jid, str) and remote_jid and not remote_jid.endswith("@lid"):
            return remote_jid
        return None

    def _persist_client_lid_if_available(
        self,
        *,
        tenant_id: uuid.UUID,
        appointment: Appointment,
        remote_lid: str | None,
    ) -> None:
        if not remote_lid or not remote_lid.endswith("@lid"):
            return

        client = self.client_repo.get_by_id(tenant_id, appointment.client_id)
        if not client:
            return

        current_lid = client.whatsapp_lid or ""
        if current_lid == remote_lid:
            return

        self.client_repo.update(
            tenant_id,
            client.id,
            whatsapp_lid=remote_lid,
        )
        logger.info(
            "[WH_MATCH] Stored client whatsapp_lid: tenant=%s client=%s lid=%s",
            tenant_id,
            client.id,
            remote_lid,
        )

    def _has_multiple_pending_candidates(
        self,
        *,
        tenant_id: uuid.UUID,
        sender_phone: str,
        sender_name: str | None,
        sender_phone_variants: set[str] | None,
    ) -> bool:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            return False

        now_local = now_for_timezone(tenant.timezone_identifier)
        appointments = self.appointment_repo.list_by_tenant(tenant_id)

        target_variants = sender_phone_variants or _phone_variants(_normalize_digits(sender_phone))
        candidates: set[uuid.UUID] = set()

        for appt in appointments:
            if appt.status != AppointmentStatus.PENDING:
                continue
            if appt.appointment_date < now_local.date():
                continue
            if appt.appointment_date == now_local.date() and appt.time_start < now_local.time():
                continue

            client = self.client_repo.get_by_id(tenant_id, appt.client_id)
            if not client:
                continue

            client_digits = _normalize_digits(client.phone)
            client_variants = _phone_variants(client_digits) if client_digits else set()
            if target_variants and (target_variants & client_variants):
                candidates.add(appt.id)
                continue

            if sender_name and client.name and client.name.strip().lower() == sender_name.strip().lower():
                candidates.add(appt.id)

        return len(candidates) > 1

    @staticmethod
    def _scoped_message_id(*, message_id: str | None, tenant_id: uuid.UUID) -> str | None:
        if not message_id:
            return None
        return f"{tenant_id}:{message_id}"
