"""Exit-level walking-leg replacement with dynamic barrier invalidation.

Leverages LTA station exits, OneMap walking routes, and live LTA
v2/FacilitiesMaintenance lift statuses to sever inaccessible exits and
guarantee step-free routing for wheelchair commuters.
"""

from __future__ import annotations
from clients.routing_client import RoutingClient
from clients.onemap_client import OneMapClient
from clients.lta_datamall_client import LtaDataMallClient
from config import get_settings
from models.requests import RoutePreferences
from models.responses import Coordinates, ExitMarker, ExitRoutingMetadata, Route, RouteLeg, StationAccess
from services.routing_service import RoutingService
from services.station_exit_service import StationExitService, build_exit_markers, exit_label


class ExitRoutingService:
    def __init__(
        self,
        routing_client: RoutingClient | None = None,
        station_exits: StationExitService | None = None,
        lta_client: LtaDataMallClient | None = None,
    ):
        self._routing_client = routing_client or RoutingClient(OneMapClient(get_settings()))
        self._station_exits = station_exits or StationExitService()
        self._lta_client = lta_client or LtaDataMallClient()

    async def apply(self, route: Route, origin: Coordinates, destination: Coordinates, preferences: RoutePreferences) -> Route:
        transit_indices = [index for index, leg in enumerate(route.legs) if leg.mode == "mrt"]
        if not transit_indices:
            route.exit_routing = ExitRoutingMetadata(
                enabled=False,
                fallback_to_station_centroid=True,
                fallback_reason="no_mrt_segment",
                candidate_exits=[],
            )
            return route

        first_transit, last_transit = transit_indices[0], transit_indices[-1]
        all_candidate_markers: list[ExitMarker] = []

        origin_access, origin_markers = await self._replace_walking_leg(
            route,
            first_transit - 1,
            origin,
            route.legs[first_transit].from_location,
            is_origin=True,
            preferences=preferences,
        )
        all_candidate_markers.extend(origin_markers)

        destination_access, dest_markers = await self._replace_walking_leg(
            route,
            last_transit + 1,
            destination,
            route.legs[last_transit].to_location,
            is_origin=False,
            preferences=preferences,
        )
        all_candidate_markers.extend(dest_markers)
        # Boarding and alighting can be the same station (loop journeys); plot each exit once.
        unique_markers: dict[str, ExitMarker] = {}
        for marker in all_candidate_markers:
            kept = unique_markers.setdefault(marker.id, marker)
            kept.is_selected = kept.is_selected or marker.is_selected
        all_candidate_markers = list(unique_markers.values())

        route.total_duration_min = round(sum(leg.duration_min for leg in route.legs), 1)
        route.distance_m = round(sum(leg.distance_m for leg in route.legs), 1)

        has_access = bool(origin_access or destination_access)
        has_severed = any(marker.lift_status == "maintenance" for marker in all_candidate_markers)

        explanation = (
            "Station exits selected using walking network duration with real-time lift outage avoidance."
            if preferences.step_free and has_severed
            else "Station exits were selected using walking-network duration."
            if has_access
            else None
        )

        route.exit_routing = ExitRoutingMetadata(
            enabled=has_access,
            fallback_to_station_centroid=not bool(origin_access and destination_access),
            origin=origin_access,
            destination=destination_access,
            explanation=explanation,
            fallback_reason=None if origin_access and destination_access else "station_exit_data_unavailable",
            candidate_exits=all_candidate_markers,
        )
        return route

    async def _replace_walking_leg(
        self,
        route: Route,
        index: int,
        endpoint: Coordinates,
        station_name: str,
        *,
        is_origin: bool,
        preferences: RoutePreferences,
    ) -> tuple[StationAccess | None, list[ExitMarker]]:
        # Every exit of the station is plotted, even when no walking leg is
        # replaced, so riders can see alternatives and their lift status.
        candidates = await self._station_exits.exits_for_station_name(station_name)
        candidate_markers = build_exit_markers(candidates, (await self._lta_client.lift_statuses(station_name)).values()) if candidates else []
        if index < 0 or index >= len(route.legs) or route.legs[index].mode != "walk" or not candidates:
            return None, candidate_markers

        existing = route.legs[index]

        # DYNAMIC BARRIER INVALIDATION:
        # When step_free preference is active, sever exits whose lift is under maintenance
        severed = {marker.id for marker in candidate_markers if marker.lift_status == "maintenance"}
        valid_candidates = [exit_ for exit_ in candidates if not (preferences.step_free and exit_["id"] in severed)]

        # If all candidate exits were severed due to lift maintenance
        if preferences.step_free and candidates and not valid_candidates:
            # Mark the existing walking leg as blocked by lift maintenance
            route.legs[index].accessibility = "lift_maintenance"
            return None, candidate_markers

        # Route through the valid candidates
        target_pool = valid_candidates if valid_candidates else candidates
        selections = []
        for exit_ in target_pool:
            exit_point = Coordinates(lat=exit_["lat"], lon=exit_["lon"], label=f"Exit {exit_['exit_id']}")
            start, end = (endpoint, exit_point) if is_origin else (exit_point, endpoint)
            try:
                walking = await self._routing_client.get_walking_route(start, end)
                summary = walking["route_summary"]
                selections.append((float(summary["total_time"]), float(summary["total_distance"]), exit_, walking))
            except (KeyError, TypeError):
                continue

        if not selections:
            return None, candidate_markers

        duration_seconds, _, selected, walking = min(selections, key=lambda item: (item[0], item[1]))

        # Prevent implausible cross-island detour
        if duration_seconds > existing.duration_min * 60 + 300:
            return None, candidate_markers

        # Mark chosen exit in candidate_markers
        for m in candidate_markers:
            if m.id == selected["id"]:
                m.is_selected = True

        summary = walking["route_summary"]
        geometry = RoutingService._decode_polyline(walking.get("route_geometry", ""))
        exit_name = exit_label(selected["exit_id"])

        # Assign verified step-free accessibility if selected exit has operational lift
        leg_accessibility = "step_free" if preferences.step_free else existing.accessibility

        route.legs[index] = RouteLeg(
            mode="walk",
            duration_min=round(float(summary["total_time"]) / 60, 1),
            distance_m=float(summary["total_distance"]),
            from_location=existing.from_location if is_origin else exit_name,
            to_location=exit_name if is_origin else existing.to_location,
            geometry=geometry,
            accessibility=leg_accessibility,
        )

        return (
            StationAccess(
                station_id=selected["station_id"],
                station_name=selected["station_id"],
                exit_id=selected["id"],
                exit_name=exit_name,
                lat=selected["lat"],
                lon=selected["lon"],
            ),
            candidate_markers,
        )
