from typing import Any
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from models.responses import Coordinates, RouteLeg


class JourneyLegInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mode: str
    line: str | None = Field(
        default=None,
        validation_alias=AliasChoices("line", "line_name", "lineName"),
    )
    from_location: str = Field(
        validation_alias=AliasChoices("from", "from_location", "fromLocation"),
        serialization_alias="from",
    )
    to_location: str = Field(
        validation_alias=AliasChoices("to", "to_location", "toLocation"),
        serialization_alias="to",
    )
    duration_min: float = Field(
        default=0.0,
        validation_alias=AliasChoices("duration_min", "durationMin"),
    )
    stations: list[str] = Field(default_factory=list)

    @property
    def line_name(self) -> str | None:
        return self.line


class CreateJourneyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    route_id: str = Field(validation_alias=AliasChoices("route_id", "routeId"))
    origin: Coordinates
    destination: Coordinates
    legs: list[JourneyLegInput]
    current_position: Coordinates | None = Field(
        default=None,
        validation_alias=AliasChoices("current_position", "currentPosition"),
    )


class CreateJourneyResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    journey_id: str = Field(validation_alias=AliasChoices("journey_id", "journeyId"))
    status: str = "active"
    route_id: str = Field(validation_alias=AliasChoices("route_id", "routeId"))


class DisruptionInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    line: str
    status: str = "2"
    affected_stations: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("affected_stations", "affectedStations", "stations"),
    )
    free_public_bus: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("free_public_bus", "freePublicBus"),
    )
    free_mrt_shuttle: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("free_mrt_shuttle", "freeMrtShuttle"),
    )
    mrt_shuttle_direction: str | None = Field(
        default=None,
        validation_alias=AliasChoices("mrt_shuttle_direction", "mrtShuttleDirection"),
    )
    message: str | None = None

    @property
    def stations(self) -> list[str]:
        return self.affected_stations


class JourneyStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    journey_id: str = Field(validation_alias=AliasChoices("journey_id", "journeyId"))
    status: str  # "active", "unaffected", "reroute_required", "rerouted", "completed", "reroute_failed"
    disruption: DisruptionInfo | None = None
    data_status: str = Field(
        default="ok",
        validation_alias=AliasChoices("data_status", "dataStatus"),
    )


class RouteDurationSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    remaining_duration_min: float = Field(
        validation_alias=AliasChoices("remaining_duration_min", "remainingDurationMin"),
    )


class NewRouteSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    remaining_duration_min: float = Field(
        validation_alias=AliasChoices("remaining_duration_min", "remainingDurationMin"),
    )
    legs: list[RouteLeg] = Field(default_factory=list)


class RerouteChangeSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    additional_duration_min: float = Field(
        validation_alias=AliasChoices("additional_duration_min", "additionalDurationMin"),
    )
    reason: str | dict[str, Any]


class JourneyRerouteResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    journey_id: str = Field(validation_alias=AliasChoices("journey_id", "journeyId"))
    status: str = "rerouted"
    previous_route: RouteDurationSummary = Field(
        validation_alias=AliasChoices("previous_route", "previousRoute"),
    )
    new_route: NewRouteSummary = Field(
        validation_alias=AliasChoices("new_route", "newRoute"),
    )
    change: RerouteChangeSummary

