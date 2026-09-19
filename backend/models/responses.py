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
    accessibility: str = "unknown"


class Route(BaseModel):
    total_duration_min: float
    distance_m: float
    legs: list[RouteLeg]
    exit_routing: "ExitRoutingMetadata | None" = None


class RouteResponse(BaseModel):
    request_id: str
    origin: Coordinates
    destination: Coordinates
    recommended_route: Route
    accessibility: "AccessibilityResult"
    decision: "RouteDecision"


class LiftUse(BaseModel):
    id: str
    station_exit: str | None = None
    status: str = "unknown"


class AccessibilityResult(BaseModel):
    step_free: bool
    accessible: bool
    verification: str
    stairs_used: bool
    unknown_segments: int
    lifts_used: list[LiftUse] = Field(default_factory=list)
    ramps_used: int = 0
    unavailable_facilities: int = 0
    station_exits_considered: list[str] = Field(default_factory=list)


class RouteDecision(BaseModel):
    reason: str
    summary: str
    details: list[str] = Field(default_factory=list)


class StationAccess(BaseModel):
    station_id: str
    station_name: str
    exit_id: str
    exit_name: str
    lat: float
    lon: float


class ExitMarker(BaseModel):
    id: str
    station_id: str
    station_name: str
    exit_id: str
    exit_name: str
    lat: float
    lon: float
    has_lift: bool = True
    lift_status: str = "operational"  # operational, maintenance, or no_lift
    is_selected: bool = False


class ExitRoutingMetadata(BaseModel):
    enabled: bool
    fallback_to_station_centroid: bool
    origin: StationAccess | None = None
    destination: StationAccess | None = None
    explanation: str | None = None
    fallback_reason: str | None = None
    candidate_exits: list[ExitMarker] = Field(default_factory=list)
