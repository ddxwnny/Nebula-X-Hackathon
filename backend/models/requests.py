from pydantic import BaseModel, model_validator
from models.responses import Coordinates


class Location(BaseModel):
    address: str | None = None
    lat: float | None = None
    lon: float | None = None

    @model_validator(mode="after")
    def validate_source(self) -> "Location":
        has_address = bool(self.address and self.address.strip())
        has_lat, has_lon = self.lat is not None, self.lon is not None
        if has_lat != has_lon:
            raise ValueError("lat and lon must be provided together")
        if not has_address and not (has_lat and has_lon):
            raise ValueError("provide an address or both lat and lon")
        if has_lat and not -90 <= self.lat <= 90:
            raise ValueError("lat must be between -90 and 90")
        if has_lon and not -180 <= self.lon <= 180:
            raise ValueError("lon must be between -180 and 180")
        return self

    def coordinates(self) -> Coordinates | None:
        return Coordinates(lat=self.lat, lon=self.lon, label=self.address) if self.lat is not None and self.lon is not None else None


class RouteRequest(BaseModel):
    origin: Location
    destination: Location
