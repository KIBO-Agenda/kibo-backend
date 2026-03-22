import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import require_owner
from app.db.session import get_db
from app.models.auth import User
from app.schemas.whatsapp import (
    OutboxEnqueueRequest,
    OutboxStatsResponse,
    WebhookProcessResponse,
)
from app.services.whatsapp import WhatsAppOutboxService

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
        payload.get("phone"),
        payload.get("number"),
        payload.get("from"),
        data.get("phone"),
        data.get("number"),
        data.get("from"),
        data.get("remoteJid"),
    ]

    message_data = data.get("message") if isinstance(data.get("message"), dict) else {}
    key_data = data.get("key") if isinstance(data.get("key"), dict) else {}
    candidates.extend([message_data.get("from"), key_data.get("remoteJid")])

    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        digits = "".join(ch for ch in candidate if ch.isdigit())
        if digits:
            return digits
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


@router.get("/messaging/outbox/stats", response_model=OutboxStatsResponse)
def get_outbox_stats(
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = WhatsAppOutboxService(db)
    stats = service.get_stats(business_id=owner_user.tenant_id)
    return OutboxStatsResponse(**stats)


@router.post("/messaging/outbox/enqueue", response_model=dict)
def enqueue_message(
    payload: OutboxEnqueueRequest,
    db: Annotated[Session, Depends(get_db)],
    owner_user: Annotated[User, Depends(require_owner)],
):
    service = WhatsAppOutboxService(db)
    entity = service.queue_message(
        business_id=owner_user.tenant_id,
        phone=payload.phone,
        message_type=payload.message_type,
        variables=payload.variables,
    )
    return {"id": str(entity.id), "status": entity.status}


@router.post("/webhooks/evolution", response_model=WebhookProcessResponse)
def evolution_webhook(
    db: Annotated[Session, Depends(get_db)],
    payload: dict[str, Any] = Body(default_factory=dict),
):
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
