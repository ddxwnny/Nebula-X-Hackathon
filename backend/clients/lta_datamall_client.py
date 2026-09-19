"""LTA DataMall adapters for station exits and station-specific lift outages."""

from datetime import datetime, timedelta, timezone
import httpx
from config import get_settings


_STATION_SUFFIXES = (" MRT STATION", " LRT STATION", " STATION", " MRT STN", " LRT STN", " STN", " MRT", " LRT")


def station_key(name: str) -> str:
    """Reduce LTA/OneMap station labels ("HOUGANG MRT STATION", "Hougang") to one key."""
    key = " ".join(str(name).upper().split())
    for suffix in _STATION_SUFFIXES:
        if key.endswith(suffix):
            return key[: -len(suffix)].strip()
    return key


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
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            # data.gov.sg rate-limits this dataset (429): keep serving the last good copy and
            # back off, so every request does not hit the rate-limited endpoint again.
            LtaDataMallClient._exit_cache_until = now + (self.EXIT_RETRY_WITH_CACHE if self._exit_cache else self.EXIT_RETRY_EMPTY)
            return self._exit_cache
        # Stored on the class: every request builds fresh clients, and a
        # per-instance cache re-downloaded the dataset until it was rate-limited.
        LtaDataMallClient._exit_cache = [exit_ for row in rows if (exit_ := self._normalise_exit(row))]
        LtaDataMallClient._exit_cache_until = now + timedelta(hours=24)
        return self._exit_cache

    # Shared across instances (each request builds new clients). LTA refreshes
    # BusArrival roughly every 20s, so a short cache avoids hammering it.
    _bus_arrival_cache: dict[str, tuple[datetime, list[dict] | None]] = {}
    BUS_ARRIVAL_TTL = timedelta(seconds=20)
    BUS_ARRIVAL_FAILURE_TTL = timedelta(seconds=10)
    BUS_ARRIVAL_CACHE_MAX = 500
    _train_crowd_cache: dict[str, tuple[datetime, list[dict] | None]] = {}
    TRAIN_CROWD_TTL = timedelta(seconds=60)
    TRAIN_CROWD_FAILURE_TTL = timedelta(seconds=15)
    EXIT_RETRY_WITH_CACHE = timedelta(minutes=5)
    EXIT_RETRY_EMPTY = timedelta(minutes=1)

    async def bus_arrivals(self, stop_code: str) -> list[dict] | None:
        """Raw LTA v3/BusArrival services for a stop, or None when live data is unavailable."""
        stop_code = str(stop_code or "").strip()
        settings = get_settings()
        if not stop_code or not settings.lta_datamall_account_key:
            return None
        now = datetime.now(timezone.utc)
        cached = LtaDataMallClient._bus_arrival_cache.get(stop_code)
        if cached and now < cached[0]:
            return cached[1]
        headers = {"AccountKey": settings.lta_datamall_account_key, "accept": "application/json"}
        services: list[dict] | None
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
                response = await client.get(f"{self.BASE_URL}/v3/BusArrival", params={"BusStopCode": stop_code}, headers=headers)
                response.raise_for_status()
                payload = response.json().get("Services", [])
            services = [service for service in payload if isinstance(service, dict)] if isinstance(payload, list) else None
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            services = None
        # Failures are cached briefly too, so a rate-limited LTA is not retried on every request.
        self._store_bus_arrivals(stop_code, services, now + (self.BUS_ARRIVAL_TTL if services is not None else self.BUS_ARRIVAL_FAILURE_TTL), now)
        return services

    @classmethod
    def _store_bus_arrivals(cls, stop_code: str, services: list[dict] | None, until: datetime, now: datetime) -> None:
        cache = cls._bus_arrival_cache
        cache.pop(stop_code, None)  # a refresh re-inserts at the back and never evicts another stop
        if len(cache) >= cls.BUS_ARRIVAL_CACHE_MAX:
            for key in [key for key, (expiry, _) in cache.items() if expiry <= now]:
                del cache[key]
            while len(cache) >= cls.BUS_ARRIVAL_CACHE_MAX:
                del cache[next(iter(cache))]
        cache[stop_code] = (until, services)

    async def train_crowd(self, train_line: str, *, forecast: bool = False) -> list[dict] | None:
        """Fetch LTA station crowd levels for a train line, with a short cache."""
        train_line = str(train_line or "").strip().upper()
        settings = get_settings()
        if not train_line or not settings.lta_datamall_account_key:
            return None
        endpoint = "PCDForecast" if forecast else "PCDRealTime"
        cache_key = f"{endpoint}:{train_line}"
        now = datetime.now(timezone.utc)
        cached = self._train_crowd_cache.get(cache_key)
        if cached and now < cached[0]:
            return cached[1]
        headers = {"AccountKey": settings.lta_datamall_account_key, "accept": "application/json"}
        rows: list[dict] | None
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
                response = await client.get(f"{self.BASE_URL}/{endpoint}", params={"TrainLine": train_line}, headers=headers)
                response.raise_for_status()
                payload = response.json()
            raw_rows = payload.get("value", payload.get("Value", [])) if isinstance(payload, dict) else payload
            rows = [row for row in raw_rows if isinstance(row, dict)] if isinstance(raw_rows, list) else None
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            rows = None
        self._train_crowd_cache[cache_key] = (now + (self.TRAIN_CROWD_TTL if rows is not None else self.TRAIN_CROWD_FAILURE_TTL), rows)
        return rows

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

    def inject_simulated_maintenance(self, station_code: str, exit_id: str | None = "Exit A", description: str = "Lift maintenance in progress") -> None:
        now = datetime.now(timezone.utc)
        target = station_code.upper().replace(" STATION", "").replace(" STN", "").replace(" MRT", "").strip()
        simulated = {
            "SIM-LIFT-1": {
                "status": "maintenance",
                "station_id": target,
                "lift_id": "SIM-LIFT-1",
                "description": f"Simulated: {description}",
                "exit_id": exit_id or "Exit A",
            }
        }
        self._maintenance_cache[target] = (now + timedelta(hours=1), simulated)
        self._maintenance_cache[station_code] = (now + timedelta(hours=1), simulated)

    @classmethod
    def clear_simulated_maintenance(cls, station_code: str | None = None) -> None:
        """Clear simulated maintenance from the cache."""
        if station_code:
            target = station_code.upper().replace(" STATION", "").replace(" STN", "").replace(" MRT", "").strip()
            cls._maintenance_cache.pop(target, None)
            cls._maintenance_cache.pop(station_code, None)
        else:
            # Clear all simulated entries
            keys_to_remove = [k for k, v in cls._maintenance_cache.items() if any(item.get("lift_id") == "SIM-LIFT-1" for item in (v[1].values() if isinstance(v[1], dict) else []))]
            for k in keys_to_remove:
                cls._maintenance_cache.pop(k, None)

    async def lift_statuses(self, station_code: str) -> dict[str, dict]:
        # A blank name would equal every blank-named outage record.
        if not station_key(station_code):
            return {}
        now = datetime.now(timezone.utc)
        station_normal = station_code.upper().replace(" STATION", "").replace(" STN", "").replace(" MRT", "").strip()
        cached = self._maintenance_cache.get(station_code) or self._maintenance_cache.get(station_normal)
        if cached and now < cached[0]:
            return cached[1]
        all_maintenance = await self.all_lift_maintenance()
        matched: dict[str, dict] = {}
        for idx, item in enumerate(all_maintenance):
            # Exact name match: substring matching let "Punggol Point" outages
            # (and records with a blank name) leak onto other stations.
            if station_key(item.get("StationName") or "") == station_key(station_code) or str(item.get("StationCode") or "").upper() == station_code.upper():
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
