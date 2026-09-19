"""Accessibility validation boundary for route providers.

OneMap transit output does not currently include OSM accessibility tags or a
station lift/exit identifier. This service deliberately treats that missing
data as unknown instead of declaring a journey step-free.
"""

from models.requests import RoutePreferences
from models.responses import AccessibilityResult, LiftUse, Route, RouteDecision
from services.station_exit_service import StationExitService
from clients.lta_datamall_client import LtaDataMallClient


class AccessibilityService:
    HARD_BLOCKED = {"inaccessible", "lift_maintenance"}

    @staticmethod
    def classify_osm_tags(tags: dict[str, str]) -> str:
        """Deterministic OSM accessibility classification for pedestrian edges."""
        if tags.get("highway") == "steps" or tags.get("barrier") == "steps":
            return "stairs"
        if tags.get("highway") == "elevator" or tags.get("elevator") in {"yes", "designated"}:
            return "lift"
        if tags.get("ramp") == "yes" or tags.get("ramp:wheelchair") == "yes":
            return "ramp"
        if tags.get("wheelchair") == "no" or tags.get("accessibility") == "no":
            return "inaccessible"
        if tags.get("wheelchair") == "yes":
            return "step_free"
        if tags.get("highway") in {"footway", "path", "pedestrian", "service"}:
            return "unknown"
        return "unknown"

    @staticmethod
    def edge_cost(duration_seconds: float, classification: str, preferences: RoutePreferences) -> float:
        if not preferences.step_free:
            return duration_seconds
        weights = {"step_free": 1.0, "ramp": 0.9, "lift": 1.0, "unknown": 1.5, "stairs": 100.0}
        return float("inf") if classification in AccessibilityService.HARD_BLOCKED else duration_seconds * weights.get(classification, 1.5)

    def __init__(self, station_exits: StationExitService | None = None, lta_client: LtaDataMallClient | None = None):
        self._station_exits = station_exits or StationExitService()
        self._lta_client = lta_client or LtaDataMallClient()

    async def apply(self, route: Route, preferences: RoutePreferences) -> tuple[AccessibilityResult, RouteDecision]:
        if not preferences.step_free:
            return (
                AccessibilityResult(step_free=False, accessible=True, verification="not_requested", stairs_used=False, unknown_segments=0),
                RouteDecision(reason="normal", summary="Standard route preference."),
            )

        nearby_exits, unavailable_facilities = await self._check_nearby_lifts(route)
        stairs_used = any(leg.accessibility == "stairs" for leg in route.legs)
        unknown_segments = sum(leg.accessibility == "unknown" for leg in route.legs if leg.mode == "walk")
        lifts = [LiftUse(id=leg.line_name or "lift", status="available") for leg in route.legs if leg.accessibility == "lift"]
        ramps = sum(leg.accessibility == "ramp" for leg in route.legs)
        verified = not stairs_used and unknown_segments == 0
        if verified:
            return (
                AccessibilityResult(step_free=True, accessible=True, verification="verified", stairs_used=False, unknown_segments=0, lifts_used=lifts, ramps_used=ramps, unavailable_facilities=unavailable_facilities, station_exits_considered=nearby_exits),
                RouteDecision(reason="step_free_preference", summary="This route avoids stairs and uses verified step-free connections."),
            )
        return (
            AccessibilityResult(step_free=True, accessible=False, verification="unverified", stairs_used=stairs_used, unknown_segments=unknown_segments, lifts_used=lifts, ramps_used=ramps, unavailable_facilities=unavailable_facilities, station_exits_considered=nearby_exits),
            RouteDecision(reason="step_free_preference", summary="No fully verified step-free route was found.", details=["Accessibility data is unavailable for one or more walking connections; this route is not labelled step-free."]),
        )

    async def _check_nearby_lifts(self, route: Route) -> tuple[list[str], int]:
        """Associate walking/transit boundaries with LTA exits and outage records.

        This does not infer a lift is used merely because it is nearby; OneMap
        does not identify the specific exit/lift in its itinerary.
        """
        boundary_points = []
        for leg in route.legs:
            if leg.mode == "walk" and leg.geometry:
                boundary_points.extend((leg.geometry[0], leg.geometry[-1]))
        candidates: dict[str, dict] = {}
        for point in boundary_points:
            for exit_ in await self._station_exits.nearest_exits(point, limit=1):
                candidates[exit_["id"]] = exit_
        unavailable = 0
        for exit_ in candidates.values():
            statuses = await self._lta_client.lift_statuses(exit_["station_id"])
            unavailable += sum(status["status"] == "maintenance" and str(status.get("exit_id")) == exit_["exit_id"] for status in statuses.values())
        return list(candidates), unavailable
