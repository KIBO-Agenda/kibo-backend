from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import httpx

from app.core.config import get_settings


class EvolutionClientError(RuntimeError):
    pass


class EvolutionClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        digits = re.sub(r"\D", "", phone)
        # Assume CO mobile local format when 10 digits start with 3.
        if len(digits) == 10 and digits.startswith("3"):
            return f"57{digits}"
        return digits

    def _get_client(self, *, api_key: str | None = None) -> httpx.AsyncClient:
        base_url = self.settings.EVOLUTION_API_BASE_URL
        resolved_api_key = api_key or self.settings.EVOLUTION_API_KEY
        if not base_url or not resolved_api_key:
            raise EvolutionClientError("Evolution API is not configured")

        headers = {"apikey": resolved_api_key, "Content-Type": "application/json"}
        return httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers, timeout=20.0)

    def _webhook_payload(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "url": self.settings.EVOLUTION_WEBHOOK_URL,
            "events": ["MESSAGES_UPSERT"],
            "byEvents": False,
            "base64": False,
        }

    @staticmethod
    def _stringify_error_detail(detail: Any) -> str:
        if isinstance(detail, str):
            return detail
        if isinstance(detail, list):
            values = [item for item in detail if isinstance(item, str)]
            return "; ".join(values)
        if isinstance(detail, Mapping):
            nested = detail.get("message") or detail.get("error") or detail.get("response")
            if nested is not None:
                return EvolutionClient._stringify_error_detail(nested)
            return str(dict(detail))
        return str(detail)

    @staticmethod
    def _extract_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            return response.text[:500]

        if isinstance(payload, Mapping):
            detail = payload.get("message") or payload.get("response") or payload.get("error")
            if detail is not None:
                return EvolutionClient._stringify_error_detail(detail)
        return str(payload)

    @staticmethod
    def _is_instance_already_in_use(message: str) -> bool:
        lowered = message.lower()
        return ("already" in lowered and ("instance" in lowered or "name" in lowered)) or "already in use" in lowered

    async def create_instance(self, *, instance_name: str, api_key: str | None = None) -> dict[str, Any]:
        payload = {
            "instanceName": instance_name,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
            "webhook": self._webhook_payload(),
        }

        async with self._get_client(api_key=api_key) as client:
            try:
                response = await client.post("/instance/create", json=payload)
            except httpx.HTTPError as exc:
                raise EvolutionClientError(f"Evolution API unavailable: {exc}") from exc
            if response.status_code < 400:
                body = response.json()
                return body if isinstance(body, dict) else {"raw": body}

            message = self._extract_message(response)
            if self._is_instance_already_in_use(message):
                return {"instance": {"instanceName": instance_name}, "status": "already_exists"}

            raise EvolutionClientError(f"Failed to create instance ({response.status_code}): {message}")

    async def find_webhook(self, *, instance_name: str, api_key: str | None = None) -> dict[str, Any] | None:
        async with self._get_client(api_key=api_key) as client:
            try:
                response = await client.get(f"/webhook/find/{instance_name}")
            except httpx.HTTPError as exc:
                raise EvolutionClientError(f"Evolution API unavailable: {exc}") from exc

            if response.status_code == 404:
                return None
            if response.status_code >= 400:
                raise EvolutionClientError(
                    f"Failed to get webhook config ({response.status_code}): {self._extract_message(response)}"
                )

            body = response.json()
            if body is None:
                return None
            return dict(body) if isinstance(body, Mapping) else None

    async def set_webhook(self, *, instance_name: str, api_key: str | None = None) -> dict[str, Any]:
        payload = {"webhook": self._webhook_payload()}
        async with self._get_client(api_key=api_key) as client:
            try:
                response = await client.post(f"/webhook/set/{instance_name}", json=payload)
            except httpx.HTTPError as exc:
                raise EvolutionClientError(f"Evolution API unavailable: {exc}") from exc

            if response.status_code >= 400:
                raise EvolutionClientError(
                    f"Failed to set webhook ({response.status_code}): {self._extract_message(response)}"
                )

            body = response.json()
            return dict(body) if isinstance(body, Mapping) else {"raw": body}

    async def ensure_webhook(self, *, instance_name: str, api_key: str | None = None) -> None:
        webhook = await self.find_webhook(instance_name=instance_name, api_key=api_key)
        expected_url = self.settings.EVOLUTION_WEBHOOK_URL
        if webhook and webhook.get("enabled") is True:
            current_url = webhook.get("url")
            events = webhook.get("events")
            if (
                isinstance(current_url, str)
                and current_url == expected_url
                and isinstance(events, list)
                and "MESSAGES_UPSERT" in events
            ):
                return

        await self.set_webhook(instance_name=instance_name, api_key=api_key)

    async def get_qr_code(self, *, instance_name: str, api_key: str | None = None) -> dict[str, Any]:
        attempts = [
            ("GET", f"/instance/connect/{instance_name}"),
            ("GET", f"/instance/qrcode/{instance_name}"),
        ]

        async with self._get_client(api_key=api_key) as client:
            last_error = ""
            for method, path in attempts:
                try:
                    response = await client.request(method, path)
                except httpx.HTTPError as exc:
                    raise EvolutionClientError(f"Evolution API unavailable: {exc}") from exc
                if response.status_code < 400:
                    body = response.json()
                    return body if isinstance(body, dict) else {"raw": body}
                last_error = f"{response.status_code}: {self._extract_message(response)}"

            raise EvolutionClientError(f"Failed to get QR code: {last_error}")

    async def get_connection_state(self, *, instance_name: str, api_key: str | None = None) -> dict[str, Any]:
        attempts = [
            ("GET", f"/instance/connectionState/{instance_name}"),
            ("GET", f"/instance/connection-state/{instance_name}"),
        ]

        async with self._get_client(api_key=api_key) as client:
            last_error = ""
            for method, path in attempts:
                try:
                    response = await client.request(method, path)
                except httpx.HTTPError as exc:
                    raise EvolutionClientError(f"Evolution API unavailable: {exc}") from exc
                if response.status_code < 400:
                    body = response.json()
                    return body if isinstance(body, dict) else {"raw": body}
                last_error = f"{response.status_code}: {self._extract_message(response)}"

            raise EvolutionClientError(f"Failed to get instance status: {last_error}")

    async def logout_instance(self, *, instance_name: str, api_key: str | None = None) -> dict[str, Any]:
        attempts = [
            ("DELETE", f"/instance/logout/{instance_name}"),
            ("DELETE", f"/instance/delete/{instance_name}"),
            ("POST", f"/instance/logout/{instance_name}"),
            ("POST", f"/instance/delete/{instance_name}"),
        ]

        async with self._get_client(api_key=api_key) as client:
            last_error = ""
            for method, path in attempts:
                try:
                    response = await client.request(method, path)
                except httpx.HTTPError as exc:
                    raise EvolutionClientError(f"Evolution API unavailable: {exc}") from exc
                if response.status_code < 400:
                    body = response.json() if response.content else {"ok": True}
                    return body if isinstance(body, dict) else {"raw": body}

                # Some Evolution versions return 404 when instance does not exist; treat as logged out.
                if response.status_code == 404:
                    return {"ok": True, "status": "not_found"}

                last_error = f"{response.status_code}: {self._extract_message(response)}"

            raise EvolutionClientError(f"Failed to logout/delete instance: {last_error}")

    async def send_text(
        self,
        *,
        instance_name: str,
        phone: str,
        text: str,
        api_key: str | None = None,
    ) -> dict:
        normalized_phone = self._normalize_phone(phone)
        if not normalized_phone:
            raise EvolutionClientError("Invalid recipient phone")

        payload_attempts = [
            {"number": normalized_phone, "text": text},
            {"phone": normalized_phone, "message": text},
        ]

        async with self._get_client(api_key=api_key) as client:
            for payload in payload_attempts:
                try:
                    response = await client.post(f"/message/sendText/{instance_name}", json=payload)
                except httpx.HTTPError as exc:
                    raise EvolutionClientError(f"Evolution API unavailable: {exc}") from exc
                if response.status_code < 400:
                    body = response.json()
                    if isinstance(body, Mapping):
                        return dict(body)
                    return {"raw": body}

            raise EvolutionClientError(
                f"Failed to send message via Evolution API ({response.status_code}): {self._extract_message(response)}"
            )

    async def send_message(
        self,
        *,
        tenant_instance_id: str,
        tenant_apikey: str,
        target_number: str,
        text: str,
    ) -> dict:
        if not tenant_apikey:
            raise EvolutionClientError("Tenant Evolution API key is missing")

        normalized_phone = self._normalize_phone(target_number)
        if not normalized_phone:
            raise EvolutionClientError("Invalid recipient phone")

        payload_attempts = [
            {"number": normalized_phone, "text": text},
            {"phone": normalized_phone, "message": text},
        ]

        async with self._get_client(api_key=tenant_apikey) as client:
            for payload in payload_attempts:
                try:
                    response = await client.post(f"/message/sendText/{tenant_instance_id}", json=payload)
                except httpx.HTTPError as exc:
                    raise EvolutionClientError(f"Evolution API unavailable: {exc}") from exc
                if response.status_code < 400:
                    body = response.json()
                    if isinstance(body, Mapping):
                        return dict(body)
                    return {"raw": body}

            raise EvolutionClientError(
                f"Failed to send message via Evolution API ({response.status_code}): {self._extract_message(response)}"
            )
