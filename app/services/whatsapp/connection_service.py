from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.timezone import now_bogota
from app.models.tenant import Tenant
from app.repositories.tenant import TenantRepository
from app.repositories.whatsapp_sessions import WhatsAppSessionRepository
from app.services.whatsapp.evolution_client import EvolutionClient, EvolutionClientError


def _normalize_status(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in {"open", "connected"}:
        return "connected"
    if value in {"connecting"}:
        return "connecting"
    if value in {"qr", "qr_required"}:
        return "qr_required"
    return "disconnected"


def _extract_state(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("state"),
        payload.get("status"),
        payload.get("instance", {}).get("state") if isinstance(payload.get("instance"), dict) else None,
        payload.get("instance", {}).get("status") if isinstance(payload.get("instance"), dict) else None,
        payload.get("data", {}).get("state") if isinstance(payload.get("data"), dict) else None,
        payload.get("data", {}).get("status") if isinstance(payload.get("data"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return "disconnected"


def _extract_phone(payload: dict[str, Any]) -> str | None:
    candidates = [
        payload.get("number"),
        payload.get("phone"),
        payload.get("instance", {}).get("number") if isinstance(payload.get("instance"), dict) else None,
        payload.get("instance", {}).get("phone") if isinstance(payload.get("instance"), dict) else None,
        payload.get("data", {}).get("number") if isinstance(payload.get("data"), dict) else None,
        payload.get("data", {}).get("phone") if isinstance(payload.get("data"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None


def _extract_qr_base64(payload: dict[str, Any]) -> str | None:
    candidates = [
        payload.get("qrcode"),
        payload.get("qr"),
        payload.get("base64"),
        payload.get("code"),
        payload.get("data", {}).get("qrcode") if isinstance(payload.get("data"), dict) else None,
        payload.get("data", {}).get("qr") if isinstance(payload.get("data"), dict) else None,
        payload.get("data", {}).get("base64") if isinstance(payload.get("data"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            value = candidate.strip()
            if value.startswith("data:image"):
                return value
            return f"data:image/png;base64,{value}"
    return None


class WhatsAppConnectionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.tenant_repo = TenantRepository(db)
        self.session_repo = WhatsAppSessionRepository(db)
        self.evolution_client = EvolutionClient()

    def _instance_name_for_tenant(self, tenant: Tenant) -> str:
        return tenant.whatsapp_instance_id or str(tenant.id)

    async def create_instance(self, *, tenant_id: uuid.UUID) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        instance_name = self._instance_name_for_tenant(tenant)

        try:
            payload = await self.evolution_client.create_instance(instance_name=instance_name)
        except EvolutionClientError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

        self.tenant_repo.set_whatsapp_instance_id(tenant_id, instance_name)
        self.session_repo.upsert_status(
            tenant_id=tenant_id,
            instance_name=instance_name,
            status="connecting",
            last_seen_at=now_bogota(),
        )

        return {
            "instance_name": instance_name,
            "status": payload.get("status", "created"),
        }

    async def get_qr(self, *, tenant_id: uuid.UUID) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        instance_name = self._instance_name_for_tenant(tenant)

        try:
            payload = await self.evolution_client.get_qr_code(instance_name=instance_name)
        except EvolutionClientError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

        qr_base64 = _extract_qr_base64(payload)
        if not qr_base64:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Evolution API did not return QR data",
            )

        self.session_repo.upsert_status(
            tenant_id=tenant_id,
            instance_name=instance_name,
            status="qr_required",
            last_seen_at=now_bogota(),
        )

        return {
            "instance_name": instance_name,
            "qr_base64": qr_base64,
        }

    async def get_status(self, *, tenant_id: uuid.UUID) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        instance_name = tenant.whatsapp_instance_id
        if not instance_name:
            return {
                "instance_name": None,
                "status": "disconnected",
                "connected": False,
                "phone": None,
            }

        try:
            payload = await self.evolution_client.get_connection_state(instance_name=instance_name)
        except EvolutionClientError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

        status_normalized = _normalize_status(_extract_state(payload))
        self.session_repo.upsert_status(
            tenant_id=tenant_id,
            instance_name=instance_name,
            status=status_normalized,
            last_seen_at=now_bogota(),
        )

        return {
            "instance_name": instance_name,
            "status": status_normalized,
            "connected": status_normalized == "connected",
            "phone": _extract_phone(payload),
        }

    async def logout(self, *, tenant_id: uuid.UUID) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        instance_name = tenant.whatsapp_instance_id
        if not instance_name:
            return {"ok": True, "instance_name": None, "status": "already_disconnected"}

        try:
            _ = await self.evolution_client.logout_instance(instance_name=instance_name)
        except EvolutionClientError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

        self.tenant_repo.set_whatsapp_instance_id(tenant_id, None)
        self.session_repo.upsert_status(
            tenant_id=tenant_id,
            instance_name=instance_name,
            status="disconnected",
            last_seen_at=now_bogota(),
        )

        return {
            "ok": True,
            "instance_name": instance_name,
            "status": "disconnected",
        }
