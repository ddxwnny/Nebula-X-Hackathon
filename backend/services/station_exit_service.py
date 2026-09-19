import httpx

from clients.lta_datamall_client import LtaDataMallClient
from models.responses import Coordinates


class StationExitService:
    """Canonical station/exit lookup; keeps LTA identifiers out of route clients."""
    def __init__(self, client: LtaDataMallClient | None = None):
        self._client = client or LtaDataMallClient()

    async def nearest_exits(self, point: Coordinates, limit: int = 3) -> list[dict]:
        try:
            exits = await self._client.station_exits()
        except (httpx.HTTPError, ValueError, TypeError):
            return []
        return sorted(exits, key=lambda exit_: (exit_["lat"] - point.lat) ** 2 + (exit_["lon"] - point.lon) ** 2)[:limit]

    async def exits_for_station(self, station_id: str) -> list[dict]:
        try:
            sid = station_id.strip().upper()
            return [
                exit_ for exit_ in await self._client.station_exits()
                if exit_.get("station_id", "").upper() == sid
                or (exit_.get("station_code") and exit_["station_code"].upper() == sid)
                or (exit_.get("station_name") and exit_["station_name"].upper() == sid)
            ]
        except (httpx.HTTPError, ValueError, TypeError):
            return []

    async def exits_for_station_name(self, station_name: str) -> list[dict]:
        """Match the official LTA station name or code; never substitute another station."""
        from services.mrt_network import _clean_station_name, station_code_for_name, STATION_NAME_TO_CODES

        clean_target = _clean_station_name(station_name)
        target_codes = set(STATION_NAME_TO_CODES.get(clean_target, []))
        code_target = station_code_for_name(station_name)
        if code_target:
            target_codes.add(code_target.upper())

        try:
            exits = await self._client.station_exits()
            matches = []
            for exit_ in exits:
                s_name = exit_.get("station_name") or exit_.get("station_id") or ""
                s_code = exit_.get("station_code") or ""
                if _clean_station_name(s_name) == clean_target:
                    matches.append(exit_)
                elif (s_code and s_code.upper() in target_codes) or (s_name.upper() in target_codes):
                    matches.append(exit_)
            return matches
        except (httpx.HTTPError, ValueError, TypeError):
            return []
