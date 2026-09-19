from datetime import datetime

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
    # Transit identifiers from OneMap, used to look up LTA live bus arrivals.
    stop_code: str | None = None
    service_no: str | None = None
    scheduled_departure: datetime | None = None
    live_bus: "LiveBusInfo | None" = None


class BusEta(BaseModel):
    estimated_arrival: datetime
    minutes_away: int
    wheelchair_accessible: bool
    load: str  # seats_available, standing_available, limited_standing, unknown
    bus_type: str  # single_deck, double_deck, bendy, unknown
    monitored: bool  # True when LTA tracks the bus by GPS; False = timetable estimate


class LiveBusInfo(BaseModel):
    """LTA BusArrival data for one bus leg, and the bus the rider can actually board."""
    status: str  # live, no_suitable_bus, beyond_live_horizon, outside_live_window, unavailable
    stop_code: str
    service_no: str
    next_buses: list[BusEta] = Field(default_factory=list)
    boarding_eta: datetime | None = None
    boarding_bus_wheelchair_accessible: bool | None = None
    delay_vs_schedule_min: float | None = None  # bus lateness vs OneMap's timetable; positive = late
    skipped_inaccessible: int = 0  # reachable buses passed over because they are not wheelchair accessible
    message: str


class ArrivalEstimate(BaseModel):
    departure: datetime
    arrival: datetime
    basis: str  # live (a bus leg boards on a live LTA ETA), scheduled, or uncertain (see note)
    note: str


class Route(BaseModel):
    total_duration_min: float
    distance_m: float
    legs: list[RouteLeg]
    exit_routing: "ExitRoutingMetadata | None" = None
    estimated_arrival: ArrivalEstimate | None = None


class BusServiceArrivals(BaseModel):
    service_no: str
    operator: str | None = None
    next_buses: list[BusEta] = Field(default_factory=list)


class BusStopArrivals(BaseModel):
    stop_code: str
    status: str  # live or unavailable
    fetched_at: datetime
    services: list[BusServiceArrivals] = Field(default_factory=list)


class VerificationStep(BaseModel):
    """What one planning stage actually did for this journey."""
    stage: str  # transit_route, exit_routing, accessibility, live_bus_arrivals, arrival_estimate, rain_forecast
    status: str  # done, warning (ran, but the result needs attention), skipped, unavailable
    detail: str


class CrowdStation(BaseModel):
    line: str
    station: str
    live_level: str = "unknown"
    forecast_level: str = "unknown"


class CrowdAssessment(BaseModel):
    status: str  # live, partial, unavailable
    overall_level: str  # low, medium, high, unknown
    stations: list[CrowdStation] = Field(default_factory=list)
    recommendation: str
    tradeoff: str | None = None


class RerouteInfo(BaseModel):
    reason: str | None = None
    origin_source: str  # current_location or original_origin
    replanned_at: datetime
    exits_checked: int = 0


class RouteResponse(BaseModel):
    request_id: str
    origin: Coordinates
    destination: Coordinates
    recommended_route: Route
    accessibility: "AccessibilityResult"
    decision: "RouteDecision"
    rain_forecast: "RainForecast | None" = None
    crowd_assessment: CrowdAssessment | None = None
    reroute: RerouteInfo | None = None
    verification: list[VerificationStep] = Field(default_factory=list)


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
    # LTA publishes lift outages, not a per-exit lift inventory, so the absence
    # of an outage is reported as such rather than as a confirmed working lift.
    lift_status: str = "no_reported_outage"  # no_reported_outage or maintenance
    lift_alerts: list[str] = Field(default_factory=list)
    station_lift_alerts: list[str] = Field(default_factory=list)
    is_selected: bool = False


class ExitRoutingMetadata(BaseModel):
    enabled: bool
    fallback_to_station_centroid: bool
    origin: StationAccess | None = None
    destination: StationAccess | None = None
    explanation: str | None = None
    fallback_reason: str | None = None
    candidate_exits: list[ExitMarker] = Field(default_factory=list)


class RainPointForecast(BaseModel):
    lat: float
    lon: float
    rain_expected: bool
    rain_severity: str
    forecast_area: str
    forecast_text: str
    valid_period: str


class RainForecast(BaseModel):
    rain_along_route: bool
    rain_severity: str
    currently_raining: bool
    current_rainfall_mm: float
    point_forecasts: list[RainPointForecast]
    recommendation: str
