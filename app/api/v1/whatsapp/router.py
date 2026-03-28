import re
from typing import Annotated, Any
import uuid

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import check_plan_permission, require_owner
from app.db.session import get_db
from app.models.auth import User
from app.models.tenant import PlanTier
from app.schemas.whatsapp import (
    OutboxEnqueueRequest,
    OutboxStatsResponse,
    OutboxMessageResponse,
    WhatsAppInstanceResponse,
    WhatsAppLogoutResponse,
    WhatsAppQrResponse,
    WhatsAppStatusResponse,
    WebhookProcessResponse,
    WhatsAppWebhookResponse,
)
from app.services.whatsapp import WhatsAppConnectionService, WhatsAppOutboxService, WhatsAppWebhookService

router = APIRouter(tags=["whatsapp"])

OPTOUT_KEYWORDS = {"STOP", "NO", "BAJA"}


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^A-Z]", "", value.upper())


def _extract_instance_name(payload: dict[str, Any]) -> str | None:
    direct = payload.get("instance") or payload.get("instanceName")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    data = payload.get("data")
    if isinstance(data, dict):
        instance = data.get("instance") or data.get("instanceName")
        if isinstance(instance, str) and instance.strip():
            return instance.strip()

    instance_data = payload.get("instanceData")
    if isinstance(instance_data, dict):
        instance = instance_data.get("instanceName")
        if isinstance(instance, str) and instance.strip():
            return instance.strip()

    return None


def _extract_phone(payload: dict[str, Any]) -> str | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

    candidates = [
        payload.get("sender"),
        data.get("sender"),
        payload.get("phone"),
        payload.get("number"),
        payload.get("from"),
        payload.get("remoteJid"),
        payload.get("participant"),
        data.get("phone"),
        data.get("number"),
        data.get("from"),
        data.get("remoteJid"),
        data.get("participant"),
    ]

    message_data = data.get("message") if isinstance(data.get("message"), dict) else {}
    key_data = data.get("key") if isinstance(data.get("key"), dict) else {}
    candidates.extend(
        [
            message_data.get("from"),
            key_data.get("remoteJid"),
            key_data.get("participant"),
        ]
    )

    preferred_jid_digits: str | None = None
    fallback_digits: str | None = None

    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        lowered = candidate.lower()
        if "@lid" in lowered:
            continue
        digits = "".join(ch for ch in candidate if ch.isdigit())
        if not digits:
            continue

        if "@s.whatsapp.net" in lowered or "@c.us" in lowered:
            preferred_jid_digits = digits
            break

        if fallback_digits is None:
            fallback_digits = digits

    if preferred_jid_digits:
        return preferred_jid_digits
    if fallback_digits:
        return fallback_digits
    return None


def _extract_message_id(payload: dict[str, Any]) -> str | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    key_data = data.get("key") if isinstance(data.get("key"), dict) else {}
    candidates = [
        payload.get("messageId"),
        payload.get("message_id"),
        key_data.get("id"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _extract_text(payload: dict[str, Any]) -> str | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    message_data = data.get("message") if isinstance(data.get("message"), dict) else {}

    candidates = [
        payload.get("text"),
        payload.get("body"),
        data.get("text"),
        data.get("body"),
        message_data.get("conversation"),
        message_data.get("text"),
        message_data.get("extendedTextMessage", {}).get("text")
        if isinstance(message_data.get("extendedTextMessage"), dict)
        else None,
    ]

    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _extract_sender_name(payload: dict[str, Any]) -> str | None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    candidates = [
        payload.get("pushName"),
        payload.get("senderName"),
        data.get("pushName"),
        data.get("senderName"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _extract_event(payload: dict[str, Any]) -> str:
    event = payload.get("event") or payload.get("type")
    if isinstance(event, str) and event.strip():
        return event.strip()
    return "unknown"


def _is_messages_upsert_event(raw_event: str) -> bool:
    normalized = "".join(ch for ch in (raw_event or "").lower() if ch.isalnum())
    return normalized == "messagesupsert"


def _extract_from_me(payload: dict[str, Any]) -> bool:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    key_data = data.get("key") if isinstance(data.get("key"), dict) else {}

    candidates = [
        payload.get("fromMe"),
        data.get("fromMe"),
        key_data.get("fromMe"),
    ]
    for candidate in candidates:
        if isinstance(candidate, bool):
            return candidate
    return False


@router.get("/messaging/outbox/stats", response_model=OutboxStatsResponse)
def get_outbox_stats(
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
    _: Annotated[User, Depends(check_plan_permission(PlanTier.PRO))],
):
    service = WhatsAppOutboxService(db)
    stats = service.get_stats(business_id=owner_user.tenant_id)
    return OutboxStatsResponse(**stats)


@router.post("/whatsapp/create-instance", response_model=WhatsAppInstanceResponse)
async def create_whatsapp_instance(
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = WhatsAppConnectionService(db)
    result = await service.create_instance(tenant_id=owner_user.tenant_id)
    return WhatsAppInstanceResponse(**result)


@router.get("/whatsapp/get-qr", response_model=WhatsAppQrResponse)
async def get_whatsapp_qr(
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = WhatsAppConnectionService(db)
    result = await service.get_qr(tenant_id=owner_user.tenant_id)
    return WhatsAppQrResponse(**result)


@router.get("/whatsapp/status", response_model=WhatsAppStatusResponse)
async def get_whatsapp_status(
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = WhatsAppConnectionService(db)
    result = await service.get_status(tenant_id=owner_user.tenant_id)
    return WhatsAppStatusResponse(**result)


@router.delete("/whatsapp/logout", response_model=WhatsAppLogoutResponse)
async def logout_whatsapp_instance(
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = WhatsAppConnectionService(db)
    result = await service.logout(tenant_id=owner_user.tenant_id)
    return WhatsAppLogoutResponse(**result)


@router.post("/messaging/outbox/enqueue", response_model=dict)
def enqueue_message(
    payload: OutboxEnqueueRequest,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
    _: Annotated[User, Depends(check_plan_permission(PlanTier.PRO))],
):
    service = WhatsAppOutboxService(db)
    entity = service.queue_message(
        business_id=owner_user.tenant_id,
        phone=payload.phone,
        message_type=payload.message_type,
        variables=payload.variables,
    )
    return {"id": str(entity.id), "status": entity.status}


@router.get("/messaging/outbox/messages", response_model=list[OutboxMessageResponse])
def list_outbox_messages(
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
    _: Annotated[User, Depends(check_plan_permission(PlanTier.PRO))],
):
    service = WhatsAppOutboxService(db)
    messages = service.list_recent_messages(business_id=owner_user.tenant_id, limit=80)
    return [OutboxMessageResponse.model_validate(item) for item in messages]


@router.post("/messaging/outbox/{message_id}/retry", response_model=dict)
def retry_outbox_message(
    message_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
    _: Annotated[User, Depends(check_plan_permission(PlanTier.PRO))],
):
    service = WhatsAppOutboxService(db)
    retried = service.retry_message(business_id=owner_user.tenant_id, message_id=message_id)
    if not retried:
        return {"ok": False, "message": "Message not found"}
    return {"ok": True, "id": str(retried.id), "status": retried.status}


@router.post("/webhooks/evolution", response_model=WebhookProcessResponse)
async def evolution_webhook(
    db: Annotated[Session, Depends(get_db)],
    payload: dict[str, Any] = Body(default_factory=dict),
):
    event = _extract_event(payload)
    # Backward-compatible behavior: if Evolution is still pointing to this endpoint,
    # process inbound interactive replies here as well.
    if _is_messages_upsert_event(event) and not _extract_from_me(payload):
        instance_name = _extract_instance_name(payload)
        phone = _extract_phone(payload)
        incoming_text = _extract_text(payload)
        if instance_name and phone and incoming_text:
            webhook_service = WhatsAppWebhookService(db)
            await webhook_service.process_incoming_message(
                instance_name=instance_name,
                sender_phone=phone,
                text=incoming_text,
                message_id=_extract_message_id(payload),
                sender_name=_extract_sender_name(payload),
            )
            return WebhookProcessResponse(
                matched_keyword=False,
                opt_out_applied=False,
                reason="message_processed",
            )

    service = WhatsAppOutboxService(db)

    incoming_text = _extract_text(payload)
    normalized = _normalize_text(incoming_text)
    if normalized not in OPTOUT_KEYWORDS:
        return WebhookProcessResponse(matched_keyword=False, opt_out_applied=False, reason="keyword_not_matched")

    instance_name = _extract_instance_name(payload)
    if not instance_name:
        return WebhookProcessResponse(matched_keyword=True, opt_out_applied=False, reason="instance_missing")

    tenant = service.get_tenant_by_instance_name(instance_name=instance_name)
    if not tenant:
        return WebhookProcessResponse(matched_keyword=True, opt_out_applied=False, reason="business_not_found")

    phone = _extract_phone(payload)
    if not phone:
        return WebhookProcessResponse(matched_keyword=True, opt_out_applied=False, reason="phone_missing")

    applied = service.apply_opt_out(business_id=tenant.id, phone=phone)
    if not applied:
        return WebhookProcessResponse(matched_keyword=True, opt_out_applied=False, reason="client_not_found")

    return WebhookProcessResponse(matched_keyword=True, opt_out_applied=True, reason=None)


@router.post("/webhooks/whatsapp", response_model=WhatsAppWebhookResponse)
async def whatsapp_webhook(
    db: Annotated[Session, Depends(get_db)],
    payload: dict[str, Any] = Body(default_factory=dict),
):
    event = _extract_event(payload)
    if not _is_messages_upsert_event(event):
        return WhatsAppWebhookResponse(
            event=event,
            processed=False,
            reason="event_ignored",
        )

    if _extract_from_me(payload):
        return WhatsAppWebhookResponse(
            event=event,
            processed=False,
            reason="outgoing_message_ignored",
        )

    instance_name = _extract_instance_name(payload)
    phone = _extract_phone(payload)
    incoming_text = _extract_text(payload)
    if not instance_name or not phone or not incoming_text:
        return WhatsAppWebhookResponse(
            event=event,
            processed=False,
            reason="missing_fields",
        )

    message_id = _extract_message_id(payload)
    sender_name = _extract_sender_name(payload)

    service = WhatsAppWebhookService(db)
    try:
        result = await service.process_incoming_message(
            instance_name=instance_name,
            sender_phone=phone,
            text=incoming_text,
            message_id=message_id,
            sender_name=sender_name,
        )
    except Exception:  # noqa: BLE001
        return WhatsAppWebhookResponse(
            event=event,
            processed=False,
            reason="internal_error",
        )

    return WhatsAppWebhookResponse(
        event=event,
        processed=bool(result.get("processed")),
        flow=result.get("flow"),
        action=result.get("action"),
        reason=result.get("reason"),
        appointment_id=result.get("appointment_id"),
        waitlist_triggered=result.get("waitlist_triggered"),
        horas_disponibles_hoy=result.get("horas_disponibles_hoy"),
    )
