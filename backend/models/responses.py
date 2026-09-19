from typing import Any
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator
from utils.duration import DurationRange, duration_to_range


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
    duration_minutes: DurationRange = Field(
        validation_alias=AliasChoices(
            "duration_minutes",
            "durationMinutes",
            "total_duration_min",
            "totalDurationMin",
        )
    )
    distance_m: float = Field(validation_alias=AliasChoices("distance_m", "distanceM"))
    legs: list[RouteLeg]
    exit_routing: "ExitRoutingMetadata | None" = Field(
        default=None,
        validation_alias=AliasChoices("exit_routing", "exitRouting"),
    )
    raw_duration_minutes: float | None = Field(
        default=None,
        exclude=True,
        validation_alias=AliasChoices(
            "raw_duration_minutes",
            "rawDurationMinutes",
            "total_duration_min",
            "totalDurationMin",
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def handle_duration_input(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw = data.get("raw_duration_minutes")
            total = data.get("total_duration_min") if "total_duration_min" in data else data.get("totalDurationMin")
            dur = data.get("duration_minutes") if "duration_minutes" in data else data.get("durationMinutes")

            raw_val = None
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                raw_val = float(raw)
            elif isinstance(total, (int, float)) and not isinstance(total, bool):
                raw_val = float(total)
            elif isinstance(dur, (int, float)) and not isinstance(dur, bool):
                raw_val = float(dur)

            if raw_val is not None:
                data["raw_duration_minutes"] = raw_val
                if "duration_minutes" not in data or isinstance(data.get("duration_minutes"), (int, float)):
                    data["duration_minutes"] = duration_to_range(raw_val)
        return data

    @property
    def total_duration_min(self) -> float:
        if self.raw_duration_minutes is not None:
            return self.raw_duration_minutes
        return float(self.duration_minutes.min)

    @total_duration_min.setter
    def total_duration_min(self, value: float | DurationRange) -> None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            self.raw_duration_minutes = float(value)
            self.duration_minutes = duration_to_range(float(value))
        elif isinstance(value, DurationRange):
            self.duration_minutes = value


class RouteResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    request_id: str = Field(validation_alias=AliasChoices("request_id", "requestId"))
    origin: Coordinates
    destination: Coordinates
    recommended_route: Route = Field(validation_alias=AliasChoices("recommended_route", "recommendedRoute"))
    accessibility: "AccessibilityResult"
    decision: "RouteDecision"
    duration_minutes: DurationRange | None = Field(
        default=None,
        validation_alias=AliasChoices("duration_minutes", "durationMinutes"),
    )

    @model_validator(mode="after")
    def populate_duration_minutes(self) -> "RouteResponse":
        if self.duration_minutes is None and self.recommended_route:
            self.duration_minutes = self.recommended_route.duration_minutes
        return self



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
