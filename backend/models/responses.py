from pydantic import BaseModel, ConfigDict, Field


class Coordinates(BaseModel):
    lat: float
    lon: float
    label: str | None = None


class RouteLeg(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    mode: str
    duration_min: float
    distance_m: float
    from_location: str = Field(serialization_alias="from")
    to_location: str = Field(serialization_alias="to")


class Route(BaseModel):
    total_duration_min: float
    distance_m: float
    legs: list[RouteLeg]


class RouteResponse(BaseModel):
    request_id: str
    recommended_route: Route
