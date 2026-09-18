from uuid import uuid4
from fastapi import APIRouter, Depends
from models.requests import RouteRequest
from models.responses import RouteResponse
from services.geocoding_service import GeocodingService
from services.routing_service import RoutingService

router = APIRouter(tags=["routes"])


def get_geocoding_service() -> GeocodingService:
    return GeocodingService()


def get_routing_service() -> RoutingService:
    return RoutingService()


@router.post("/routes/plan", response_model=RouteResponse)
async def plan_route(request: RouteRequest, geocoding_service: GeocodingService = Depends(get_geocoding_service), routing_service: RoutingService = Depends(get_routing_service)) -> RouteResponse:
    origin = await geocoding_service.resolve_location(request.origin)
    destination = await geocoding_service.resolve_location(request.destination)
    return RouteResponse(request_id=str(uuid4()), origin=origin, destination=destination, recommended_route=await routing_service.get_route(origin, destination, request.departure_date, request.departure_time))
