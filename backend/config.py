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
    lta_datamall_account_key: str | None = None
    lta_station_exits_geojson_url: str = "https://api-open.data.gov.sg/v1/public/api/datasets/d_b39d3a0871985372d7e1637193335da5/poll-download"
    lta_train_service_alerts_url: str = "https://datamall2.mytransport.sg/ltaodataservice/TrainServiceAlerts"
    disruption_poll_interval_seconds: float = 30.0
    enable_background_disruption_monitor: bool = False
    http_timeout_seconds: float = 12.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
