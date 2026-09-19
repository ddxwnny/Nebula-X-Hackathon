import re
from typing import Iterable

import httpx

from clients.lta_datamall_client import LtaDataMallClient
from models.responses import Coordinates, ExitMarker

# Exit codes are upper-case ("A", "B1", "2", "2A"); only the word "exit" is
# case-insensitive, so prose like "Exit to Bus Interchange" is not read as exit "TO".
_EXIT_CODE = r"(?:[A-Z]\d{0,2}|\d{1,2}[A-Z]?)"
_EXIT_IN_TEXT = re.compile(rf"\b(?i:exits?)\s+({_EXIT_CODE}(?:\s*(?:/|,|&|(?i:and))\s*{_EXIT_CODE})*)\b")
_EXIT_CODE_RE = re.compile(rf"\b{_EXIT_CODE}\b")


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


def _outage_exits(outage: dict) -> set[str]:
    """Every exit an outage names ("Exit A/B Street level - Concourse" -> {"EXIT A", "EXIT B"})."""
    keys = {f"EXIT {code}" for match in _EXIT_IN_TEXT.finditer(str(outage.get("description") or "")) for code in _EXIT_CODE_RE.findall(match.group(1))}
    if not keys and outage.get("exit_id"):
        keys.add(exit_label(outage["exit_id"]).upper())
    return keys


def _natural_key(text: str) -> list:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


def build_exit_markers(exits: list[dict], outages: Iterable[dict], selected_exit_ids: set[str] | None = None) -> list[ExitMarker]:
    """Every exit of a station, annotated with reported lift outages.

    Outages naming one of the station's exits mark that exit. Everything else
    (concourse-to-platform lifts, or an exit missing from the LTA exit list) is
    attached to every exit as a station-wide alert, so no outage is dropped.
    """
    selected_exit_ids = selected_exit_ids or set()
    known_exits = {exit_label(exit_["exit_id"]).upper() for exit_ in exits}
    by_exit: dict[str, list[str]] = {}
    station_wide: list[str] = []
    for outage in outages:
        if outage.get("status", "maintenance") != "maintenance":
            continue
        description = str(outage.get("description") or outage.get("lift_id") or "Lift under maintenance")
        matched = _outage_exits(outage) & known_exits
        for exit_key in matched:
            by_exit.setdefault(exit_key, []).append(description)
        if not matched:
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
    return sorted(markers, key=lambda marker: _natural_key(marker.exit_name))
