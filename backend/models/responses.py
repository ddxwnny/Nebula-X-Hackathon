from pydantic import BaseModel, ConfigDict, Field


class Coordinates(BaseModel):
    lat: float
    lon: float
    label: str | None = None


class LocationSuggestion(Coordinates):
    address: str


class RouteLeg(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    mode: str
    duration_min: float
    distance_m: float
    from_location: str = Field(serialization_alias="from")
    to_location: str = Field(serialization_alias="to")
    geometry: list[Coordinates] = Field(default_factory=list)
    line_name: str | None = None


class Route(BaseModel):
    total_duration_min: float
    distance_m: float
    legs: list[RouteLeg]


class RouteResponse(BaseModel):
    request_id: str
    origin: Coordinates
    destination: Coordinates
    recommended_route: Route
