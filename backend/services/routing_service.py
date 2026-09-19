from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from clients.onemap_client import OneMapClient
from clients.routing_client import RoutingClient
from config import get_settings
from models.responses import Coordinates, Route, RouteLeg
from services.mrt_network import normalize_line_name

SGT = timezone(timedelta(hours=8))


class RoutingService:
    def __init__(self, client: RoutingClient | None = None): self.client = client or RoutingClient(OneMapClient(get_settings()))

    async def get_route(
        self,
        origin: Coordinates,
        destination: Coordinates,
        departure_date: date | None = None,
        departure_time: time | None = None,
        avoid_lines: list[str] | None = None,
        avoid_stations: list[str] | None = None,
    ) -> Route:
        payload = await self.client.get_public_transit_route(origin, destination, departure_date, departure_time)
        try: itineraries = payload["plan"]["itineraries"]
        except (KeyError, IndexError, TypeError) as error: raise HTTPException(status_code=404, detail="No public-transit route found") from error
        itinerary = self._select_best_itinerary(itineraries, avoid_lines=avoid_lines, avoid_stations=avoid_stations)
        legs = [self._to_leg(leg) for leg in itinerary["legs"]]
        if not legs:
            raise HTTPException(status_code=404, detail="No route found for these locations")
        return Route(total_duration_min=round(float(itinerary["duration"]) / 60, 1), distance_m=round(sum(leg.distance_m for leg in legs), 1), legs=legs)

    @classmethod
    def _select_best_itinerary(
        cls,
        itineraries: list[dict],
        avoid_lines: list[str] | None = None,
        avoid_stations: list[str] | None = None,
    ) -> dict:
        candidates = [itinerary for itinerary in itineraries if not cls._avoids_disruption(itinerary, avoid_lines, avoid_stations)] or itineraries
        if not candidates:
            raise HTTPException(status_code=404, detail="No public-transit route found")
        # Prefer a multimodal journey, but preserve a genuine walking-only result.
        return next(
            (item for item in candidates if any(str(leg.get("mode", "")).upper() != "WALK" for leg in item.get("legs", []))),
            candidates[0],
        )

    @staticmethod
    def _avoids_disruption(itinerary: dict, avoid_lines: list[str] | None, avoid_stations: list[str] | None) -> bool:
        lines = {normalize_line_name(leg.get("route")) for leg in itinerary.get("legs", []) if leg.get("route")}
        lines.discard(None)
        wanted_lines = {normalize_line_name(line) for line in avoid_lines or []}
        wanted_lines.discard(None)
        if wanted_lines & lines:
            return True
        wanted_stations = {" ".join(str(station).upper().split()) for station in avoid_stations or []}
        if not wanted_stations:
            return False
        for leg in itinerary.get("legs", []):
            locations = (leg.get("from", {}).get("name"), leg.get("to", {}).get("name"))
            if any(any(station in " ".join(str(location or "").upper().split()) for station in wanted_stations) for location in locations):
                return True
        return False

    @staticmethod
    def _to_leg(leg: dict) -> RouteLeg:
        mode = str(leg.get("mode", "")).lower()
        raw_accessibility = str(leg.get("accessibility", "unknown")).lower()
        accessibility = raw_accessibility if raw_accessibility in {"step_free", "stairs", "lift", "ramp", "unknown", "inaccessible", "lift_maintenance"} else "unknown"
        normalised_mode = "mrt" if mode in {"rail", "subway", "metro", "train"} else mode
        # OneMap (OpenTripPlanner) bus legs carry the LTA 5-digit stop code and the
        # service number (routeId), which is what LTA BusArrival is keyed on.
        is_bus = normalised_mode == "bus"
        raw_stop = leg.get("from", {}).get("stopCode")
        # LTA stop codes are 5 digits with leading zeros ("04167"); keep them if sent as a number.
        stop_code = (f"{raw_stop:05d}" if isinstance(raw_stop, int) and not isinstance(raw_stop, bool) else str(raw_stop or "").strip()) if is_bus else ""
        service_no = str(leg.get("routeId") or leg.get("routeShortName") or "").strip() if is_bus else ""
        start_ms = leg.get("startTime") if leg.get("transitLeg") else None
        try:
            scheduled = datetime.fromtimestamp(start_ms / 1000, SGT) if isinstance(start_ms, (int, float)) and not isinstance(start_ms, bool) else None
        except (OverflowError, OSError, ValueError):
            scheduled = None
        return RouteLeg(
            mode=normalised_mode,
            duration_min=round(float(leg["duration"]) / 60, 1),
            distance_m=float(leg.get("distance", 0)),
            from_location=leg.get("from", {}).get("name", "Origin"),
            to_location=leg.get("to", {}).get("name", "Destination"),
            geometry=RoutingService._decode_polyline(leg.get("legGeometry", {}).get("points", "")),
            line_name=leg.get("route"),
            accessibility=accessibility,
            stop_code=stop_code or None,
            service_no=service_no or None,
            scheduled_departure=scheduled,
        )

    @staticmethod
    def _decode_polyline(encoded: str) -> list[Coordinates]:
        """Decode OneMap's Google encoded polyline into map-ready WGS84 points."""
        coordinates: list[Coordinates] = []
        index = latitude = longitude = 0
        while index < len(encoded):
            values: list[int] = []
            for _ in range(2):
                shift = value = 0
                while True:
                    byte = ord(encoded[index]) - 63
                    index += 1
                    value |= (byte & 0x1F) << shift
                    shift += 5
                    if byte < 0x20:
                        break
                values.append(~(value >> 1) if value & 1 else value >> 1)
            latitude += values[0]
            longitude += values[1]
            coordinates.append(Coordinates(lat=latitude / 100_000, lon=longitude / 100_000))
        return coordinates
