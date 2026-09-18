from fastapi import HTTPException
from clients.onemap_client import OneMapClient
from clients.routing_client import RoutingClient
from config import get_settings
from models.responses import Coordinates, Route, RouteLeg


class RoutingService:
    def __init__(self, client: RoutingClient | None = None): self.client = client or RoutingClient(OneMapClient(get_settings()))

    async def get_route(self, origin: Coordinates, destination: Coordinates) -> Route:
        payload = await self.client.get_public_transit_route(origin, destination)
        try: itineraries = payload["plan"]["itineraries"]
        except (KeyError, IndexError, TypeError) as error: raise HTTPException(status_code=404, detail="No public-transit route found") from error
        # Prefer a multimodal journey, but preserve a genuine walking-only
        # result when OneMap does not offer public transit for the locations.
        itinerary = next(
            (item for item in itineraries if any(str(leg.get("mode", "")).upper() != "WALK" for leg in item.get("legs", []))),
            itineraries[0],
        )
        legs = [self._to_leg(leg) for leg in itinerary["legs"]]
        if not legs:
            raise HTTPException(status_code=404, detail="No route found for these locations")
        return Route(total_duration_min=round(float(itinerary["duration"]) / 60, 1), distance_m=round(sum(leg.distance_m for leg in legs), 1), legs=legs)

    @staticmethod
    def _to_leg(leg: dict) -> RouteLeg:
        mode = str(leg.get("mode", "")).lower()
        return RouteLeg(mode="mrt" if mode == "rail" else mode, duration_min=round(float(leg["duration"]) / 60, 1), distance_m=float(leg.get("distance", 0)), from_location=leg.get("from", {}).get("name", "Origin"), to_location=leg.get("to", {}).get("name", "Destination"))
