from uuid import uuid4
from fastapi import APIRouter, Depends
from models.requests import RouteRequest
from models.responses import LocationSuggestion, RouteResponse, RainForecast
from services.geocoding_service import GeocodingService
from services.routing_service import RoutingService
from services.accessibility_service import AccessibilityService
from services.exit_routing_service import ExitRoutingService
from services.covered_linkway_service import CoveredLinkwayService
from services.station_ground_level_service import StationGroundLevelService
from services.weather_service import WeatherService
from clients.lta_datamall_client import LtaDataMallClient

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


@router.post("/routes/plan", response_model=RouteResponse)
async def plan_route(
    request: RouteRequest,
    geocoding_service: GeocodingService = Depends(get_geocoding_service),
    routing_service: RoutingService = Depends(get_routing_service),
    accessibility_service: AccessibilityService = Depends(get_accessibility_service),
    exit_routing_service: ExitRoutingService = Depends(get_exit_routing_service),
    weather_service: WeatherService = Depends(get_weather_service),
) -> RouteResponse:
    if request.preferences.simulate_lift_maintenance:
        lta_client = LtaDataMallClient()
        lta_client.inject_simulated_maintenance(request.preferences.simulate_lift_maintenance)

    origin = await geocoding_service.resolve_location(request.origin)
    destination = await geocoding_service.resolve_location(request.destination)
    route = await routing_service.get_route(origin, destination, request.departure_date, request.departure_time)
    route = await exit_routing_service.apply(route, origin, destination, request.preferences)
    accessibility, decision = await accessibility_service.apply(route, request.preferences)

    # Assess rain risk along the route
    route_points = []
    for leg in route.legs:
        for pt in leg.geometry:
            route_points.append((pt.lat, pt.lon))
    if not route_points:
        route_points = [(origin.lat, origin.lon), (destination.lat, destination.lon)]

    rain_assessment = await weather_service.assess_route_rain_risk(route_points)
    rain_forecast = RainForecast(
        rain_along_route=rain_assessment["rain_along_route"],
        rain_severity=rain_assessment["rain_severity"],
        currently_raining=rain_assessment["current_rain"]["currently_raining"],
        current_rainfall_mm=rain_assessment["current_rain"]["rainfall_mm"],
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
            for pf in rain_assessment["point_forecasts"]
        ],
        recommendation=rain_assessment["recommendation"],
    )

    return RouteResponse(
        request_id=str(uuid4()),
        origin=origin,
        destination=destination,
        recommended_route=route,
        accessibility=accessibility,
        decision=decision,
        rain_forecast=rain_forecast,
    )


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
