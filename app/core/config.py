from functools import lru_cache
from os import getenv

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    APP_NAME: str = getenv("APP_NAME", "Agenda Backend")
    API_V1_PREFIX: str = getenv("API_V1_PREFIX", "/api/v1")
    DATABASE_URL: str = getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:root@localhost:5432/agenda",
    )
    DEBUG: bool = getenv("DEBUG", "false").lower() == "true"
    JWT_SECRET_KEY: str = getenv("JWT_SECRET_KEY", "change-this-secret")
    JWT_ALGORITHM: str = getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = int(
        getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
    )
    BACKEND_CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in getenv("BACKEND_CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
