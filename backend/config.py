from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Resolve the repository-level .env explicitly so `uvicorn main:app` works
    # whether it is launched from backend/ or the repository root.
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")
    onemap_base_url: str = "https://www.onemap.gov.sg"
    onemap_access_token: str | None = None
    onemap_email: str | None = None
    onemap_password: str | None = None
    http_timeout_seconds: float = 12.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
