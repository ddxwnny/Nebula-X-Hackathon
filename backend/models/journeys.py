from typing import Any
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from models.responses import Coordinates, RouteLeg


class JourneyLegInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: str
    line: str | None = None
    from_location: str = Field(
        validation_alias=AliasChoices("from", "from_location"),
        serialization_alias="from",
    )
    to_location: str = Field(
        validation_alias=AliasChoices("to", "to_location"),
        serialization_alias="to",
    )
    duration_min: float = 0.0
    stations: list[str] = Field(default_factory=list)


class CreateJourneyRequest(BaseModel):
    route_id: str
    origin: Coordinates
    destination: Coordinates
    legs: list[JourneyLegInput]
    current_position: Coordinates | None = None


class CreateJourneyResponse(BaseModel):
    journey_id: str
    status: str = "active"
    route_id: str


class DisruptionInfo(BaseModel):
    line: str
    status: str = "2"
    affected_stations: list[str] = Field(default_factory=list)
    free_public_bus: list[str] = Field(default_factory=list)
    free_mrt_shuttle: list[str] = Field(default_factory=list)
    mrt_shuttle_direction: str | None = None
    message: str | None = None


class JourneyStatusResponse(BaseModel):
    journey_id: str
    status: str  # "active", "unaffected", "reroute_required", "rerouted", "completed", "reroute_failed"
    disruption: DisruptionInfo | None = None
    data_status: str = "ok"


class RouteDurationSummary(BaseModel):
    remaining_duration_min: float


class NewRouteSummary(BaseModel):
    remaining_duration_min: float
    legs: list[RouteLeg] = Field(default_factory=list)


class RerouteChangeSummary(BaseModel):
    additional_duration_min: float
    reason: str | dict[str, Any]


class JourneyRerouteResponse(BaseModel):
    journey_id: str
    status: str = "rerouted"
    previous_route: RouteDurationSummary
    new_route: NewRouteSummary
    change: RerouteChangeSummary

