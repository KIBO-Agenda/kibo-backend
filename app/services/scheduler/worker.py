import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.db.session import get_db_sessionmaker
from app.services.scheduler.reminder_scheduler import ReminderScheduler

logger = logging.getLogger(__name__)
settings = get_settings()

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler | None:
    """Get the global APScheduler instance."""
    return _scheduler


async def start_scheduler() -> AsyncIOScheduler:
    """Initialize and start the APScheduler."""
    global _scheduler

    db_sessionmaker = get_db_sessionmaker()
    reminder_scheduler = ReminderScheduler(db_sessionmaker)

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        reminder_scheduler.process_reminders,
        trigger="interval",
        minutes=5,
        id="reminder_job",
        name="Process appointment reminders",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("Reminder scheduler started (interval: 5 minutes)")

    return _scheduler


async def stop_scheduler() -> None:
    """Stop the APScheduler."""
    global _scheduler

    if _scheduler:
        _scheduler.shutdown()
        logger.info("Reminder scheduler stopped")
        _scheduler = None


async def run_scheduler_lifecycle(stop_event: asyncio.Event) -> None:
    """Run scheduler until stop_event is set."""
    try:
        await start_scheduler()
        await stop_event.wait()
    finally:
        await stop_scheduler()
