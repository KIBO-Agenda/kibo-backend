from __future__ import annotations

import argparse
import asyncio
import uuid

from app.db.session import SessionLocal
from app.services.scheduler.reminder_scheduler import ReminderScheduler


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send reminder_24h to all tomorrow appointments regardless of missing hours.",
    )
    parser.add_argument(
        "--tenant-id",
        type=uuid.UUID,
        default=None,
        help="Optional tenant filter",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print eligible reminders",
    )
    parser.add_argument(
        "--respect-sent",
        action="store_true",
        help="Skip appointments already marked with reminder_24h_sent",
    )
    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()
    scheduler = ReminderScheduler(SessionLocal)
    result = await scheduler.process_tomorrow_reminders(
        force=not args.respect_sent,
        tenant_id=args.tenant_id,
        dry_run=args.dry_run,
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(_run())
