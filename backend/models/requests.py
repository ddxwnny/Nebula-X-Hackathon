from datetime import date, time

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from models.responses import Coordinates


class Location(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    address: str | None = Field(default=None, validation_alias=AliasChoices("address", "label"))
    lat: float | None = None
    lon: float | None = None

    @property
    def label(self) -> str | None:
        return self.address

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


class RoutePreferences(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    step_free: bool = Field(default=False, validation_alias=AliasChoices("stepFree", "step_free"), serialization_alias="stepFree")


class RouteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    origin: Location
    destination: Location
    departure_date: date | None = Field(default=None, validation_alias=AliasChoices("departure_date", "departureDate"))
    departure_time: time | None = Field(default=None, validation_alias=AliasChoices("departure_time", "departureTime"))
    preferences: RoutePreferences = Field(default_factory=RoutePreferences)
