"""Unified LTA DataMall client for station exits, lift outages, and train service alerts."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any
import httpx

from config import Settings, get_settings
from models.disruptions import TrainDisruption, TrainServiceStatus

logger = logging.getLogger(__name__)


class LTAClient:
    """Canonical client for all LTA DataMall and open data transport APIs."""

    BASE_URL = "https://datamall2.mytransport.sg/ltaodataservice"
    _exit_cache: list[dict] = []
    _exit_cache_until = datetime.min.replace(tzinfo=timezone.utc)
    _maintenance_cache: dict[str, tuple[datetime, dict[str, dict]]] = {}

    _alert_cache: TrainServiceStatus | None = None
    _alert_cache_until: datetime = datetime.min.replace(tzinfo=timezone.utc)

    @classmethod
    def clear_alert_cache(cls) -> None:
        cls._alert_cache = None
        cls._alert_cache_until = datetime.min.replace(tzinfo=timezone.utc)

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._last_known_status: TrainServiceStatus | None = None

    # --- Train Service Alerts ---

    async def get_train_service_alerts(self, force_refresh: bool = False) -> TrainServiceStatus:
        now = datetime.now(timezone.utc)
        if not force_refresh and self._alert_cache is not None and now < self._alert_cache_until:
            return self._alert_cache

        if not self.settings.lta_datamall_account_key:
            return self._fallback_status("unavailable", "Missing LTA DataMall AccountKey")

        headers = {
            "AccountKey": self.settings.lta_datamall_account_key,
            "accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
                response = await client.get(
                    self.settings.lta_train_service_alerts_url,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as err:
            err_msg = str(err)
            if isinstance(err, httpx.HTTPStatusError) and err.response is not None:
                try:
                    payload = err.response.json()
                    fault_msg = payload.get("fault", {}).get("faultstring")
                    if fault_msg:
                        err_msg = f"{err.response.status_code} ({fault_msg})"
                except Exception:
                    pass
            logger.warning("Failed to fetch TrainServiceAlerts from LTA DataMall: %s", err_msg)
            fallback = self._fallback_status("stale" if self._last_known_status else "unavailable", err_msg)
            self._alert_cache = fallback
            self._alert_cache_until = now + timedelta(seconds=self.settings.disruption_poll_interval_seconds)
            return fallback

        status = self._parse_payload(data)
        self._last_known_status = status
        self._alert_cache = status
        self._alert_cache_until = now + timedelta(seconds=self.settings.disruption_poll_interval_seconds)
        return status

    def _parse_payload(self, data: dict[str, Any]) -> TrainServiceStatus:
        val = data.get("value", data)
        if isinstance(val, list) and val:
            val = val[0]
        elif not isinstance(val, dict):
            val = {}

        raw_status = val.get("Status", 1)
        try:
            status_code = int(raw_status)
        except (ValueError, TypeError):
            status_code = 1

        raw_segments = val.get("AffectedSegments", [])
        if isinstance(raw_segments, dict):
            raw_segments = [raw_segments]

        segments: list[TrainDisruption] = []
        for seg in raw_segments:
            if not isinstance(seg, dict):
                continue
            line = str(seg.get("Line") or "").strip().upper()
            direction = str(seg.get("Direction") or "").strip()

            raw_stations = seg.get("Stations", [])
            stations = self._normalize_list(raw_stations)

            free_bus = self._normalize_list(seg.get("FreePublicBus", []))
            free_shuttle = self._normalize_list(seg.get("FreeMRTShuttle", []))
            shuttle_direction = seg.get("MRTShuttleDirection")
            if shuttle_direction:
                shuttle_direction = str(shuttle_direction).strip()

            if line or stations:
                segments.append(
                    TrainDisruption(
                        line=line,
                        direction=direction,
                        stations=stations,
                        free_public_bus=free_bus,
                        free_mrt_shuttle=free_shuttle,
                        mrt_shuttle_direction=shuttle_direction,
                    )
                )

        raw_messages = val.get("Message", [])
        messages: list[str] = []
        if isinstance(raw_messages, list):
            for msg in raw_messages:
                if isinstance(msg, dict):
                    content = msg.get("Content") or msg.get("text") or str(msg)
                    messages.append(str(content).strip())
                elif isinstance(msg, str) and msg.strip():
                    messages.append(msg.strip())
        elif isinstance(raw_messages, str) and raw_messages.strip():
            messages.append(raw_messages.strip())

        return TrainServiceStatus(
            status=status_code,
            affected_segments=segments,
            messages=messages,
            data_status="ok",
        )

    @staticmethod
    def _normalize_list(val: Any) -> list[str]:
        if isinstance(val, str):
            parts = [p.strip().upper() for p in val.replace(";", ",").split(",") if p.strip()]
            return parts
        if isinstance(val, list):
            res = []
            for item in val:
                if isinstance(item, str):
                    for sub in item.replace(";", ",").split(","):
                        if sub.strip():
                            res.append(sub.strip().upper())
                elif item is not None:
                    res.append(str(item).strip().upper())
            return res
        return []

    def _fallback_status(self, data_status: str, error_msg: str) -> TrainServiceStatus:
        if self._last_known_status:
            return TrainServiceStatus(
                status=self._last_known_status.status,
                affected_segments=self._last_known_status.affected_segments,
                messages=self._last_known_status.messages + [f"Data is stale: {error_msg}"],
                data_status="stale",
            )
        return TrainServiceStatus(
            status=1,
            affected_segments=[],
            messages=[f"Service alerts unavailable: {error_msg}"],
            data_status=data_status,
        )

    # --- Station Exits & Lift Maintenance ---

    async def station_exits(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        if now < self._exit_cache_until:
            return self._exit_cache
        try:
            async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
                response = await client.get(self.settings.lta_station_exits_geojson_url)
                response.raise_for_status()
                payload = response.json()
                download_url = payload.get("data", {}).get("url")
                if download_url:
                    response = await client.get(download_url)
                    response.raise_for_status()
                    payload = response.json()
            features = payload.get("features", [])
            rows = [{**feature.get("properties", {}), "_coordinates": feature.get("geometry", {}).get("coordinates", [])} for feature in features]
        except (httpx.HTTPError, ValueError, TypeError):
            return []
        self._exit_cache = [exit_ for row in rows if (exit_ := self._normalise_exit(row))]
        self._exit_cache_until = now + timedelta(hours=24)
        return self._exit_cache

    async def lift_statuses(self, station_code: str) -> dict[str, dict]:
        now = datetime.now(timezone.utc)
        cached = self._maintenance_cache.get(station_code)
        if cached and now < cached[0]:
            return cached[1]
        if not self.settings.lta_datamall_account_key:
            return {}
        headers = {"AccountKey": self.settings.lta_datamall_account_key, "accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
                response = await client.get(f"{self.BASE_URL}/v2/FacilitiesMaintenance", params={"StationCode": station_code}, headers=headers)
                response.raise_for_status()
                links = response.json().get("value", response.json().get("Value", []))
                link = next((item.get("Link") for item in links if item.get("Link")), None)
                if not link:
                    statuses: dict[str, dict] = {}
                else:
                    file_response = await client.get(link)
                    file_response.raise_for_status()
                    records = file_response.json().get("value", file_response.json())
                    statuses = {self._lift_id(item): self._normalise_lift(item, station_code) for item in records if self._lift_id(item)}
        except (httpx.HTTPError, ValueError, TypeError):
            statuses = {}
        self._maintenance_cache[station_code] = (now + timedelta(minutes=5), statuses)
        return statuses

    @staticmethod
    def _normalise_exit(row: dict) -> dict | None:
        coordinates = row.get("_coordinates", [])
        latitude, longitude = row.get("Latitude") or row.get("LATITUDE"), row.get("Longitude") or row.get("LONGITUDE")
        if len(coordinates) >= 2:
            longitude, latitude = coordinates[0], coordinates[1]

        station_code = row.get("StationCode") or row.get("STN_NO") or row.get("STATION_CODE")
        station_name = row.get("STATION_NA") or row.get("StationName") or station_code
        station_id = station_name or station_code
        exit_code = row.get("ExitCode") or row.get("EXIT_CODE")

        if latitude is None or longitude is None or not station_id or not exit_code:
            return None

        return {
            "id": f"{station_code or station_name}-EXIT-{exit_code}",
            "station_id": str(station_id),
            "station_code": str(station_code) if station_code else None,
            "station_name": str(station_name) if station_name else None,
            "exit_id": str(exit_code),
            "lat": float(latitude),
            "lon": float(longitude),
        }

    @staticmethod
    def _lift_id(row: dict) -> str:
        return str(row.get("LiftId") or row.get("FacilityId") or row.get("EquipmentId") or "")

    @staticmethod
    def _normalise_lift(row: dict, station_code: str) -> dict:
        raw_status = str(row.get("Status") or row.get("OperationalStatus") or "unknown").lower()
        status = "maintenance" if any(term in raw_status for term in ("fault", "maint", "out")) else "available" if raw_status in {"available", "operational", "in service"} else "unknown"
        return {"status": status, "station_id": station_code, "exit_id": row.get("ExitCode") or row.get("Exit"), "updated_at": row.get("LastUpdated") or row.get("LastUpdatedDate")}


# Backward compatibility alias
LtaDataMallClient = LTAClient
