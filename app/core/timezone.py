from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BOGOTA_TZ = "America/Bogota"


def _resolve_timezone(timezone_identifier: str | None) -> ZoneInfo:
    candidate = timezone_identifier or BOGOTA_TZ
    try:
        return ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return ZoneInfo(BOGOTA_TZ)


def now_for_timezone(timezone_identifier: str | None) -> datetime:
    return datetime.now(_resolve_timezone(timezone_identifier))


def today_for_timezone(timezone_identifier: str | None) -> date:
    return now_for_timezone(timezone_identifier).date()


def now_bogota() -> datetime:
    return now_for_timezone(BOGOTA_TZ)
