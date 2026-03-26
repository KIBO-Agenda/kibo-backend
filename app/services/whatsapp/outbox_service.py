from __future__ import annotations

import asyncio
import random
import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.timezone import now_bogota
from app.core.dependencies import has_min_plan_tier
from app.models.tenant import PlanTier, Tenant
from app.repositories.clients import ClientRepository
from app.repositories.tenant import TenantRepository
from app.repositories.whatsapp_outbox import WhatsAppOutboxRepository
from app.services.whatsapp.evolution_client import EvolutionClient
from app.services.whatsapp.template_engine import resolve_variables, select_variant


class WhatsAppOutboxService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.tenant_repo = TenantRepository(db)
        self.client_repo = ClientRepository(db)
        self.outbox_repo = WhatsAppOutboxRepository(db)
        self.evolution_client = EvolutionClient()

    @staticmethod
    def _build_idempotency_key(prefix: str = "wa") -> str:
        return f"{prefix}_{uuid.uuid4().hex}"

    def queue_message(
        self,
        *,
        business_id: uuid.UUID,
        phone: str,
        message_type: str,
        variables: dict,
        client_id: uuid.UUID | None = None,
        appointment_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
    ):
        tenant = self.tenant_repo.get_by_id(business_id)
        if not tenant:
            raise ValueError("Business not found")
        if not has_min_plan_tier(tenant.plan_tier, PlanTier.PRO):
            raise ValueError(
                "This feature is available in the pro plan. Please upgrade to continue."
            )

        template_index, template_text = select_variant(tenant.message_templates or {}, message_type)
        rendered = resolve_variables(template_text, variables)

        return self.outbox_repo.create(
            business_id=business_id,
            client_id=client_id,
            appointment_id=appointment_id,
            phone=phone,
            message_type=message_type,
            template_variant_index=template_index,
            rendered_text=rendered,
            variables=variables,
            idempotency_key=idempotency_key or self._build_idempotency_key(),
        )

    async def process_pending_messages(
        self,
        *,
        limit: int,
        jitter_min_seconds: int,
        jitter_max_seconds: int,
        max_attempts: int,
        retry_base_seconds: int,
    ) -> int:
        now = now_bogota()
        pending = self.outbox_repo.claim_pending_batch(now=now, limit=limit)
        if not pending:
            return 0

        processed = 0
        for message in pending:
            tenant = self.tenant_repo.get_by_id(message.business_id)
            if not tenant:
                self.outbox_repo.retry_or_fail(
                    message_id=message.id,
                    now=now,
                    error_message="Business not found",
                    max_attempts=max_attempts,
                    base_delay_seconds=retry_base_seconds,
                )
                continue

            if not tenant.whatsapp_instance_id:
                self.outbox_repo.retry_or_fail(
                    message_id=message.id,
                    now=now,
                    error_message="WhatsApp instance not configured",
                    max_attempts=max_attempts,
                    base_delay_seconds=retry_base_seconds,
                )
                continue

            client = None
            if message.client_id:
                client = self.client_repo.get_by_id(tenant.id, message.client_id)
            if client is None:
                client = self.client_repo.get_by_phone_normalized(tenant.id, message.phone)

            if client and client.whatsapp_opt_out:
                self.outbox_repo.mark_blocked_opt_out(
                    message_id=message.id,
                    error_message="Message blocked by client opt-out",
                )
                processed += 1
                continue

            if jitter_max_seconds > 0:
                jitter_seconds = random.randint(max(0, jitter_min_seconds), max(jitter_min_seconds, jitter_max_seconds))
                message.jitter_seconds = jitter_seconds
                self.db.commit()
                await asyncio.sleep(jitter_seconds)

            try:
                payload = await self.evolution_client.send_text(
                    instance_name=tenant.whatsapp_instance_id,
                    phone=message.phone,
                    text=message.rendered_text,
                )
                provider_message_id = None
                if isinstance(payload, dict):
                    provider_message_id = (
                        payload.get("key")
                        or payload.get("id")
                        or payload.get("messageId")
                    )

                self.outbox_repo.mark_sent(
                    message_id=message.id,
                    sent_at=now_bogota(),
                    provider_message_id=str(provider_message_id) if provider_message_id else None,
                    provider_payload=payload if isinstance(payload, dict) else {"raw": str(payload)},
                )
            except Exception as exc:  # noqa: BLE001
                self.outbox_repo.retry_or_fail(
                    message_id=message.id,
                    now=now_bogota() + timedelta(seconds=0),
                    error_message=str(exc)[:500],
                    max_attempts=max_attempts,
                    base_delay_seconds=retry_base_seconds,
                )

            processed += 1

        return processed

    def get_stats(self, *, business_id: uuid.UUID) -> dict[str, int]:
        return self.outbox_repo.count_by_status(business_id=business_id)

    def list_recent_messages(self, *, business_id: uuid.UUID, limit: int = 50):
        safe_limit = max(1, min(limit, 200))
        return self.outbox_repo.list_recent(business_id=business_id, limit=safe_limit)

    def retry_message(self, *, business_id: uuid.UUID, message_id: uuid.UUID):
        return self.outbox_repo.reset_for_retry(
            business_id=business_id,
            message_id=message_id,
            now=now_bogota(),
        )

    def apply_opt_out(self, *, business_id: uuid.UUID, phone: str) -> bool:
        client = self.client_repo.get_by_phone_normalized(business_id, phone)
        if not client:
            return False
        self.client_repo.set_whatsapp_opt_out(business_id, client.id, at=now_bogota())
        return True

    def get_tenant_by_instance_name(self, *, instance_name: str) -> Tenant | None:
        return self.tenant_repo.get_by_whatsapp_instance_id(instance_name)
