from uuid import uuid4
from fastapi import APIRouter, Depends
from models.requests import RouteRequest
from models.responses import LocationSuggestion, RouteResponse
from services.geocoding_service import GeocodingService
from services.routing_service import RoutingService
from services.accessibility_service import AccessibilityService
from services.exit_routing_service import ExitRoutingService
from services.covered_linkway_service import CoveredLinkwayService

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


@router.get("/locations/search", response_model=list[LocationSuggestion])
async def search_locations(query: str, geocoding_service: GeocodingService = Depends(get_geocoding_service)) -> list[LocationSuggestion]:
    return await geocoding_service.search(query)


@router.post("/routes/plan", response_model=RouteResponse)
async def plan_route(request: RouteRequest, geocoding_service: GeocodingService = Depends(get_geocoding_service), routing_service: RoutingService = Depends(get_routing_service), accessibility_service: AccessibilityService = Depends(get_accessibility_service), exit_routing_service: ExitRoutingService = Depends(get_exit_routing_service)) -> RouteResponse:
    origin = await geocoding_service.resolve_location(request.origin)
    destination = await geocoding_service.resolve_location(request.destination)
    route = await routing_service.get_route(origin, destination, request.departure_date, request.departure_time)
    route = await exit_routing_service.apply(route, origin, destination, request.preferences)
    accessibility, decision = await accessibility_service.apply(route, request.preferences)
    return RouteResponse(request_id=str(uuid4()), origin=origin, destination=destination, recommended_route=route, accessibility=accessibility, decision=decision)

