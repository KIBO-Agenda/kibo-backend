from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
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
        self.settings = get_settings()
        self.tenant_repo = TenantRepository(db)
        self.session_repo = WhatsAppSessionRepository(db)
        self.evolution_client = EvolutionClient()

    def _resolve_tenant_apikey(self, tenant: Tenant) -> str | None:
        api_key = tenant.whatsapp_apikey or self.settings.EVOLUTION_API_KEY
        if not tenant.whatsapp_apikey and self.settings.EVOLUTION_API_KEY:
            self.tenant_repo.update(tenant.id, whatsapp_apikey=self.settings.EVOLUTION_API_KEY)
        return api_key

    def _candidate_api_keys(self, tenant: Tenant) -> list[str]:
        candidates: list[str] = []
        if tenant.whatsapp_apikey:
            candidates.append(tenant.whatsapp_apikey)
        if self.settings.EVOLUTION_API_KEY and self.settings.EVOLUTION_API_KEY not in candidates:
            candidates.append(self.settings.EVOLUTION_API_KEY)
        return candidates

    @staticmethod
    def _is_auth_error(exc: EvolutionClientError) -> bool:
        message = str(exc).lower()
        return "403" in message or "401" in message or "forbidden" in message or "unauthorized" in message

    async def _execute_with_apikey_fallback(
        self,
        *,
        tenant: Tenant,
        operation: Callable[[str], Awaitable[Any]],
    ) -> Any:
        api_keys = self._candidate_api_keys(tenant)
        self._ensure_apikey_or_400(api_keys[0] if api_keys else None)

        last_exc: EvolutionClientError | None = None
        for index, api_key in enumerate(api_keys):
            try:
                payload = await operation(api_key)
                if tenant.whatsapp_apikey != api_key:
                    self.tenant_repo.update(tenant.id, whatsapp_apikey=api_key)
                return payload
            except EvolutionClientError as exc:
                last_exc = exc
                has_next = index + 1 < len(api_keys)
                if has_next and self._is_auth_error(exc):
                    continue
                raise

        if last_exc:
            raise last_exc
        raise EvolutionClientError("Evolution API key resolution failed")

    @staticmethod
    def _ensure_apikey_or_400(api_key: str | None) -> str:
        if api_key:
            return api_key
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "WhatsApp API key is missing for this tenant. "
                "Set tenant.whatsapp_apikey in tenant settings or configure EVOLUTION_API_KEY."
            ),
        )

    def _instance_name_for_tenant(self, tenant: Tenant) -> str:
        return tenant.whatsapp_instance_id or str(tenant.id)

    async def create_instance(self, *, tenant_id: uuid.UUID) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        instance_name = self._instance_name_for_tenant(tenant)
        try:
            payload = await self._execute_with_apikey_fallback(
                tenant=tenant,
                operation=lambda api_key: self.evolution_client.create_instance(
                    instance_name=instance_name,
                    api_key=api_key,
                ),
            )
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

        # Keep legacy instances and recreated instances aligned with inbound callback expectations.
        try:
            await self._execute_with_apikey_fallback(
                tenant=tenant,
                operation=lambda api_key: self.evolution_client.ensure_webhook(
                    instance_name=instance_name,
                    api_key=api_key,
                ),
            )
        except EvolutionClientError:
            # Instance creation should still succeed even if webhook sync is temporarily unavailable.
            pass

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
            payload = await self._execute_with_apikey_fallback(
                tenant=tenant,
                operation=lambda api_key: self.evolution_client.get_qr_code(
                    instance_name=instance_name,
                    api_key=api_key,
                ),
            )
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
            payload = await self._execute_with_apikey_fallback(
                tenant=tenant,
                operation=lambda api_key: self.evolution_client.get_connection_state(
                    instance_name=instance_name,
                    api_key=api_key,
                ),
            )
        except EvolutionClientError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

        try:
            await self._execute_with_apikey_fallback(
                tenant=tenant,
                operation=lambda api_key: self.evolution_client.ensure_webhook(
                    instance_name=instance_name,
                    api_key=api_key,
                ),
            )
        except EvolutionClientError:
            # Do not fail status polling if webhook reconciliation is unavailable.
            pass

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
            _ = await self._execute_with_apikey_fallback(
                tenant=tenant,
                operation=lambda api_key: self.evolution_client.logout_instance(
                    instance_name=instance_name,
                    api_key=api_key,
                ),
            )
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

    async def sync_webhook(self, *, tenant_id: uuid.UUID) -> dict[str, Any]:
        tenant = self.tenant_repo.get_by_id(tenant_id)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        instance_name = tenant.whatsapp_instance_id
        if not instance_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="WhatsApp instance not configured",
            )

        try:
            await self._execute_with_apikey_fallback(
                tenant=tenant,
                operation=lambda api_key: self.evolution_client.ensure_webhook(
                    instance_name=instance_name,
                    api_key=api_key,
                ),
            )
        except EvolutionClientError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

        return {
            "ok": True,
            "instance_name": instance_name,
            "webhook_url": self.evolution_client.settings.EVOLUTION_WEBHOOK_URL,
        }
