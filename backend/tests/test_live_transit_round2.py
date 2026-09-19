"""Review round 2: pipeline verification branches, leave-now resolution, simulated outages, edge cases."""

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from clients.lta_datamall_client import LtaDataMallClient
from models.requests import RoutePreferences
from models.responses import AccessibilityResult, Coordinates, ExitMarker, ExitRoutingMetadata, Route, RouteDecision, RouteLeg
from services.live_transit_service import LiveTransitService
from services.route_pipeline import RoutePipeline
from services.routing_service import SGT, RoutingService
from tests.test_live_transit import NOW, FakeLta, RecordingWeather, apply, bus_route, eta


class ConfigurableRouting:
    def __init__(self, route: Route):
        self.route, self.calls = route, []

    async def get_route(self, origin, destination, departure_date, departure_time):
        self.calls.append((departure_date, departure_time))
        return self.route


class ConfigurableExits:
    def __init__(self, metadata: ExitRoutingMetadata | None):
        self.metadata = metadata

    async def apply(self, route, origin, destination, preferences):
        route.exit_routing = self.metadata
        return route


class ConfigurableAccessibility:
    def __init__(self, accessible: bool = True):
        self.accessible = accessible

    async def apply(self, route, preferences):
        return (AccessibilityResult(step_free=preferences.step_free, accessible=self.accessible, verification="verified" if self.accessible else "unverified", stairs_used=False, unknown_segments=0), RouteDecision(reason="step_free_preference", summary="ok"))


def marker(code: str, outage: bool = False) -> ExitMarker:
    return ExitMarker(id=f"X-{code}", station_id="X", station_name="X", exit_id=code, exit_name=f"Exit {code}", lat=1.3, lon=103.8, lift_status="maintenance" if outage else "no_reported_outage")


VERIFIED_EXITS = ExitRoutingMetadata(enabled=True, fallback_to_station_centroid=False, candidate_exits=[marker("A", outage=True), marker("B")])


def run(*, route=None, exits=VERIFIED_EXITS, accessible=True, lta=None, departure=(NOW.date(), NOW.time()), **prefs):
    routing = ConfigurableRouting(route or bus_route())
    pipeline = RoutePipeline(routing, ConfigurableAccessibility(accessible), ConfigurableExits(exits), RecordingWeather(), LiveTransitService(lta or FakeLta(None), clock=lambda: NOW))
    response = asyncio.run(pipeline.run(Coordinates(lat=1.3, lon=103.8), Coordinates(lat=1.31, lon=103.81), *departure, RoutePreferences(**{"stepFree": True, **prefs})))
    return response, {step.stage: step for step in response.verification}, routing


class TestVerificationBranches(unittest.TestCase):
    def test_no_mrt_segment_skips_exit_check(self):
        _, steps, _ = run(exits=ExitRoutingMetadata(enabled=False, fallback_to_station_centroid=True, fallback_reason="no_mrt_segment"))
        self.assertEqual(steps["exit_routing"].status, "skipped")

    def test_missing_exit_data_is_unavailable(self):
        _, steps, _ = run(exits=ExitRoutingMetadata(enabled=False, fallback_to_station_centroid=True, fallback_reason="station_exit_data_unavailable"))
        self.assertEqual(steps["exit_routing"].status, "unavailable")

    def test_one_station_without_verified_exit_is_a_warning(self):
        partial = ExitRoutingMetadata(enabled=True, fallback_to_station_centroid=True, fallback_reason="station_exit_data_unavailable", candidate_exits=[marker("A")])
        _, steps, _ = run(exits=partial)
        self.assertEqual(steps["exit_routing"].status, "warning")
        self.assertIn("no verified exit route", steps["exit_routing"].detail)

    def test_unverified_step_free_is_a_warning(self):
        _, steps, _ = run(accessible=False)
        self.assertEqual(steps["accessibility"].status, "warning")

    def test_no_accessible_bus_fails_step_free_and_warns(self):
        lta = FakeLta([{"ServiceNo": "143", "NextBus": eta(6, feature=""), "NextBus2": eta(12, feature="")}])
        response, steps, _ = run(lta=lta)
        self.assertFalse(response.accessibility.accessible)
        self.assertTrue(any("wheelchair-accessible bus 143" in detail for detail in response.decision.details))
        self.assertEqual(steps["accessibility"].status, "warning")
        self.assertEqual(steps["live_bus_arrivals"].status, "warning")
        self.assertEqual(steps["arrival_estimate"].status, "warning")

    def test_future_journey_skips_live_buses(self):
        tomorrow = NOW + timedelta(days=1)
        _, steps, _ = run(route=bus_route(scheduled_offset_min=24 * 60 + 5), departure=(tomorrow.date(), tomorrow.time()), lta=FakeLta([{"ServiceNo": "143", "NextBus": eta(9)}]))
        self.assertEqual(steps["live_bus_arrivals"].status, "skipped")
        self.assertEqual(steps["arrival_estimate"].status, "done")

    def test_route_without_buses_skips_live_buses(self):
        mrt_only = Route(total_duration_min=10, distance_m=100, legs=[RouteLeg(mode="mrt", duration_min=10, distance_m=100, from_location="A", to_location="B", scheduled_departure=NOW + timedelta(minutes=2))])
        _, steps, _ = run(route=mrt_only)
        self.assertEqual(steps["live_bus_arrivals"].status, "skipped")


class TestLeaveNow(unittest.TestCase):
    def test_leave_now_resolves_singapore_time_for_onemap_and_live_buses(self):
        response, steps, routing = run(departure=(None, None), lta=FakeLta([{"ServiceNo": "143", "NextBus": eta(9)}]))
        self.assertEqual(routing.calls, [(NOW.date(), NOW.time().replace(second=0, microsecond=0))])
        self.assertEqual(response.recommended_route.estimated_arrival.departure, NOW)
        self.assertEqual(steps["live_bus_arrivals"].status, "done")

    def test_departure_that_already_started_does_not_use_live_data(self):
        lta = FakeLta([{"ServiceNo": "143", "NextBus": eta(9)}])
        route = apply(lta, bus_route(scheduled_offset_min=-5), start=NOW - timedelta(minutes=10))
        self.assertEqual(route.legs[1].live_bus.status, "outside_live_window")


class TestSimulatedOutageThroughPipeline(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(LtaDataMallClient, "all_lift_maintenance", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(LtaDataMallClient.clear_simulated_maintenance)

    def outages(self):
        return asyncio.run(LtaDataMallClient().lift_statuses("NOVENA"))

    def test_simulated_outage_injected_then_cleared(self):
        run(simulateLiftMaintenance="NOVENA")
        self.assertIn("SIM-LIFT-1", self.outages())
        run()
        self.assertNotIn("SIM-LIFT-1", self.outages())


class TestEdgeCases(unittest.TestCase):
    def test_numeric_stop_code_keeps_leading_zero(self):
        leg = RoutingService._to_leg({"mode": "BUS", "duration": 60, "transitLeg": True, "routeId": "174", "startTime": int(NOW.timestamp() * 1000), "from": {"name": "A", "stopCode": 4167}, "to": {"name": "B"}, "legGeometry": {"points": ""}})
        self.assertEqual(leg.stop_code, "04167")

    def test_out_of_range_start_time_ignored(self):
        leg = RoutingService._to_leg({"mode": "BUS", "duration": 60, "transitLeg": True, "startTime": 10 ** 20, "from": {"name": "A"}, "to": {"name": "B"}, "legGeometry": {"points": ""}})
        self.assertIsNone(leg.scheduled_departure)

    def test_delay_only_from_gps_tracked_buses(self):
        lta = FakeLta([{"ServiceNo": "143", "NextBus": eta(9, monitored=0)}])
        live = apply(lta, bus_route()).legs[1].live_bus
        self.assertEqual(live.status, "live")
        self.assertIsNone(live.delay_vs_schedule_min)
        self.assertIn("not GPS-tracked", live.message)

    def test_delay_measures_the_timetabled_trip_even_if_it_ran_early(self):
        # Timetabled +5 bus ran early at +3 (rider reaches the stop at +4 and misses it).
        lta = FakeLta([{"ServiceNo": "143", "NextBus": eta(3), "NextBus2": eta(15)}])
        live = apply(lta, bus_route()).legs[1].live_bus
        self.assertEqual(live.delay_vs_schedule_min, -2.0)
        self.assertEqual(live.boarding_eta, NOW + timedelta(minutes=15))

    def test_message_uses_clock_time_and_arriving_now(self):
        lta = FakeLta([{"ServiceNo": "143", "NextBus": eta(4.5)}])
        live = apply(lta, bus_route()).legs[1].live_bus
        self.assertIn("10:04", live.message)
        self.assertIn("in 4 min", live.message)

    def test_transit_leg_without_timetable_is_uncertain(self):
        route = Route(total_duration_min=10, distance_m=100, legs=[RouteLeg(mode="mrt", duration_min=10, distance_m=100, from_location="A", to_location="B")])
        self.assertEqual(apply(FakeLta(None), route).estimated_arrival.basis, "uncertain")

    def test_stop_arrivals_unavailable_and_missing_service(self):
        service = LiveTransitService(FakeLta(None), clock=lambda: NOW)
        self.assertEqual(asyncio.run(service.stop_arrivals("40189")).status, "unavailable")
        service = LiveTransitService(FakeLta([{"ServiceNo": "124", "NextBus": eta(3)}]), clock=lambda: NOW)
        self.assertEqual(asyncio.run(service.stop_arrivals("40189", "143")).status, "no_service")
        self.assertEqual(asyncio.run(service.stop_arrivals("40189")).status, "live")


if __name__ == "__main__":
    unittest.main()
