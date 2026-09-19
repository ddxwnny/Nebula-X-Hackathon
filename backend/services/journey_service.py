from copy import deepcopy
import uuid
from fastapi import HTTPException, status
from models.disruptions import TrainDisruption, TrainServiceStatus
from models.journeys import (
    CreateJourneyRequest,
    DisruptionInfo,
    JourneyLegInput,
    JourneyRerouteResponse,
    JourneyStatusResponse,
    NewRouteSummary,
    RerouteChangeSummary,
    RouteDurationSummary,
)
from models.responses import Coordinates, Route, RouteLeg
from services.mrt_network import (
    check_station_overlap,
    get_stations_traversed,
    normalize_line_name,
)
from services.routing_service import RoutingService


class ActiveJourney:
    def __init__(
        self,
        journey_id: str,
        route_id: str,
        origin: Coordinates,
        destination: Coordinates,
        legs: list[JourneyLegInput],
        current_position: Coordinates | None = None,
    ):
        self.journey_id = journey_id
        self.route_id = route_id
        self.origin = origin
        self.destination = destination
        self.current_position = current_position or origin
        self.legs = legs
        self.remaining_legs = deepcopy(legs)

        # Precompute traversed stations for any MRT legs lacking explicit stations
        self.transport_lines_used: set[str] = set()
        for leg in self.remaining_legs:
            if leg.mode.lower() == "mrt":
                canon_line = normalize_line_name(leg.line)
                if canon_line:
                    self.transport_lines_used.add(canon_line)
                if not leg.stations:
                    leg.stations = get_stations_traversed(leg.line, leg.from_location, leg.to_location)

        self.status = "active"  # active, unaffected, reroute_required, rerouted, completed, reroute_failed
        self.active_disruption: TrainDisruption | None = None
        self.disruption_stations_affected: list[str] = []
        self.last_checked_disruption_hash: str | None = None
        self.previous_remaining_duration_min: float = round(sum(leg.duration_min for leg in self.remaining_legs), 1)
        self.last_reroute_response: JourneyRerouteResponse | None = None

    @property
    def remaining_duration_min(self) -> float:
        return round(sum(leg.duration_min for leg in self.remaining_legs), 1)


class JourneyService:
    """Manages active commuter journeys, status evaluation, and disruption rerouting."""

    def __init__(self, routing_service: RoutingService | None = None):
        self._journeys: dict[str, ActiveJourney] = {}
        self._routing_service = routing_service or RoutingService()

    def create_journey(self, request: CreateJourneyRequest) -> ActiveJourney:
        journey_id = f"journey_{uuid.uuid4().hex[:8]}"
        journey = ActiveJourney(
            journey_id=journey_id,
            route_id=request.route_id,
            origin=request.origin,
            destination=request.destination,
            legs=request.legs,
            current_position=request.current_position,
        )
        self._journeys[journey_id] = journey
        return journey

    def get_journey(self, journey_id: str) -> ActiveJourney | None:
        return self._journeys.get(journey_id)

    def evaluate_journey_disruption(
        self,
        journey: ActiveJourney,
        alert_status: TrainServiceStatus,
    ) -> tuple[str, TrainDisruption | None]:
        if journey.status == "completed":
            return journey.status, None

        # 1. Does journey use MRT in its remaining legs?
        remaining_mrt_legs = [leg for leg in journey.remaining_legs if leg.mode.lower() == "mrt"]
        if not remaining_mrt_legs or alert_status.status != 2 or not alert_status.affected_segments:
            # If disruption was cleared
            if journey.status == "reroute_required":
                journey.status = "active"
                journey.active_disruption = None
                journey.disruption_stations_affected = []
            elif journey.status not in {"rerouted", "completed"}:
                journey.status = "unaffected" if remaining_mrt_legs else "active"
            return journey.status, None

        # 2. Check each remaining MRT leg against each affected segment
        for leg in remaining_mrt_legs:
            leg_line = normalize_line_name(leg.line)
            for disruption in alert_status.affected_segments:
                dis_line = normalize_line_name(disruption.line)
                if not leg_line or not dis_line or leg_line != dis_line:
                    continue

                # 3. Check station overlap
                overlap = check_station_overlap(leg.stations, disruption.stations)
                if overlap:
                    current_hash = disruption.segment_hash()
                    if journey.last_checked_disruption_hash == current_hash and journey.status == "rerouted":
                        # Same unchanged disruption already handled for this journey
                        return journey.status, disruption

                    # Mark for reroute
                    journey.status = "reroute_required"
                    journey.active_disruption = disruption
                    journey.disruption_stations_affected = overlap
                    journey.last_checked_disruption_hash = current_hash
                    return "reroute_required", disruption

        if journey.status == "reroute_required":
            # No longer affected
            journey.status = "active"
            journey.active_disruption = None
            journey.disruption_stations_affected = []
        elif journey.status not in {"rerouted", "completed"}:
            journey.status = "unaffected"

        return journey.status, None

    def get_journey_status(self, journey_id: str, alert_status: TrainServiceStatus | None = None) -> JourneyStatusResponse:
        journey = self.get_journey(journey_id)
        if not journey:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Journey {journey_id} not found")

        data_status = "ok"
        if alert_status:
            self.evaluate_journey_disruption(journey, alert_status)
            data_status = alert_status.data_status

        disruption_info = None
        if journey.active_disruption:
            disruption_info = DisruptionInfo(
                line=journey.active_disruption.line,
                status="2",
                affected_stations=journey.disruption_stations_affected or journey.active_disruption.stations,
                free_public_bus=journey.active_disruption.free_public_bus,
                free_mrt_shuttle=journey.active_disruption.free_mrt_shuttle,
                mrt_shuttle_direction=journey.active_disruption.mrt_shuttle_direction,
                message=alert_status.messages[0] if alert_status and alert_status.messages else None,
            )

        return JourneyStatusResponse(
            journey_id=journey.journey_id,
            status=journey.status,
            disruption=disruption_info,
            data_status=data_status,
        )

    async def reroute_journey(
        self,
        journey_id: str,
        routing_service: RoutingService | None = None,
    ) -> JourneyRerouteResponse:
        journey = self.get_journey(journey_id)
        if not journey:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Journey {journey_id} not found")

        router = routing_service or self._routing_service
        prev_duration = journey.remaining_duration_min

        # Recalculate route beginning from current position, not original origin
        try:
            new_route = await self._calculate_alternative_route(
                router=router,
                start=journey.current_position,
                destination=journey.destination,
                disruption=journey.active_disruption,
            )
        except Exception as exc:
            journey.status = "reroute_failed"
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to recalculate remaining route: {exc}",
            ) from exc

        new_duration = new_route.total_duration_min
        additional_duration = round(max(0.0, new_duration - prev_duration), 1)

        # Build user-facing & machine-readable explanation
        reason_detail = self._build_reroute_reason(journey.active_disruption)

        # Convert RouteLeg to JourneyLegInput for remaining journey state
        journey.remaining_legs = [
            JourneyLegInput(
                mode=leg.mode,
                line=leg.line_name,
                from_location=leg.from_location,
                to_location=leg.to_location,
                duration_min=leg.duration_min,
            )
            for leg in new_route.legs
        ]
        journey.status = "rerouted"

        response = JourneyRerouteResponse(
            journey_id=journey.journey_id,
            status="rerouted",
            previous_route=RouteDurationSummary(remaining_duration_min=prev_duration),
            new_route=NewRouteSummary(
                remaining_duration_min=new_duration,
                legs=new_route.legs,
            ),
            change=RerouteChangeSummary(
                additional_duration_min=additional_duration,
                reason=reason_detail,
            ),
        )
        journey.last_reroute_response = response
        return response

    async def _calculate_alternative_route(
        self,
        router: RoutingService,
        start: Coordinates,
        destination: Coordinates,
        disruption: TrainDisruption | None,
    ) -> Route:
        # Fetch candidate public transit routes from router
        route = await router.get_route(start, destination)

        # If a disruption is active, check if LTA mitigations can be attached
        if disruption:
            mitigation_notes = []
            if disruption.free_mrt_shuttle:
                mitigation_notes.append("LTA Free MRT Shuttle: " + ", ".join(disruption.free_mrt_shuttle))
            if disruption.free_public_bus:
                mitigation_notes.append("LTA Free Public Bus: " + ", ".join(disruption.free_public_bus))

            # If shuttle is available, ensure legs communicate mitigation
            if mitigation_notes and route.legs:
                route.legs[0].line_name = (
                    f"{route.legs[0].line_name} ({mitigation_notes[0]})"
                    if route.legs[0].line_name
                    else mitigation_notes[0]
                )

        return route

    @staticmethod
    def _build_reroute_reason(disruption: TrainDisruption | None) -> dict[str, str]:
        if not disruption:
            return {
                "type": "route_update",
                "message": "Route recalculated for optimal arrival time.",
            }

        line_name = disruption.line
        has_shuttle = bool(disruption.free_mrt_shuttle)
        has_bus = bool(disruption.free_public_bus)

        if has_shuttle:
            message = f"Your planned {line_name} journey is affected. A free MRT shuttle is available."
        elif has_bus:
            message = f"Your planned {line_name} journey is affected. Free public bus boarding is available."
        else:
            message = f"{line_name} disruption affecting your planned route."

        return {
            "type": "train_disruption",
            "line": disruption.line,
            "message": message,
        }

