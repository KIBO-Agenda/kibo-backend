from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.whatsapp.outbox_service import WhatsAppOutboxService

logger = logging.getLogger(__name__)


async def run_outbox_worker(stop_event: asyncio.Event) -> None:
    settings = get_settings()

    while not stop_event.is_set():
        try:
            db = SessionLocal()
            try:
                service = WhatsAppOutboxService(db)
                processed = await service.process_pending_messages(
                    limit=20,
                    jitter_min_seconds=settings.WHATSAPP_WORKER_JITTER_MIN_SECONDS,
                    jitter_max_seconds=settings.WHATSAPP_WORKER_JITTER_MAX_SECONDS,
                    max_attempts=3,
                    retry_base_seconds=30,
                )
                if processed:
                    logger.info("Processed whatsapp outbox messages", extra={"count": processed})
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Outbox worker iteration failed: %s", exc)

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=max(1, settings.WHATSAPP_WORKER_POLL_SECONDS),
            )
        except TimeoutError:
            continue
