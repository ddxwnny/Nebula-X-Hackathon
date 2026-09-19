"""Accessibility validation boundary for route providers.

Integrates StationGroundLevelService (AmendmenttoMP2014RailStation GRND_LEVEL)
and LTA FacilitiesMaintenance to verify step-free routes, identify stairs/ramps,
and warn about concourse elevator transitions.
"""

from __future__ import annotations
from models.requests import RoutePreferences
from models.responses import AccessibilityResult, LiftUse, Route, RouteDecision
from services.station_exit_service import StationExitService
from services.station_ground_level_service import StationGroundLevelService
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

    def __init__(
        self,
        station_exits: StationExitService | None = None,
        lta_client: LtaDataMallClient | None = None,
        ground_level_service: StationGroundLevelService | None = None,
    ):
        self._station_exits = station_exits or StationExitService()
        self._lta_client = lta_client or LtaDataMallClient()
        self._ground_level = ground_level_service or StationGroundLevelService()

    async def apply(self, route: Route, preferences: RoutePreferences) -> tuple[AccessibilityResult, RouteDecision]:
        if not preferences.step_free:
            return (
                AccessibilityResult(step_free=False, accessible=True, verification="not_requested", stairs_used=False, unknown_segments=0),
                RouteDecision(reason="normal", summary="Standard route preference."),
            )

        nearby_exits, unavailable_facilities = await self._check_nearby_lifts(route)
        stairs_used = any(leg.accessibility == "stairs" for leg in route.legs)
        lift_maintenance_encountered = any(leg.accessibility == "lift_maintenance" for leg in route.legs)
        unknown_segments = sum(leg.accessibility == "unknown" for leg in route.legs if leg.mode == "walk")
        lifts = [LiftUse(id=leg.line_name or "lift", status="available") for leg in route.legs if leg.accessibility == "lift"]
        ramps = sum(leg.accessibility == "ramp" for leg in route.legs)

        # Confirm concourse transitions using GRND_LEVEL polygons
        concourse_details: list[str] = []
        for leg in route.legs:
            if leg.mode == "mrt":
                from_trans = self._ground_level.concourse_transition_info(leg.from_location)
                to_trans = self._ground_level.concourse_transition_info(leg.to_location)

                if from_trans["ground_level"] == "UNDERGROUND":
                    concourse_details.append(f"Origin Concourse ({from_trans['station_name']}): UNDERGROUND footprint confirmed — dual-lift transfer required.")
                elif from_trans["ground_level"] == "ABOVEGROUND":
                    concourse_details.append(f"Origin Concourse ({from_trans['station_name']}): ABOVEGROUND footprint confirmed — elevated concourse lift/ramp available.")

                if to_trans["ground_level"] == "UNDERGROUND":
                    concourse_details.append(f"Destination Concourse ({to_trans['station_name']}): UNDERGROUND footprint confirmed — platform-to-concourse lift transfer verified.")
                elif to_trans["ground_level"] == "ABOVEGROUND":
                    concourse_details.append(f"Destination Concourse ({to_trans['station_name']}): ABOVEGROUND footprint confirmed — elevated concourse lift/ramp available.")

        details: list[str] = []
        if concourse_details:
            details.extend(concourse_details)

        if lift_maintenance_encountered:
            details.append("Severed Barrier: Station lift maintenance was detected. Route was rerouted or flagged.")
            return (
                AccessibilityResult(
                    step_free=True,
                    accessible=False,
                    verification="severed_barrier",
                    stairs_used=stairs_used,
                    unknown_segments=unknown_segments,
                    lifts_used=lifts,
                    ramps_used=ramps,
                    unavailable_facilities=unavailable_facilities,
                    station_exits_considered=nearby_exits,
                ),
                RouteDecision(
                    reason="lift_maintenance_alert",
                    summary="Active lift maintenance severed standard exit path.",
                    details=details,
                ),
            )

        verified = not stairs_used and unknown_segments == 0 and not lift_maintenance_encountered
        if verified:
            details.append("All walking segments and station exits utilize confirmed step-free paths, lifts, or ramps.")
            return (
                AccessibilityResult(
                    step_free=True,
                    accessible=True,
                    verification="verified",
                    stairs_used=False,
                    unknown_segments=0,
                    lifts_used=lifts,
                    ramps_used=ramps,
                    unavailable_facilities=unavailable_facilities,
                    station_exits_considered=nearby_exits,
                ),
                RouteDecision(
                    reason="step_free_preference",
                    summary="This route avoids stairs and uses verified step-free connections.",
                    details=details,
                ),
            )

        details.append("Accessibility data is unverified or stairs are present for one or more segments.")
        return (
            AccessibilityResult(
                step_free=True,
                accessible=False,
                verification="unverified",
                stairs_used=stairs_used,
                unknown_segments=unknown_segments,
                lifts_used=lifts,
                ramps_used=ramps,
                unavailable_facilities=unavailable_facilities,
                station_exits_considered=nearby_exits,
            ),
            RouteDecision(
                reason="step_free_preference",
                summary="No fully verified step-free route was found.",
                details=details,
            ),
        )

    async def _check_nearby_lifts(self, route: Route) -> tuple[list[str], int]:
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
            unavailable += sum(
                status["status"] == "maintenance" and str(status.get("exit_id")) == exit_["exit_id"]
                for status in statuses.values()
            )
        return list(candidates), unavailable
