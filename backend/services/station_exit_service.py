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
            return [exit_ for exit_ in await self._client.station_exits() if exit_["station_id"] == station_id]
        except (httpx.HTTPError, ValueError, TypeError):
            return []

    async def exits_for_station_name(self, station_name: str) -> list[dict]:
        """Match the official LTA station name; never substitute another station."""
        normalise = lambda value: " ".join(value.upper().replace(" STN", " STATION").split())
        try:
            target = normalise(station_name)
            return [exit_ for exit_ in await self._client.station_exits() if normalise(exit_["station_id"]) == target]
        except (httpx.HTTPError, ValueError, TypeError):
            return []
