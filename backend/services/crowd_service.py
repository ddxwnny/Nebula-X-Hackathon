"""Crowding guidance for MRT legs using LTA PCD live and forecast feeds."""

from clients.lta_datamall_client import LtaDataMallClient
from models.responses import CrowdAssessment, CrowdStation, Route


_LEVELS = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
_LINE_CODES = {
    "NS": "NSL", "NORTH SOUTH": "NSL", "NORTH-SOUTH": "NSL",
    "EW": "EWL", "EAST WEST": "EWL", "EAST-WEST": "EWL",
    "NE": "NEL", "NORTH EAST": "NEL", "NORTH-EAST": "NEL",
    "CC": "CCL", "CIRCLE": "CCL", "DT": "DTL", "DOWNTOWN": "DTL",
    "TE": "TEL", "THOMSON EAST COAST": "TEL", "BP": "BPL", "BPL": "BPL",
    "STL": "SLRT", "SENGKANG": "SLRT", "PTL": "PLRT", "PUNGGOL": "PLRT",
}


def normalise_line(line_name: str | None) -> str | None:
    label = " ".join(str(line_name or "").upper().replace("LINE", "").split())
    if not label:
        return None
    for prefix, code in _LINE_CODES.items():
        if label == prefix or label.startswith(f"{prefix} "):
            return code
    return None


def normalise_level(raw: object) -> str:
    value = str(raw or "").strip().lower()
    if value in {"l", "low", "1"}:
        return "low"
    if value in {"m", "medium", "moderate", "2"}:
        return "medium"
    if value in {"h", "high", "heavy", "3"}:
        return "high"
    return "unknown"


def _row_station(row: dict) -> str:
    return str(row.get("Station") or row.get("StationCode") or row.get("StationName") or "Unknown station")


def _row_level(row: dict) -> str:
    return normalise_level(row.get("CrowdLevel") or row.get("Crowd") or row.get("CrowdDensity") or row.get("Level"))


class CrowdService:
    def __init__(self, lta_client: LtaDataMallClient | None = None):
        self._lta = lta_client or LtaDataMallClient()

    async def assess(self, route: Route, *, enabled: bool = True) -> CrowdAssessment:
        if not enabled:
            return CrowdAssessment(status="unavailable", overall_level="unknown", recommendation="Crowd control is off for this journey.")
        fetch_crowd = getattr(self._lta, "train_crowd", None)
        if not callable(fetch_crowd):
            return CrowdAssessment(status="unavailable", overall_level="unknown", recommendation="Live crowd data is unavailable; crowding has not been used to change this route.")
        lines = sorted({code for code in (normalise_line(leg.line_name) for leg in route.legs if leg.mode == "mrt") if code})
        if not lines:
            return CrowdAssessment(status="unavailable", overall_level="unknown", recommendation="No MRT segment has crowd data to check.")

        merged: dict[tuple[str, str], CrowdStation] = {}
        live_available = forecast_available = False
        for line in lines:
            live_rows, forecast_rows = await fetch_crowd(line), await fetch_crowd(line, forecast=True)
            live_available |= live_rows is not None
            forecast_available |= forecast_rows is not None
            for row in live_rows or []:
                station = _row_station(row)
                merged[(line, station)] = CrowdStation(line=line, station=station, live_level=_row_level(row))
            for row in forecast_rows or []:
                station = _row_station(row)
                key = (line, station)
                current = merged.get(key, CrowdStation(line=line, station=station))
                current.forecast_level = _row_level(row)
                merged[key] = current

        stations = sorted(merged.values(), key=lambda station: max(_LEVELS[station.live_level], _LEVELS[station.forecast_level]), reverse=True)
        overall_value = max((_LEVELS[max((station.live_level, station.forecast_level), key=lambda level: _LEVELS[level])] for station in stations), default=0)
        overall = next(level for level, value in _LEVELS.items() if value == overall_value)
        status = "live" if live_available and forecast_available else "partial" if live_available or forecast_available else "unavailable"
        if overall == "high":
            recommendation = "High crowding is reported on this MRT route. Consider travelling outside the peak window or allowing extra boarding time."
            tradeoff = "Crowd control prioritises a calmer boarding window; leaving later may add waiting time but reduces platform and lift congestion."
        elif overall == "medium":
            recommendation = "Moderate crowding is reported. Keep the step-free route and allow a little extra time at stations."
            tradeoff = "Avoiding the busiest boarding window may add waiting time, but keeps the journey more predictable."
        elif overall == "low":
            recommendation = "Crowding is low on the reported MRT segments."
            tradeoff = None
        else:
            recommendation = "Live crowd data is unavailable; crowding has not been used to change this route."
            tradeoff = None
        return CrowdAssessment(status=status, overall_level=overall, stations=stations[:12], recommendation=recommendation, tradeoff=tradeoff)