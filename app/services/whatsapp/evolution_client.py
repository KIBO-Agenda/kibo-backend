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

    def _get_client(self) -> httpx.AsyncClient:
        base_url = self.settings.EVOLUTION_API_BASE_URL
        api_key = self.settings.EVOLUTION_API_KEY
        if not base_url or not api_key:
            raise EvolutionClientError("Evolution API is not configured")

        headers = {"apikey": api_key, "Content-Type": "application/json"}
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
    def _extract_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            return response.text[:500]

        if isinstance(payload, Mapping):
            detail = payload.get("message") or payload.get("error") or payload.get("response")
            if isinstance(detail, str):
                return detail
            return str(detail)
        return str(payload)

    async def create_instance(self, *, instance_name: str) -> dict[str, Any]:
        payload = {
            "instanceName": instance_name,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
            "webhook": self._webhook_payload(),
        }

        async with self._get_client() as client:
            try:
                response = await client.post("/instance/create", json=payload)
            except httpx.HTTPError as exc:
                raise EvolutionClientError(f"Evolution API unavailable: {exc}") from exc
            if response.status_code < 400:
                body = response.json()
                return body if isinstance(body, dict) else {"raw": body}

            message = self._extract_message(response)
            lowered = message.lower()
            if "already" in lowered and "instance" in lowered:
                return {"instance": {"instanceName": instance_name}, "status": "already_exists"}

            raise EvolutionClientError(
                f"Failed to create instance ({response.status_code}): {message}"
            )

    async def find_webhook(self, *, instance_name: str) -> dict[str, Any] | None:
        async with self._get_client() as client:
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

    async def set_webhook(self, *, instance_name: str) -> dict[str, Any]:
        payload = {"webhook": self._webhook_payload()}
        async with self._get_client() as client:
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

    async def ensure_webhook(self, *, instance_name: str) -> None:
        webhook = await self.find_webhook(instance_name=instance_name)
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

        await self.set_webhook(instance_name=instance_name)

    async def get_qr_code(self, *, instance_name: str) -> dict[str, Any]:
        attempts = [
            ("GET", f"/instance/connect/{instance_name}"),
            ("GET", f"/instance/qrcode/{instance_name}"),
        ]

        async with self._get_client() as client:
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

    async def get_connection_state(self, *, instance_name: str) -> dict[str, Any]:
        attempts = [
            ("GET", f"/instance/connectionState/{instance_name}"),
            ("GET", f"/instance/connection-state/{instance_name}"),
        ]

        async with self._get_client() as client:
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

    async def logout_instance(self, *, instance_name: str) -> dict[str, Any]:
        attempts = [
            ("DELETE", f"/instance/logout/{instance_name}"),
            ("DELETE", f"/instance/delete/{instance_name}"),
            ("POST", f"/instance/logout/{instance_name}"),
            ("POST", f"/instance/delete/{instance_name}"),
        ]

        async with self._get_client() as client:
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

    async def send_text(self, *, instance_name: str, phone: str, text: str) -> dict:
        normalized_phone = self._normalize_phone(phone)
        if not normalized_phone:
            raise EvolutionClientError("Invalid recipient phone")

        payload_attempts = [
            {"number": normalized_phone, "text": text},
            {"phone": normalized_phone, "message": text},
        ]

        async with self._get_client() as client:
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
