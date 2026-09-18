from datetime import date, datetime, time
import httpx
from fastapi import HTTPException, status
from config import Settings
from models.responses import Coordinates, LocationSuggestion


class OneMapClient:
    """Boundary around OneMap's geocoding and public-transit APIs."""
    def __init__(self, settings: Settings): self.settings = settings

    async def geocode(self, address: str) -> Coordinates:
        suggestions = await self.search(address)
        if not suggestions: raise HTTPException(status_code=404, detail=f"Address not found: {address}")
        match = suggestions[0]
        return Coordinates(lat=match.lat, lon=match.lon, label=match.address)

    async def search(self, address: str) -> list[LocationSuggestion]:
        token = await self._token()
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            response = await client.get(f"{self.settings.onemap_base_url}/api/common/elastic/search", params={"searchVal": address, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1}, headers={"Authorization": token})
        self._check(response, "geocoding")
        return [LocationSuggestion(lat=float(result["LATITUDE"]), lon=float(result["LONGITUDE"]), address=result.get("ADDRESS") or result.get("SEARCHVAL") or address, label=result.get("ADDRESS") or result.get("SEARCHVAL") or address) for result in response.json().get("results", [])]

    async def transit_route(self, origin: Coordinates, destination: Coordinates, departure_date: date | None = None, departure_time: time | None = None) -> dict:
        token = await self._token()
        now = datetime.now()
        selected_date = departure_date or now.date()
        selected_time = departure_time or now.time()
        params = {"start": f"{origin.lat},{origin.lon}", "end": f"{destination.lat},{destination.lon}", "routeType": "pt", "date": selected_date.strftime("%m-%d-%Y"), "time": selected_time.strftime("%H:%M:%S"), "mode": "transit", "maxWalkDistance": 1000, "numItineraries": 3}
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            response = await client.get(f"{self.settings.onemap_base_url}/api/public/routingsvc/route", params=params, headers={"Authorization": token})
        self._check(response, "transit routing")
        return response.json()

    async def _token(self) -> str:
        if self.settings.onemap_access_token:
            return self.settings.onemap_access_token
        # Keep existing local setups working when a JWT was previously placed
        # in ONEMAP_PASSWORD before explicit token support was added.
        if self.settings.onemap_password and self.settings.onemap_password.count(".") == 2:
            return self.settings.onemap_password
        if not self.settings.onemap_email or not self.settings.onemap_password:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Transit routing is not configured. Set ONEMAP_ACCESS_TOKEN or ONEMAP_EMAIL and ONEMAP_PASSWORD.")
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            response = await client.post(f"{self.settings.onemap_base_url}/api/auth/post/getToken", json={"email": self.settings.onemap_email, "password": self.settings.onemap_password})
        self._check(response, "authentication")
        token = response.json().get("access_token")
        if not token: raise HTTPException(status_code=502, detail="OneMap did not return an access token")
        return token

    @staticmethod
    def _check(response: httpx.Response, operation: str) -> None:
        if not response.is_success: raise HTTPException(status_code=502, detail=f"OneMap {operation} failed with status {response.status_code}")
