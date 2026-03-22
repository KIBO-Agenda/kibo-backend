from __future__ import annotations

import re
from collections.abc import Mapping

import httpx

from app.core.config import get_settings


class EvolutionClientError(RuntimeError):
    pass


class EvolutionClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        return re.sub(r"\D", "", phone)

    async def send_text(self, *, instance_name: str, phone: str, text: str) -> dict:
        base_url = self.settings.EVOLUTION_API_BASE_URL
        api_key = self.settings.EVOLUTION_API_KEY

        if not base_url or not api_key:
            raise EvolutionClientError("Evolution API is not configured")

        normalized_phone = self._normalize_phone(phone)
        if not normalized_phone:
            raise EvolutionClientError("Invalid recipient phone")

        headers = {"apikey": api_key, "Content-Type": "application/json"}
        payload_attempts = [
            {"number": normalized_phone, "text": text},
            {"phone": normalized_phone, "message": text},
        ]

        async with httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers, timeout=20.0) as client:
            for payload in payload_attempts:
                response = await client.post(f"/message/sendText/{instance_name}", json=payload)
                if response.status_code < 400:
                    body = response.json()
                    if isinstance(body, Mapping):
                        return dict(body)
                    return {"raw": body}

            raise EvolutionClientError(
                f"Failed to send message via Evolution API ({response.status_code}): {response.text[:500]}"
            )
