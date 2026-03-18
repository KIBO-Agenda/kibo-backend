from functools import lru_cache
from os import getenv


class Settings:
    """Application settings loaded from environment variables."""

    APP_NAME: str = getenv("APP_NAME", "Agenda Backend")
    API_V1_PREFIX: str = getenv("API_V1_PREFIX", "/api/v1")
    DATABASE_URL: str = getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/agenda",
    )
    DEBUG: bool = getenv("DEBUG", "false").lower() == "true"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
