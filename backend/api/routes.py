from datetime import datetime
from fastapi import APIRouter, Depends, Query
from models.requests import RerouteRequest, RouteRequest
from models.responses import BusStopArrivals, LocationSuggestion, RainForecast, RerouteInfo, RouteResponse
from services.geocoding_service import GeocodingService
from services.routing_service import RoutingService
from services.accessibility_service import AccessibilityService
from services.exit_routing_service import ExitRoutingService
from services.covered_linkway_service import CoveredLinkwayService
from services.station_ground_level_service import StationGroundLevelService
from services.weather_service import WeatherService
from services.live_transit_service import LiveTransitService
from services.route_pipeline import RoutePipeline
from services.routing_service import SGT

router = APIRouter(tags=["routes"])


def get_geocoding_service() -> GeocodingService:
    return GeocodingService()


def get_routing_service() -> RoutingService:
    return RoutingService()


def get_accessibility_service() -> AccessibilityService:
    return AccessibilityService()


def get_exit_routing_service() -> ExitRoutingService:
    return ExitRoutingService()


def get_covered_linkway_service() -> CoveredLinkwayService:
    return CoveredLinkwayService()


def get_station_ground_level_service() -> StationGroundLevelService:
    return StationGroundLevelService()


def get_weather_service() -> WeatherService:
    return WeatherService()


def get_live_transit_service() -> LiveTransitService:
    return LiveTransitService()


@router.get("/geo/covered-linkways")
async def get_covered_linkways(
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    limit: int | None = None,
    covered_service: CoveredLinkwayService = Depends(get_covered_linkway_service),
) -> list[dict]:
    return covered_service.find_linkways_near_route(min_lat, max_lat, min_lon, max_lon, limit=limit)


@router.get("/geo/station-ground-levels")
async def get_station_ground_levels(
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    limit: int | None = None,
    ground_service: StationGroundLevelService = Depends(get_station_ground_level_service),
) -> list[dict]:
    """Retrieve official station footprint polygons with GRND_LEVEL concourse attributes."""
    return ground_service.get_polygons_in_bounds(min_lat, max_lat, min_lon, max_lon, limit=limit)


@router.get("/geo/station-ground-levels/{station_name}")
async def get_station_concourse_info(
    station_name: str,
    ground_service: StationGroundLevelService = Depends(get_station_ground_level_service),
) -> dict:
    """Retrieve concourse transition guidance for a specific station name."""
    return ground_service.concourse_transition_info(station_name)


@router.get("/locations/search", response_model=list[LocationSuggestion])
async def search_locations(query: str, geocoding_service: GeocodingService = Depends(get_geocoding_service)) -> list[LocationSuggestion]:
    return await geocoding_service.search(query)


def get_route_pipeline(
    routing_service: RoutingService = Depends(get_routing_service),
    accessibility_service: AccessibilityService = Depends(get_accessibility_service),
    exit_routing_service: ExitRoutingService = Depends(get_exit_routing_service),
    weather_service: WeatherService = Depends(get_weather_service),
    live_transit_service: LiveTransitService = Depends(get_live_transit_service),
) -> RoutePipeline:
    return RoutePipeline(routing_service, accessibility_service, exit_routing_service, weather_service, live_transit_service)


@router.post("/routes/plan", response_model=RouteResponse)
async def plan_route(
    request: RouteRequest,
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
    pipeline: RoutePipeline = Depends(get_route_pipeline),
) -> RouteResponse:
    origin = await geocoding_service.resolve_location(request.origin)
    destination = await geocoding_service.resolve_location(request.destination)
    return await pipeline.run(origin, destination, request.departure_date, request.departure_time, request.preferences)


@router.post("/routes/reroute", response_model=RouteResponse)
async def reroute(
    request: RerouteRequest,
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
    pipeline: RoutePipeline = Depends(get_route_pipeline),
) -> RouteResponse:
    """Re-plan from where the rider is now, departing now, through the full verification pipeline."""
    now = datetime.now(SGT)
    from_current = request.current_location is not None
    origin = await geocoding_service.resolve_location(request.current_location if from_current else request.origin)
    if from_current and not origin.label:
        origin.label = "Your current location"
    destination = await geocoding_service.resolve_location(request.destination)
    response = await pipeline.run(origin, destination, now.date(), now.time().replace(second=0, microsecond=0), request.preferences)
    exit_routing = response.recommended_route.exit_routing
    response.reroute = RerouteInfo(
        reason=request.reason,
        origin_source="current_location" if from_current else "original_origin",
        replanned_at=now,
        exits_checked=len(exit_routing.candidate_exits) if exit_routing else 0,
    )
    return response


@router.get("/transit/bus-arrivals", response_model=BusStopArrivals)
async def get_bus_arrivals(
    stop_code: str = Query(pattern=r"^\d{5}$", description="5-digit LTA bus stop code"),
    service_no: str | None = None,
    live_transit_service: LiveTransitService = Depends(get_live_transit_service),
) -> BusStopArrivals:
    """Live LTA arrivals (next 3 buses per service, with wheelchair accessibility) for a bus stop."""
    return await live_transit_service.stop_arrivals(stop_code, service_no)


@router.get("/weather/rain-status", response_model=RainForecast)
async def get_rain_status(
    lat: float = 1.3521,
    lon: float = 103.8198,
    weather_service: WeatherService = Depends(get_weather_service),
) -> RainForecast:
    """Standalone rain status for a location (default: Singapore centre)."""
    assessment = await weather_service.assess_route_rain_risk([(lat, lon)])
    return RainForecast(
        rain_along_route=assessment["rain_along_route"],
        rain_severity=assessment["rain_severity"],
        currently_raining=assessment["current_rain"]["currently_raining"],
        current_rainfall_mm=assessment["current_rain"]["rainfall_mm"],
        point_forecasts=[
            {
                "lat": pf["lat"],
                "lon": pf["lon"],
                "rain_expected": pf["rain_expected"],
                "rain_severity": pf["rain_severity"],
                "forecast_area": pf["forecast_area"],
                "forecast_text": pf["forecast_text"],
                "valid_period": pf["valid_period"],
            }
            for pf in assessment["point_forecasts"]
        ],
        recommendation=assessment["recommendation"],
    )
