from uuid import uuid4
from fastapi import APIRouter, Depends
from models.disruptions import TrainServiceStatus
from models.journeys import (
    CreateJourneyRequest,
    CreateJourneyResponse,
    JourneyRerouteResponse,
    JourneyStatusResponse,
)
from models.requests import RouteRequest
from models.responses import LocationSuggestion, RouteResponse
from services.accessibility_service import AccessibilityService
from services.disruption_monitor import DisruptionMonitor
from services.exit_routing_service import ExitRoutingService
from services.geocoding_service import GeocodingService
from services.journey_service import JourneyService
from services.routing_service import RoutingService

router = APIRouter(tags=["routes"])

_journey_service: JourneyService | None = None
_disruption_monitor: DisruptionMonitor | None = None


def get_geocoding_service() -> GeocodingService:
    return GeocodingService()


def get_routing_service() -> RoutingService:
    return RoutingService()


def get_accessibility_service() -> AccessibilityService:
    return AccessibilityService()


def get_exit_routing_service() -> ExitRoutingService:
    return ExitRoutingService()


def get_journey_service(routing_service: RoutingService = Depends(get_routing_service)) -> JourneyService:
    global _journey_service
    if not isinstance(routing_service, RoutingService):
        routing_service = get_routing_service()
    if _journey_service is None:
        _journey_service = JourneyService(routing_service)
    return _journey_service


def get_disruption_monitor(journey_service: JourneyService = Depends(get_journey_service)) -> DisruptionMonitor:
    global _disruption_monitor
    if not isinstance(journey_service, JourneyService):
        journey_service = get_journey_service()
    if _disruption_monitor is None:
        _disruption_monitor = DisruptionMonitor(journey_service=journey_service)
    elif not isinstance(_disruption_monitor._journey_service, JourneyService):
        _disruption_monitor.set_journey_service(journey_service)
    return _disruption_monitor




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
    return RouteResponse(
        request_id=str(uuid4()),
        origin=origin,
        destination=destination,
        recommended_route=route,
        duration_minutes=route.duration_minutes,
        duration_range=route.duration_range,
        duration_display=route.duration_display,
        accessibility=accessibility,
        decision=decision,
    )




@router.post("/journeys", response_model=CreateJourneyResponse)
async def create_journey(
    request: CreateJourneyRequest,
    journey_service: JourneyService = Depends(get_journey_service),
    disruption_monitor: DisruptionMonitor = Depends(get_disruption_monitor),
) -> CreateJourneyResponse:
    journey = journey_service.create_journey(request)
    if disruption_monitor.current_status:
        journey_service.evaluate_journey_disruption(journey, disruption_monitor.current_status)
    return CreateJourneyResponse(
        journey_id=journey.journey_id,
        status=journey.status,
        route_id=journey.route_id,
    )


@router.get("/journeys/{journey_id}/status", response_model=JourneyStatusResponse)
async def get_journey_status(
    journey_id: str,
    journey_service: JourneyService = Depends(get_journey_service),
    disruption_monitor: DisruptionMonitor = Depends(get_disruption_monitor),
) -> JourneyStatusResponse:
    alert_status = disruption_monitor.current_status
    if not alert_status:
        try:
            alert_status = await disruption_monitor.check_for_updates()
        except Exception:
            alert_status = None
    return journey_service.get_journey_status(journey_id, alert_status=alert_status)


@router.post("/journeys/{journey_id}/reroute", response_model=JourneyRerouteResponse)
async def reroute_journey(
    journey_id: str,
    journey_service: JourneyService = Depends(get_journey_service),
    routing_service: RoutingService = Depends(get_routing_service),
) -> JourneyRerouteResponse:
    return await journey_service.reroute_journey(journey_id, routing_service)


@router.get("/disruptions/status", response_model=TrainServiceStatus)
async def get_disruptions_status(
    disruption_monitor: DisruptionMonitor = Depends(get_disruption_monitor),
) -> TrainServiceStatus:
    return await disruption_monitor.check_for_updates()
