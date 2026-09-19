import re
from typing import Iterable

import httpx

from clients.lta_datamall_client import LtaDataMallClient
from models.responses import Coordinates, ExitMarker

_EXIT_IN_TEXT = re.compile(r"\bEXIT\s+([A-Z]?\d{0,2}[A-Z]?)\b", re.IGNORECASE)


def exit_label(exit_id: str) -> str:
    return exit_id if str(exit_id).upper().startswith("EXIT ") else f"Exit {exit_id}"


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

    async def exit_markers(self, station_name: str, selected_exit_ids: set[str] | None = None) -> list[ExitMarker]:
        exits = await self.exits_for_station_name(station_name)
        if not exits:
            return []
        return build_exit_markers(exits, (await self._client.lift_statuses(station_name)).values(), selected_exit_ids)


def _outage_exit(outage: dict) -> str | None:
    """The exit an outage refers to, read from its description first ("Exit A Street level - Concourse")."""
    match = _EXIT_IN_TEXT.search(str(outage.get("description") or ""))
    if match and match.group(1):
        return f"EXIT {match.group(1).upper()}"
    return exit_label(outage["exit_id"]).upper() if outage.get("exit_id") else None


def build_exit_markers(exits: list[dict], outages: Iterable[dict], selected_exit_ids: set[str] | None = None) -> list[ExitMarker]:
    """Every exit of a station, annotated with reported lift outages.

    Outages naming an exit mark that exit; outages without one (e.g.
    concourse-to-platform lifts) are attached to every exit as station-wide alerts.
    """
    selected_exit_ids = selected_exit_ids or set()
    by_exit: dict[str, list[str]] = {}
    station_wide: list[str] = []
    for outage in outages:
        if outage.get("status", "maintenance") != "maintenance":
            continue
        description = str(outage.get("description") or outage.get("lift_id") or "Lift under maintenance")
        exit_key = _outage_exit(outage)
        if exit_key:
            by_exit.setdefault(exit_key, []).append(description)
        else:
            station_wide.append(description)
    markers = []
    for exit_ in exits:
        name = exit_label(exit_["exit_id"])
        alerts = by_exit.get(name.upper(), [])
        markers.append(ExitMarker(
            id=exit_["id"],
            station_id=exit_["station_id"],
            station_name=exit_["station_id"],
            exit_id=str(exit_["exit_id"]),
            exit_name=name,
            lat=exit_["lat"],
            lon=exit_["lon"],
            lift_status="maintenance" if alerts else "no_reported_outage",
            lift_alerts=alerts,
            station_lift_alerts=station_wide,
            is_selected=exit_["id"] in selected_exit_ids,
        ))
    return sorted(markers, key=lambda marker: marker.exit_name)
