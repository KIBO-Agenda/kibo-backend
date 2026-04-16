from functools import lru_cache
from os import getenv

from dotenv import load_dotenv

load_dotenv()


def _parse_cors_origins(raw_origins: str | None, frontend_url: str) -> list[str]:
    if raw_origins is None:
        return [frontend_url]

    normalized = raw_origins.strip()
    if not normalized:
        return [frontend_url]

    if normalized == "*":
        return ["*"]

    origins = [origin.strip() for origin in normalized.split(",") if origin.strip()]
    return origins or [frontend_url]


class Settings:
    """Application settings loaded from environment variables."""

    APP_NAME: str = getenv("APP_NAME", "Agenda Backend")
    API_V1_PREFIX: str = getenv("API_V1_PREFIX", "/api/v1")
    BACKEND_BASE_URL: str = getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    DATABASE_URL: str = getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:root@localhost:5432/agenda",
    )
    DEFAULT_TIMEZONE: str = getenv("DEFAULT_TIMEZONE", "America/Bogota")
    WHATSAPP_WORKER_ENABLED: bool = getenv("WHATSAPP_WORKER_ENABLED", "false").lower() == "true"
    WHATSAPP_WORKER_POLL_SECONDS: int = int(getenv("WHATSAPP_WORKER_POLL_SECONDS", "10"))
    WHATSAPP_WORKER_JITTER_MIN_SECONDS: int = int(getenv("WHATSAPP_WORKER_JITTER_MIN_SECONDS", "5"))
    WHATSAPP_WORKER_JITTER_MAX_SECONDS: int = int(getenv("WHATSAPP_WORKER_JITTER_MAX_SECONDS", "15"))
    EVOLUTION_API_BASE_URL: str | None = getenv("EVOLUTION_API_BASE_URL") or getenv("WHATSAPP_API_URL")
    EVOLUTION_API_KEY: str | None = getenv("EVOLUTION_API_KEY") or getenv("WHATSAPP_API_KEY")
    EVOLUTION_WEBHOOK_URL: str = getenv(
        "EVOLUTION_WEBHOOK_URL",
        f"{BACKEND_BASE_URL}{API_V1_PREFIX}/webhooks/whatsapp",
    )
    DEBUG: bool = getenv("DEBUG", "false").lower() == "true"
    JWT_SECRET_KEY: str = getenv("JWT_SECRET_KEY", "change-this-secret")
    JWT_ALGORITHM: str = getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = int(getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    JWT_PASSWORD_RESET_EXPIRE_MINUTES: int = int(getenv("JWT_PASSWORD_RESET_EXPIRE_MINUTES", "30"))
    FRONTEND_URL: str = getenv("FRONTEND_URL", "http://localhost:3000")
    SMTP_HOST: str | None = getenv("SMTP_HOST")
    SMTP_PORT: int = int(getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str | None = getenv("SMTP_USERNAME")
    SMTP_PASSWORD: str | None = getenv("SMTP_PASSWORD")
    SMTP_USE_TLS: bool = getenv("SMTP_USE_TLS", "true").lower() == "true"
    SMTP_SENDER_EMAIL: str = getenv("SMTP_SENDER_EMAIL", "no-reply@agenda.local")
    BACKEND_CORS_ORIGINS: list[str] = _parse_cors_origins(
        getenv("BACKEND_CORS_ORIGINS"),
        FRONTEND_URL,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
