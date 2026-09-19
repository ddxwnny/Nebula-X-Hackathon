from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class Coordinates(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    lat: float
    lon: float
    label: str | None = Field(default=None, validation_alias=AliasChoices("label", "address"))


class LocationSuggestion(Coordinates):
    model_config = ConfigDict(populate_by_name=True)
    address: str = Field(validation_alias=AliasChoices("address", "label"))

    @model_validator(mode="after")
    def populate_label_if_missing(self) -> "LocationSuggestion":
        if not self.label and self.address:
            self.label = self.address
        return self


class RouteLeg(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    mode: str
    duration_min: float = Field(validation_alias=AliasChoices("duration_min", "durationMin"))
    distance_m: float = Field(default=0.0, validation_alias=AliasChoices("distance_m", "distanceM"))
    from_location: str = Field(
        validation_alias=AliasChoices("from", "from_location", "fromLocation"),
        serialization_alias="from",
    )
    to_location: str = Field(
        validation_alias=AliasChoices("to", "to_location", "toLocation"),
        serialization_alias="to",
    )
    geometry: list[Coordinates] = Field(default_factory=list)
    line_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("line_name", "line", "lineName"),
    )
    accessibility: str = "unknown"

    @property
    def line(self) -> str | None:
        return self.line_name


class Route(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    total_duration_min: float = Field(validation_alias=AliasChoices("total_duration_min", "totalDurationMin"))
    distance_m: float = Field(validation_alias=AliasChoices("distance_m", "distanceM"))
    legs: list[RouteLeg]
    exit_routing: "ExitRoutingMetadata | None" = Field(
        default=None,
        validation_alias=AliasChoices("exit_routing", "exitRouting"),
    )


class RouteResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    request_id: str = Field(validation_alias=AliasChoices("request_id", "requestId"))
    origin: Coordinates
    destination: Coordinates
    recommended_route: Route = Field(validation_alias=AliasChoices("recommended_route", "recommendedRoute"))
    accessibility: "AccessibilityResult"
    decision: "RouteDecision"


class LiftUse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    station_exit: str | None = Field(default=None, validation_alias=AliasChoices("station_exit", "stationExit"))
    status: str = "unknown"


class AccessibilityResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    step_free: bool = Field(validation_alias=AliasChoices("step_free", "stepFree"))
    accessible: bool
    verification: str
    stairs_used: bool = Field(validation_alias=AliasChoices("stairs_used", "stairsUsed"))
    unknown_segments: int = Field(validation_alias=AliasChoices("unknown_segments", "unknownSegments"))
    lifts_used: list[LiftUse] = Field(default_factory=list, validation_alias=AliasChoices("lifts_used", "liftsUsed"))
    ramps_used: int = Field(default=0, validation_alias=AliasChoices("ramps_used", "rampsUsed"))
    unavailable_facilities: int = Field(default=0, validation_alias=AliasChoices("unavailable_facilities", "unavailableFacilities"))
    station_exits_considered: list[str] = Field(default_factory=list, validation_alias=AliasChoices("station_exits_considered", "stationExitsConsidered"))


class RouteDecision(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    reason: str
    summary: str
    details: list[str] = Field(default_factory=list)


class StationAccess(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    station_id: str = Field(validation_alias=AliasChoices("station_id", "stationId", "station_code", "stationCode"))
    station_name: str = Field(validation_alias=AliasChoices("station_name", "stationName"))
    exit_id: str = Field(validation_alias=AliasChoices("exit_id", "exitId"))
    exit_name: str = Field(validation_alias=AliasChoices("exit_name", "exitName"))
    lat: float
    lon: float

    @property
    def station_code(self) -> str:
        return self.station_id


class ExitRoutingMetadata(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    enabled: bool
    fallback_to_station_centroid: bool = Field(
        validation_alias=AliasChoices("fallback_to_station_centroid", "fallbackToStationCentroid")
    )
    origin: StationAccess | None = None
    destination: StationAccess | None = None
    explanation: str | None = None
    fallback_reason: str | None = Field(
        default=None,
        validation_alias=AliasChoices("fallback_reason", "fallbackReason"),
    )
