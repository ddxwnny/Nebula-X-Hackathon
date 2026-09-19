from datetime import date, time

from clients.onemap_client import OneMapClient
from models.responses import Coordinates


class RoutingClient:
    def __init__(self, onemap_client: OneMapClient): self.onemap_client = onemap_client
    async def get_public_transit_route(self, origin: Coordinates, destination: Coordinates, departure_date: date | None = None, departure_time: time | None = None) -> dict:
        return await self.onemap_client.transit_route(origin, destination, departure_date, departure_time)

    async def get_walking_route(self, origin: Coordinates, destination: Coordinates) -> dict:
        return await self.onemap_client.walking_route(origin, destination)
