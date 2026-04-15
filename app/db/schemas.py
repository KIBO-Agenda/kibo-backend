from os import getenv


def _resolve_schema(name: str, *, default: str) -> str | None:
    raw = getenv(name, default)
    normalized = raw.strip()
    return normalized or None


WHATSAPP_SCHEMA = _resolve_schema("WHATSAPP_DB_SCHEMA", default="whatsapp")
