from clients.onemap_client import OneMapClient
from models.responses import Coordinates


class RoutingClient:
    def __init__(self, onemap_client: OneMapClient): self.onemap_client = onemap_client
    async def get_public_transit_route(self, origin: Coordinates, destination: Coordinates) -> dict:
        return await self.onemap_client.transit_route(origin, destination)
