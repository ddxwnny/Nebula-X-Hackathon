"""LTA DataMall adapters for station exits and station-specific lift outages."""

from datetime import datetime, timedelta, timezone
import httpx
from config import get_settings


class LtaDataMallClient:
    _exit_cache: list[dict] = []
    _exit_cache_until = datetime.min.replace(tzinfo=timezone.utc)
    _maintenance_cache: dict[str, tuple[datetime, dict[str, dict]]] = {}
    BASE_URL = "https://datamall2.mytransport.sg/ltaodataservice"

    async def station_exits(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        if now < self._exit_cache_until:
            return self._exit_cache
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
                response = await client.get(settings.lta_station_exits_geojson_url)
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

    async def all_lift_maintenance(self) -> list[dict]:
        """Fetch all active lift/facility maintenance events across the entire rail network."""
        now = datetime.now(timezone.utc)
        cached = self._maintenance_cache.get("__ALL__")
        if cached and now < cached[0]:
            return list(cached[1].values())
        settings = get_settings()
        if not settings.lta_datamall_account_key:
            return []
        headers = {"AccountKey": settings.lta_datamall_account_key, "accept": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
                response = await client.get(f"{self.BASE_URL}/v2/FacilitiesMaintenance", headers=headers)
                response.raise_for_status()
                payload = response.json()
                raw_items = payload.get("value", payload.get("Value", []))
                # Check if payload contains directly array of maintenance or an external link
                if raw_items and any("LiftDesc" in item or "StationName" in item for item in raw_items):
                    items = raw_items
                else:
                    link = next((item.get("Link") for item in raw_items if item.get("Link")), None)
                    if link:
                        file_response = await client.get(link)
                        file_response.raise_for_status()
                        items = file_response.json().get("value", file_response.json())
                    else:
                        items = []
                records = {}
                for item in items:
                    stn = item.get("StationCode") or item.get("StationName") or "UNKNOWN"
                    lift_id = str(item.get("LiftID") or item.get("LiftId") or item.get("FacilityId") or "")
                    records[f"{stn}_{lift_id}_{item.get('LiftDesc', '')}"] = item
                self._maintenance_cache["__ALL__"] = (now + timedelta(minutes=5), records)
                return list(records.values())
        except Exception:
            return []

    async def lift_statuses(self, station_code: str) -> dict[str, dict]:
        now = datetime.now(timezone.utc)
        cached = self._maintenance_cache.get(station_code)
        if cached and now < cached[0]:
            return cached[1]
        all_maintenance = await self.all_lift_maintenance()
        station_normal = station_code.upper().replace(" STATION", "").replace(" STN", "").replace(" MRT", "").strip()
        matched: dict[str, dict] = {}
        for idx, item in enumerate(all_maintenance):
            item_stn = str(item.get("StationCode") or "").upper()
            item_name = str(item.get("StationName") or "").upper()
            if station_normal in item_stn or station_normal in item_name or item_name in station_normal:
                desc = str(item.get("LiftDesc", ""))
                lift_id = str(item.get("LiftID") or f"LIFT-{idx}")
                matched[lift_id] = {
                    "status": "maintenance",
                    "station_id": station_code,
                    "lift_id": lift_id,
                    "description": desc,
                    "exit_id": "Exit A" if "EXIT A" in desc.upper() else "Exit B" if "EXIT B" in desc.upper() else "Exit C" if "EXIT C" in desc.upper() else "Exit 1" if "EXIT 1" in desc.upper() else "Exit 2" if "EXIT 2" in desc.upper() else None,
                }
        self._maintenance_cache[station_code] = (now + timedelta(minutes=5), matched)
        return matched

    @staticmethod
    def _normalise_exit(row: dict) -> dict | None:
        coordinates = row.get("_coordinates", [])
        latitude, longitude = row.get("Latitude") or row.get("LATITUDE"), row.get("Longitude") or row.get("LONGITUDE")
        if len(coordinates) >= 2:
            longitude, latitude = coordinates[0], coordinates[1]
        station = row.get("StationCode") or row.get("STN_NO") or row.get("STATION_CODE") or row.get("STATION_NA")
        exit_code = row.get("ExitCode") or row.get("EXIT_CODE")
        if latitude is None or longitude is None or not station or not exit_code:
            return None
        return {"id": f"{station}-EXIT-{exit_code}", "station_id": station, "exit_id": str(exit_code), "lat": float(latitude), "lon": float(longitude)}

    @staticmethod
    def _lift_id(row: dict) -> str:
        return str(row.get("LiftId") or row.get("FacilityId") or row.get("EquipmentId") or "")

    @staticmethod
    def _normalise_lift(row: dict, station_code: str) -> dict:
        raw_status = str(row.get("Status") or row.get("OperationalStatus") or "unknown").lower()
        status = "maintenance" if any(term in raw_status for term in ("fault", "maint", "out")) else "available" if raw_status in {"available", "operational", "in service"} else "unknown"
        return {"status": status, "station_id": station_code, "exit_id": row.get("ExitCode") or row.get("Exit"), "updated_at": row.get("LastUpdated") or row.get("LastUpdatedDate")}
