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

        nearby_exits, unavailable_facilities, exit_lifts = await self._check_nearby_lifts(route)
        stairs_used = any(leg.accessibility == "stairs" for leg in route.legs)
        unknown_segments = sum(leg.accessibility == "unknown" for leg in route.legs if leg.mode == "walk")
        leg_lifts = [LiftUse(id=leg.line_name or "lift", status="available") for leg in route.legs if leg.accessibility == "lift"]
        lifts = exit_lifts or leg_lifts
        ramps = sum(leg.accessibility == "ramp" for leg in route.legs)

        # 1. Stairs detected
        if stairs_used:
            return (
                AccessibilityResult(step_free=True, accessible=False, verification="stairs_detected", stairs_used=True, unknown_segments=unknown_segments, lifts_used=lifts, ramps_used=ramps, unavailable_facilities=unavailable_facilities, station_exits_considered=nearby_exits),
                RouteDecision(reason="stairs_detected", summary="Route contains stairs.", details=["One or more walking connections contain stairs and are not step-free."]),
            )

        # 2. Lift maintenance outage detected
        if unavailable_facilities > 0:
            return (
                AccessibilityResult(step_free=True, accessible=False, verification="lift_maintenance", stairs_used=False, unknown_segments=unknown_segments, lifts_used=lifts, ramps_used=ramps, unavailable_facilities=unavailable_facilities, station_exits_considered=nearby_exits),
                RouteDecision(reason="lift_maintenance", summary="Station lift is currently under maintenance.", details=[f"{unavailable_facilities} elevator(s) required for step-free access are currently out of service."]),
            )

        # 3. Station centroid fallback (unverified station exit access)
        if route.exit_routing and route.exit_routing.fallback_to_station_centroid:
            reason = route.exit_routing.fallback_reason or "station_exit_data_unavailable"
            return (
                AccessibilityResult(step_free=True, accessible=False, verification="unverified", stairs_used=False, unknown_segments=unknown_segments, lifts_used=lifts, ramps_used=ramps, unavailable_facilities=unavailable_facilities, station_exits_considered=nearby_exits),
                RouteDecision(reason="step_free_preference", summary="No fully verified step-free route was found.", details=[f"Accessibility data is unavailable for one or more station walking connections ({reason}); this route is not labelled step-free."]),
            )

        # 4. Unknown walking segments
        if unknown_segments > 0:
            return (
                AccessibilityResult(step_free=True, accessible=False, verification="unverified", stairs_used=False, unknown_segments=unknown_segments, lifts_used=lifts, ramps_used=ramps, unavailable_facilities=unavailable_facilities, station_exits_considered=nearby_exits),
                RouteDecision(reason="step_free_preference", summary="No fully verified step-free route was found.", details=["Accessibility data is unavailable for one or more walking connections; this route is not labelled step-free."]),
            )

        # 5. Verified step-free route
        return (
            AccessibilityResult(step_free=True, accessible=True, verification="verified", stairs_used=False, unknown_segments=0, lifts_used=lifts, ramps_used=ramps, unavailable_facilities=0, station_exits_considered=nearby_exits),
            RouteDecision(reason="step_free_preference", summary="This route avoids stairs and uses verified step-free connections.", details=["All station and pedestrian connections provide verified barrier-free access."]),
        )

    async def _check_nearby_lifts(self, route: Route) -> tuple[list[str], int, list[LiftUse]]:
        """Associate walking/transit boundaries with LTA exits and outage records."""
        from services.mrt_network import station_code_for_name

        candidates: dict[str, dict] = {}
        # Include exits directly selected by exit routing
        if route.exit_routing:
            for access in (route.exit_routing.origin, route.exit_routing.destination):
                if access:
                    stn_code = getattr(access, "station_code", None) or station_code_for_name(access.station_name) or access.station_id
                    candidates[f"{access.station_id}-EXIT-{access.exit_id}"] = {
                        "id": f"{access.station_id}-EXIT-{access.exit_id}",
                        "station_id": access.station_id,
                        "station_code": stn_code,
                        "exit_id": access.exit_id,
                    }

        # Geometric search for boundaries
        boundary_points = []
        for leg in route.legs:
            if leg.mode == "walk" and leg.geometry:
                boundary_points.extend((leg.geometry[0], leg.geometry[-1]))
        for point in boundary_points:
            for exit_ in await self._station_exits.nearest_exits(point, limit=1):
                candidates[exit_["id"]] = exit_

        unavailable = 0
        lifts_found: list[LiftUse] = []
        for exit_ in candidates.values():
            stn = exit_.get("station_code") or station_code_for_name(exit_.get("station_name") or exit_.get("station_id") or "") or exit_.get("station_id")
            statuses = await self._lta_client.lift_statuses(stn)
            for lid, status in statuses.items():
                if str(status.get("exit_id")).upper() == str(exit_.get("exit_id")).upper():
                    if status.get("status") == "maintenance":
                        unavailable += 1
                        lifts_found.append(LiftUse(id=str(lid), station_exit=f"Exit {exit_['exit_id']}", status="maintenance"))
                    else:
                        lifts_found.append(LiftUse(id=str(lid), station_exit=f"Exit {exit_['exit_id']}", status="available"))
        return list(candidates.keys()), unavailable, lifts_found
