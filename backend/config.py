"""
Central configuration for the IPAM backend (Phase 5.1).

One Settings object is the single source of truth for everything that can
change between environments: the database URL, CORS origins, SQL echo, and
the scan interval. Values come from real environment variables first, and
in local dev from backend/.env as a fallback.

Why this exists: a container is configured from the OUTSIDE (env vars), not
by editing source. The same image then runs unchanged on the laptop (DB host
= localhost) and inside docker compose (DB host = the 'postgres' service),
just with different env values. pydantic-settings also validates types and
fails LOUDLY at startup if a required value is missing, instead of blowing up
later mid-request.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env_file=".env" is resolved relative to the current working directory.
    # We always run uvicorn from the backend/ folder, so this points at
    # backend/.env — same behavior the old load_dotenv() had. Inside a
    # container there is no .env file; env vars are injected directly, and
    # pydantic-settings simply skips the missing file. case_sensitive=False
    # means DATABASE_URL in the env maps to the database_url field below.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Required. No default, so if DATABASE_URL is missing, Settings() raises a
    # ValidationError at import time: "database_url Field required". That is
    # the loud-at-startup behavior we want.
    database_url: str

    # Optional, with safe defaults.
    sql_echo: bool = False
    scan_interval_seconds: int = 300

    # Stored as a plain comma-separated string (NOT a list) on purpose: a
    # list[str] field would make pydantic try to JSON-parse the env value,
    # forcing ugly CORS_ORIGINS=["http://localhost:5174"] syntax in .env.
    # Use the cors_origins_list property below to get the parsed list.
    cors_origins: str = "http://localhost:5174"

    @property
    def cors_origins_list(self) -> list[str]:
        """Split the comma-separated CORS_ORIGINS into a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


# Instantiated once at import. Everything else does `from config import settings`.
settings = Settings()
