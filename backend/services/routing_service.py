from datetime import date, time

from fastapi import HTTPException
from clients.onemap_client import OneMapClient
from clients.routing_client import RoutingClient
from config import get_settings
from models.responses import Coordinates, Route, RouteLeg
from utils.duration import duration_to_range, format_duration_range



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
        try:
            itineraries = payload["plan"]["itineraries"]
        except (KeyError, IndexError, TypeError) as error:
            raise HTTPException(status_code=404, detail="No public-transit route found") from error

        itinerary = self._select_best_itinerary(itineraries, avoid_lines, avoid_stations)
        legs = [self._to_leg(leg) for leg in itinerary["legs"]]
        if not legs:
            raise HTTPException(status_code=404, detail="No route found for these locations")
        raw_duration = round(float(itinerary["duration"]) / 60, 1)
        duration_range = duration_to_range(raw_duration)
        return Route(
            duration_minutes=raw_duration,
            duration_range=duration_range,
            duration_display=format_duration_range(duration_range),
            distance_m=round(sum(leg.distance_m for leg in legs), 1),
            legs=legs,
        )


    @staticmethod
    def _select_best_itinerary(
        itineraries: list[dict],
        avoid_lines: list[str] | None = None,
        avoid_stations: list[str] | None = None,
    ) -> dict:
        from services.mrt_network import check_station_overlap, get_stations_traversed, normalize_line_name

        def is_affected(itin: dict) -> bool:
            if not avoid_lines and not avoid_stations:
                return False
            for leg in itin.get("legs", []):
                mode = str(leg.get("mode", "")).lower()
                if mode in {"rail", "subway", "metro", "train"}:
                    raw_line = str(leg.get("route") or "")
                    canon_line = normalize_line_name(raw_line)
                    if avoid_lines and any(canon_line == normalize_line_name(l) for l in avoid_lines):
                        if not avoid_stations:
                            return True
                        from_name = leg.get("from", {}).get("name", "")
                        to_name = leg.get("to", {}).get("name", "")
                        leg_stations = get_stations_traversed(canon_line, from_name, to_name)
                        if check_station_overlap(leg_stations, avoid_stations):
                            return True
            return False

        if avoid_lines or avoid_stations:
            clean_multimodal = next(
                (item for item in itineraries if not is_affected(item) and any(str(leg.get("mode", "")).upper() != "WALK" for leg in item.get("legs", []))),
                None,
            )
            if clean_multimodal:
                return clean_multimodal

            clean_any = next((item for item in itineraries if not is_affected(item)), None)
            if clean_any:
                return clean_any

        # Default: Prefer multimodal, fall back to first
        return next(
            (item for item in itineraries if any(str(leg.get("mode", "")).upper() != "WALK" for leg in item.get("legs", []))),
            itineraries[0],
        )

    @staticmethod
    def _to_leg(leg: dict) -> RouteLeg:
        mode = str(leg.get("mode", "")).lower()
        normalised_mode = "mrt" if mode in {"rail", "subway", "metro", "train"} else mode
        raw_accessibility = str(leg.get("accessibility", "unknown")).lower()
        if raw_accessibility in {"step_free", "stairs", "lift", "ramp", "unknown", "inaccessible", "lift_maintenance"}:
            accessibility = raw_accessibility
        elif normalised_mode in {"mrt", "bus"}:
            accessibility = "step_free"
        else:
            accessibility = "unknown"
        return RouteLeg(mode=normalised_mode, duration_min=round(float(leg["duration"]) / 60, 1), distance_m=float(leg.get("distance", 0)), from_location=leg.get("from", {}).get("name", "Origin"), to_location=leg.get("to", {}).get("name", "Destination"), geometry=RoutingService._decode_polyline(leg.get("legGeometry", {}).get("points", "")), line_name=leg.get("route"), accessibility=accessibility)

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
