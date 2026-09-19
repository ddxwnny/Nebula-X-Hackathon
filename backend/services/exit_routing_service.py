"""Exit-level walking-leg replacement using LTA exits and OneMap walking routes."""

from clients.routing_client import RoutingClient
from clients.onemap_client import OneMapClient
from config import get_settings
from models.requests import RoutePreferences
from models.responses import Coordinates, ExitRoutingMetadata, Route, RouteLeg, StationAccess
from services.routing_service import RoutingService
from services.station_exit_service import StationExitService


class ExitRoutingService:
    def __init__(self, routing_client: RoutingClient | None = None, station_exits: StationExitService | None = None):
        self._routing_client = routing_client or RoutingClient(OneMapClient(get_settings()))
        self._station_exits = station_exits or StationExitService()

    async def apply(self, route: Route, origin: Coordinates, destination: Coordinates, preferences: RoutePreferences) -> Route:
        transit_indices = [index for index, leg in enumerate(route.legs) if leg.mode == "mrt"]
        if not transit_indices:
            route.exit_routing = ExitRoutingMetadata(enabled=False, fallback_to_station_centroid=True, fallback_reason="no_mrt_segment")
            return route
        first_transit, last_transit = transit_indices[0], transit_indices[-1]

        # Determine endpoint for origin walking leg (handles direct walks and transfer walks)
        origin_walk_idx = first_transit - 1
        origin_endpoint = origin
        if 0 <= origin_walk_idx < len(route.legs) and origin_walk_idx > 0 and route.legs[origin_walk_idx].geometry:
            origin_endpoint = route.legs[origin_walk_idx].geometry[0]

        # Determine endpoint for destination walking leg
        dest_walk_idx = last_transit + 1
        dest_endpoint = destination
        if 0 <= dest_walk_idx < len(route.legs) and dest_walk_idx < len(route.legs) - 1 and route.legs[dest_walk_idx].geometry:
            dest_endpoint = route.legs[dest_walk_idx].geometry[-1]

        origin_access = await self._replace_walking_leg(route, origin_walk_idx, origin_endpoint, route.legs[first_transit].from_location, is_origin=True, preferences=preferences)
        destination_access = await self._replace_walking_leg(route, dest_walk_idx, dest_endpoint, route.legs[last_transit].to_location, is_origin=False, preferences=preferences)
        route.total_duration_min = round(sum(leg.duration_min for leg in route.legs), 1)
        route.distance_m = round(sum(leg.distance_m for leg in route.legs), 1)

        if origin_access and destination_access:
            explanation = "Station exits were selected using walking-network duration."
            fallback_reason = None
        elif origin_access:
            explanation = "Station exit was selected for origin station using walking-network duration."
            fallback_reason = "destination_exit_data_unavailable"
        elif destination_access:
            explanation = "Station exit was selected for destination station using walking-network duration."
            fallback_reason = "origin_exit_data_unavailable"
        else:
            explanation = None
            fallback_reason = "station_exit_data_unavailable"

        route.exit_routing = ExitRoutingMetadata(
            enabled=bool(origin_access or destination_access),
            fallback_to_station_centroid=not bool(origin_access and destination_access),
            origin=origin_access,
            destination=destination_access,
            explanation=explanation,
            fallback_reason=fallback_reason,
        )
        return route

    async def _replace_walking_leg(self, route: Route, index: int, endpoint: Coordinates, station_name: str, *, is_origin: bool, preferences: RoutePreferences) -> StationAccess | None:
        if index < 0 or index >= len(route.legs) or route.legs[index].mode != "walk":
            return None
        existing = route.legs[index]
        candidates = await self._station_exits.exits_for_station_name(station_name)
        selections = []
        for exit_ in candidates:
            exit_point = Coordinates(lat=exit_["lat"], lon=exit_["lon"], label=f"Exit {exit_['exit_id']}")
            start, end = (endpoint, exit_point) if is_origin else (exit_point, endpoint)
            try:
                walking = await self._routing_client.get_walking_route(start, end)
                summary = walking["route_summary"]
                selections.append((float(summary["total_time"]), float(summary["total_distance"]), exit_, walking))
            except (KeyError, TypeError):
                continue
        if not selections:
            return None
        duration_seconds, _, selected, walking = min(selections, key=lambda item: (item[0], item[1]))
        # OneMap already provides a station-access walking leg. Exit routing
        # must not replace it with an implausible cross-island detour.
        if duration_seconds > existing.duration_min * 60 + 300:
            return None
        summary = walking["route_summary"]
        geometry = RoutingService._decode_polyline(walking.get("route_geometry", ""))
        exit_code = selected.get("exit_id") or selected.get("EXIT_CODE") or "Exit"
        exit_name = str(exit_code) if str(exit_code).upper().startswith("EXIT ") else f"Exit {exit_code}"
        station_id = str(selected.get("station_code") or selected.get("station_id") or station_name)
        proper_station_name = str(selected.get("station_name") or station_name)
        route.legs[index] = RouteLeg(
            mode="walk",
            duration_min=round(float(summary["total_time"]) / 60, 1),
            distance_m=float(summary["total_distance"]),
            from_location=existing.from_location if is_origin else exit_name,
            to_location=exit_name if is_origin else existing.to_location,
            geometry=geometry,
            accessibility=existing.accessibility,
        )
        return StationAccess(
            station_id=station_id,
            station_name=proper_station_name,
            exit_id=str(selected.get("exit_id") or selected.get("id") or exit_code),
            exit_name=exit_name,
            lat=selected["lat"],
            lon=selected["lon"],
        )
