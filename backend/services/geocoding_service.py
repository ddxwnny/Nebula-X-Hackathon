from clients.onemap_client import OneMapClient
from config import get_settings
from models.requests import Location
from models.responses import Coordinates


class GeocodingService:
    def __init__(self, client: OneMapClient | None = None): self.client = client or OneMapClient(get_settings())
    async def resolve_location(self, location: Location) -> Coordinates:
        return location.coordinates() or await self.client.geocode(location.address or "")
