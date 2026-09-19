"""The one planning pipeline shared by /routes/plan and /routes/reroute.

A reroute can therefore never skip exit, lift-outage or accessibility checks,
and each response records what every stage actually did (`verification`).
"""

from datetime import date, time
from uuid import uuid4

from clients.lta_datamall_client import LtaDataMallClient
from models.requests import RoutePreferences
from models.responses import AccessibilityResult, Coordinates, CrowdAssessment, RainForecast, Route, RouteResponse, VerificationStep
from services.accessibility_service import AccessibilityService
from services.exit_routing_service import ExitRoutingService
from services.live_transit_service import LiveTransitService
from services.routing_service import RoutingService
from services.weather_service import WeatherService
from services.crowd_service import CrowdService


class RoutePipeline:
    def __init__(self, routing_service: RoutingService, accessibility_service: AccessibilityService, exit_routing_service: ExitRoutingService, weather_service: WeatherService, live_transit_service: LiveTransitService, crowd_service: CrowdService | None = None):
        self.routing_service = routing_service
        self.accessibility_service = accessibility_service
        self.exit_routing_service = exit_routing_service
        self.weather_service = weather_service
        self.live_transit_service = live_transit_service
        self.crowd_service = crowd_service or CrowdService()

    async def run(self, origin: Coordinates, destination: Coordinates, departure_date: date | None, departure_time: time | None, preferences: RoutePreferences) -> RouteResponse:
        if preferences.simulate_lift_maintenance:
            LtaDataMallClient().inject_simulated_maintenance(preferences.simulate_lift_maintenance)
        else:
            LtaDataMallClient.clear_simulated_maintenance()

        # "Leave now": resolve the Singapore time once, so OneMap's timetable and the live
        # bus check agree (OneMap would otherwise use the server's local clock).
        if departure_date is None or departure_time is None:
            now = self.live_transit_service.now()
            departure_date = departure_date or now.date()
            departure_time = departure_time or now.time().replace(second=0, microsecond=0)

        route = await self.routing_service.get_route(origin, destination, departure_date, departure_time)
        steps = [VerificationStep(stage="transit_route", status="done", detail=f"{len(route.legs)} legs from OneMap")]
        route = await self.exit_routing_service.apply(route, origin, destination, preferences)
        steps.append(_exit_step(route))
        accessibility, decision = await self.accessibility_service.apply(route, preferences)
        route = await self.live_transit_service.apply(route, departure_date, departure_time, step_free=preferences.step_free)
        # A step-free journey is only doable if an accessible bus actually turns up.
        no_accessible_bus = [leg.service_no for leg in route.legs if leg.live_bus and leg.live_bus.status == "no_suitable_bus"]
        if preferences.step_free and no_accessible_bus:
            accessibility.accessible = False
            decision.details.append(f"No wheelchair-accessible bus {', '.join(no_accessible_bus)} is due among the next buses you can reach.")
        steps.append(_accessibility_step(accessibility, preferences, no_accessible_bus))
        steps.append(_live_bus_step(route))
        if route.estimated_arrival:
            uncertain = route.estimated_arrival.basis == "uncertain"
            steps.append(VerificationStep(stage="arrival_estimate", status="warning" if uncertain else "done", detail=route.estimated_arrival.note if uncertain else f"Arrival time from {route.estimated_arrival.basis} data"))

        # Assess rain risk along the route
        route_points = [(pt.lat, pt.lon) for leg in route.legs for pt in leg.geometry]
        if not route_points:
            route_points = [(origin.lat, origin.lon), (destination.lat, destination.lon)]

        rain_assessment = await self.weather_service.assess_route_rain_risk(
            route_points,
            simulate_rain=preferences.simulate_rain,
            dry_route=preferences.dry_route,
        )
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
        steps.append(VerificationStep(stage="rain_forecast", status="done", detail=f"rain severity: {rain_forecast.rain_severity}"))
        crowd_assessment = await self.crowd_service.assess(route, enabled=preferences.crowd_control)
        if crowd_assessment.status != "unavailable":
            steps.append(VerificationStep(stage="crowd_control", status="warning" if crowd_assessment.overall_level == "high" else "done", detail=crowd_assessment.recommendation))
            if preferences.crowd_control and crowd_assessment.tradeoff:
                decision.details.append(crowd_assessment.tradeoff)

        return RouteResponse(
            request_id=str(uuid4()),
            origin=origin,
            destination=destination,
            recommended_route=route,
            accessibility=accessibility,
            decision=decision,
            rain_forecast=rain_forecast,
            crowd_assessment=crowd_assessment,
            verification=steps,
        )


def _exit_step(route: Route) -> VerificationStep:
    exits = route.exit_routing
    if exits is None or exits.fallback_reason == "no_mrt_segment":
        return VerificationStep(stage="exit_routing", status="skipped", detail="No MRT segment, so no station exits to check")
    outages = sum(marker.lift_status == "maintenance" for marker in exits.candidate_exits)
    if not exits.candidate_exits:
        return VerificationStep(stage="exit_routing", status="unavailable", detail="LTA station exit data unavailable")
    checked = f"{len(exits.candidate_exits)} exits checked against LTA lift outages ({outages} with an outage)"
    if exits.fallback_to_station_centroid:
        # At least one end kept OneMap's station access route instead of a verified exit.
        return VerificationStep(stage="exit_routing", status="warning", detail=f"{checked}, but no verified exit route for one station; its original access route is kept")
    return VerificationStep(stage="exit_routing", status="done", detail=checked)


def _accessibility_step(accessibility: AccessibilityResult, preferences: RoutePreferences, no_accessible_bus: list[str]) -> VerificationStep:
    if not preferences.step_free:
        return VerificationStep(stage="accessibility", status="skipped", detail="Step-free routing not requested")
    if no_accessible_bus:
        return VerificationStep(stage="accessibility", status="warning", detail=f"No wheelchair-accessible bus {', '.join(no_accessible_bus)} due soon")
    if accessibility.accessible:
        return VerificationStep(stage="accessibility", status="done", detail="Step-free route verified")
    return VerificationStep(stage="accessibility", status="warning", detail="Step-free not fully verified: some connections lack accessibility data or use stairs")


def _live_bus_step(route: Route) -> VerificationStep:
    bus_legs = [leg for leg in route.legs if leg.mode == "bus"]
    statuses = [leg.live_bus.status for leg in bus_legs if leg.live_bus]
    if not bus_legs:
        return VerificationStep(stage="live_bus_arrivals", status="skipped", detail="No bus legs")
    if not statuses:
        return VerificationStep(stage="live_bus_arrivals", status="unavailable", detail="Bus legs have no LTA stop data; timetable used")
    if all(status == "outside_live_window" for status in statuses):
        return VerificationStep(stage="live_bus_arrivals", status="skipped", detail="Journey does not start now; timetable used")
    live, no_bus, unavailable = statuses.count("live"), statuses.count("no_suitable_bus"), statuses.count("unavailable")
    if no_bus:
        return VerificationStep(stage="live_bus_arrivals", status="warning", detail=f"No wheelchair-accessible bus due soon on {no_bus} of {len(bus_legs)} bus legs")
    if live:
        return VerificationStep(stage="live_bus_arrivals", status="done", detail=f"{live} of {len(bus_legs)} bus legs on live LTA arrivals")
    if unavailable:
        return VerificationStep(stage="live_bus_arrivals", status="unavailable", detail="LTA live arrivals unavailable; timetable used")
    return VerificationStep(stage="live_bus_arrivals", status="done", detail="You reach the bus stop after the buses LTA currently reports; timetable used")
