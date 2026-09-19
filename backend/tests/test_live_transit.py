import asyncio
import unittest
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from api import routes
from clients.lta_datamall_client import LtaDataMallClient
from main import app
from models.requests import RoutePreferences
from models.responses import AccessibilityResult, Coordinates, ExitMarker, ExitRoutingMetadata, Route, RouteDecision, RouteLeg, RouteResponse
from services.live_transit_service import LiveTransitService
from services.route_pipeline import RoutePipeline
from services.routing_service import SGT, RoutingService

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=SGT)


def eta(minutes: float, feature: str = "WAB", monitored: int = 1) -> dict:
    return {"EstimatedArrival": (NOW + timedelta(minutes=minutes)).isoformat(), "Feature": feature, "Load": "SEA", "Type": "SD", "Monitored": monitored}


class FakeLta:
    def __init__(self, services):
        self.services, self.calls = services, 0

    async def bus_arrivals(self, stop_code):
        self.calls += 1
        return self.services


def bus_route(scheduled_offset_min: float = 5, walk_min: float = 4) -> Route:
    return Route(total_duration_min=30, distance_m=5000, legs=[
        RouteLeg(mode="walk", duration_min=walk_min, distance_m=300, from_location="Origin", to_location="Stop"),
        RouteLeg(mode="bus", duration_min=15, distance_m=4000, from_location="Stop", to_location="Stop 2", stop_code="40189", service_no="143", scheduled_departure=NOW + timedelta(minutes=scheduled_offset_min)),
        RouteLeg(mode="walk", duration_min=3, distance_m=200, from_location="Stop 2", to_location="Destination"),
    ])


def apply(lta, route, *, start=NOW, step_free=True):
    service = LiveTransitService(lta, clock=lambda: NOW)
    return asyncio.run(service.apply(route, start.date(), start.time(), step_free=step_free))


class TestLiveTransit(unittest.TestCase):
    def test_boards_first_reachable_wheelchair_accessible_bus(self):
        # Rider reaches the stop at +4 min: the +2 bus is gone, the +6 bus is not wheelchair accessible.
        lta = FakeLta([{"ServiceNo": "143", "NextBus": eta(2), "NextBus2": eta(6, feature=""), "NextBus3": eta(9)}])
        route = apply(lta, bus_route())
        live = route.legs[1].live_bus
        self.assertEqual(live.status, "live")
        self.assertEqual(live.boarding_eta, NOW + timedelta(minutes=9))
        self.assertTrue(live.boarding_bus_wheelchair_accessible)
        self.assertEqual(live.skipped_inaccessible, 1)
        # Bus lateness is the first bus the rider could meet (+6) vs the timetable (+5), not the accessible-bus wait.
        self.assertEqual(live.delay_vs_schedule_min, 1.0)
        # Arrival = board at +9, ride 15, walk 3.
        self.assertEqual(route.estimated_arrival.arrival, NOW + timedelta(minutes=27))
        self.assertEqual(route.estimated_arrival.basis, "live")

    def test_no_delay_reported_when_rider_reaches_stop_after_timetable(self):
        lta = FakeLta([{"ServiceNo": "143", "NextBus": eta(9)}])
        live = apply(lta, bus_route(scheduled_offset_min=3)).legs[1].live_bus
        self.assertEqual(live.status, "live")
        self.assertIsNone(live.delay_vs_schedule_min)

    def test_non_step_free_rider_can_take_any_bus(self):
        lta = FakeLta([{"ServiceNo": "143", "NextBus": eta(6, feature=""), "NextBus2": eta(9)}])
        live = apply(lta, bus_route(), step_free=False).legs[1].live_bus
        self.assertEqual(live.boarding_eta, NOW + timedelta(minutes=6))
        self.assertFalse(live.boarding_bus_wheelchair_accessible)
        self.assertEqual(live.skipped_inaccessible, 0)

    def test_no_accessible_bus_pushes_arrival_past_last_listed_bus(self):
        lta = FakeLta([{"ServiceNo": "143", "NextBus": eta(6, feature=""), "NextBus2": eta(12, feature="")}])
        route = apply(lta, bus_route())
        self.assertEqual(route.legs[1].live_bus.status, "no_suitable_bus")
        self.assertIn("wheelchair-accessible", route.legs[1].live_bus.message)
        self.assertEqual(route.estimated_arrival.basis, "uncertain")
        # Cannot board before the last listed bus (+12): at least +12 + 15 ride + 3 walk.
        self.assertEqual(route.estimated_arrival.arrival, NOW + timedelta(minutes=30))
        self.assertIn("later than this", route.estimated_arrival.note)

    def test_stop_reached_beyond_live_horizon_uses_timetable(self):
        # A long first leg: rider reaches the stop at +40, after every bus LTA currently reports.
        lta = FakeLta([{"ServiceNo": "143", "NextBus": eta(5), "NextBus2": eta(12)}])
        route = apply(lta, bus_route(scheduled_offset_min=42, walk_min=40))
        self.assertEqual(route.legs[1].live_bus.status, "beyond_live_horizon")
        self.assertEqual(route.estimated_arrival.basis, "scheduled")
        self.assertEqual(route.estimated_arrival.arrival, NOW + timedelta(minutes=42 + 15 + 3))

    def test_future_journey_does_not_use_live_arrivals(self):
        lta = FakeLta([{"ServiceNo": "143", "NextBus": eta(9)}])
        route = apply(lta, bus_route(scheduled_offset_min=24 * 60 + 5), start=NOW + timedelta(days=1))
        self.assertEqual(route.legs[1].live_bus.status, "outside_live_window")
        self.assertEqual(lta.calls, 0)
        self.assertEqual(route.estimated_arrival.basis, "scheduled")

    def test_live_data_unavailable(self):
        route = apply(FakeLta(None), bus_route())
        self.assertEqual(route.legs[1].live_bus.status, "unavailable")
        self.assertEqual(route.estimated_arrival.basis, "scheduled")

    def test_other_services_at_stop_ignored(self):
        lta = FakeLta([{"ServiceNo": "124", "NextBus": eta(5)}])
        self.assertEqual(apply(lta, bus_route()).legs[1].live_bus.status, "unavailable")

    def test_service_with_no_upcoming_buses_is_unavailable(self):
        lta = FakeLta([{"ServiceNo": "143", "NextBus": {"EstimatedArrival": ""}, "NextBus2": {}, "NextBus3": {}}])
        self.assertEqual(apply(lta, bus_route()).legs[1].live_bus.status, "unavailable")

    def test_malformed_lta_entries_are_ignored(self):
        lta = FakeLta([None, "junk", {"ServiceNo": 143, "Operator": 7, "NextBus": eta(8), "NextBus2": {"EstimatedArrival": "not-a-date"}}])
        live = apply(lta, bus_route()).legs[1].live_bus
        self.assertEqual(live.status, "live")
        self.assertEqual(len(live.next_buses), 1)

    def test_missed_timetabled_connection_is_uncertain(self):
        route = Route(total_duration_min=20, distance_m=8000, legs=[
            RouteLeg(mode="walk", duration_min=5, distance_m=300, from_location="Origin", to_location="Stn"),
            RouteLeg(mode="mrt", duration_min=10, distance_m=7000, from_location="NOVENA", to_location="Stn 2", scheduled_departure=NOW + timedelta(minutes=3)),
        ])
        result = apply(FakeLta(None), route)
        self.assertEqual(result.estimated_arrival.basis, "uncertain")
        self.assertIn("Tight connection", result.estimated_arrival.note)

    def test_mrt_only_route_uses_timetable(self):
        route = Route(total_duration_min=20, distance_m=8000, legs=[
            RouteLeg(mode="walk", duration_min=5, distance_m=300, from_location="Origin", to_location="Stn"),
            RouteLeg(mode="mrt", duration_min=10, distance_m=7000, from_location="Stn", to_location="Stn 2", scheduled_departure=NOW + timedelta(minutes=8)),
        ])
        result = apply(FakeLta(None), route)
        self.assertEqual(result.estimated_arrival.arrival, NOW + timedelta(minutes=18))
        self.assertEqual(result.estimated_arrival.basis, "scheduled")


class TestOneMapLegParsing(unittest.TestCase):
    def test_bus_leg_keeps_stop_code_service_and_schedule(self):
        leg = RoutingService._to_leg({
            "mode": "BUS", "duration": 900, "distance": 4000, "transitLeg": True, "routeId": "143", "route": "TTS BUS 143",
            "startTime": int(NOW.timestamp() * 1000), "from": {"name": "NEWTON STN EXIT B", "stopCode": "40189"}, "to": {"name": "X"}, "legGeometry": {"points": ""},
        })
        self.assertEqual((leg.stop_code, leg.service_no), ("40189", "143"))
        self.assertEqual(leg.scheduled_departure, NOW)

    def test_mrt_leg_keeps_schedule_but_no_bus_ids(self):
        leg = RoutingService._to_leg({"mode": "SUBWAY", "duration": 600, "transitLeg": True, "routeId": "NS", "startTime": int(NOW.timestamp() * 1000), "from": {"name": "A", "stopCode": "NS16"}, "to": {"name": "B"}, "legGeometry": {"points": ""}})
        self.assertEqual(leg.mode, "mrt")
        self.assertEqual(leg.scheduled_departure, NOW)
        self.assertIsNone(leg.stop_code)
        self.assertIsNone(leg.service_no)

    def test_walk_leg_has_no_transit_ids(self):
        leg = RoutingService._to_leg({"mode": "WALK", "duration": 60, "startTime": 1, "from": {"name": "A", "stopCode": "1"}, "to": {"name": "B"}, "legGeometry": {"points": ""}})
        self.assertIsNone(leg.stop_code)
        self.assertIsNone(leg.scheduled_departure)

    def test_boolean_start_time_ignored(self):
        leg = RoutingService._to_leg({"mode": "BUS", "duration": 60, "transitLeg": True, "startTime": True, "from": {"name": "A"}, "to": {"name": "B"}, "legGeometry": {"points": ""}})
        self.assertIsNone(leg.scheduled_departure)


# --- The real pipeline, run end to end with recording fakes ---------------------------

class FakeRouting:
    async def get_route(self, origin, destination, departure_date, departure_time):
        return bus_route()


class RecordingExitRouting:
    def __init__(self):
        self.calls = 0

    async def apply(self, route, origin, destination, preferences):
        self.calls += 1
        route.exit_routing = ExitRoutingMetadata(enabled=True, fallback_to_station_centroid=False, candidate_exits=[
            ExitMarker(id="X-A", station_id="X", station_name="X", exit_id="A", exit_name="Exit A", lat=1.3, lon=103.8, lift_status="maintenance"),
            ExitMarker(id="X-B", station_id="X", station_name="X", exit_id="B", exit_name="Exit B", lat=1.3, lon=103.8),
        ])
        return route


class RecordingAccessibility:
    def __init__(self):
        self.calls = 0

    async def apply(self, route, preferences):
        self.calls += 1
        return (AccessibilityResult(step_free=preferences.step_free, accessible=True, verification="verified", stairs_used=False, unknown_segments=0), RouteDecision(reason="step_free_preference", summary="ok"))


class RecordingWeather:
    def __init__(self):
        self.kwargs = None

    async def assess_route_rain_risk(self, points, **kwargs):
        self.kwargs = kwargs
        return {"rain_along_route": False, "rain_severity": "none", "current_rain": {"currently_raining": False, "rainfall_mm": 0.0}, "point_forecasts": [], "recommendation": "ok"}


class TestRoutePipeline(unittest.TestCase):
    def build(self, lta):
        self.exits, self.access, self.weather = RecordingExitRouting(), RecordingAccessibility(), RecordingWeather()
        return RoutePipeline(FakeRouting(), self.access, self.exits, self.weather, LiveTransitService(lta, clock=lambda: NOW))

    def run_pipeline(self, pipeline, **prefs):
        preferences = RoutePreferences(**{"stepFree": True, **prefs})
        return asyncio.run(pipeline.run(Coordinates(lat=1.3, lon=103.8), Coordinates(lat=1.31, lon=103.81), NOW.date(), NOW.time(), preferences))

    def test_every_stage_runs_and_is_recorded(self):
        lta = FakeLta([{"ServiceNo": "143", "NextBus": eta(9)}])
        response = self.run_pipeline(self.build(lta), simulateRain=True, dryRoute=True)
        self.assertEqual((self.exits.calls, self.access.calls), (1, 1))
        self.assertEqual(self.weather.kwargs, {"simulate_rain": True, "dry_route": True})
        self.assertEqual(response.recommended_route.legs[1].live_bus.status, "live")
        self.assertEqual(response.recommended_route.estimated_arrival.basis, "live")
        steps = {step.stage: step for step in response.verification}
        self.assertEqual(list(steps), ["transit_route", "exit_routing", "accessibility", "live_bus_arrivals", "arrival_estimate", "rain_forecast"])
        self.assertEqual(steps["exit_routing"].status, "done")
        self.assertIn("2 exits checked", steps["exit_routing"].detail)
        self.assertIn("1 with an outage", steps["exit_routing"].detail)
        self.assertEqual(steps["live_bus_arrivals"].detail, "1 of 1 bus legs on live LTA arrivals")

    def test_verification_reports_what_did_not_happen(self):
        response = self.run_pipeline(self.build(FakeLta(None)), stepFree=False)
        steps = {step.stage: step for step in response.verification}
        self.assertEqual(steps["accessibility"].status, "skipped")
        self.assertEqual(steps["live_bus_arrivals"].status, "unavailable")


# --- LTA BusArrival client -----------------------------------------------------------

class FakeHttp:
    calls: list = []
    status = 200
    payload: object = {"Services": [{"ServiceNo": "143"}]}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        FakeHttp.calls.append((url, params, headers))
        request = httpx.Request("GET", url)
        return httpx.Response(FakeHttp.status, json=FakeHttp.payload, request=request)


class TestBusArrivalClient(unittest.TestCase):
    def setUp(self):
        FakeHttp.calls, FakeHttp.status, FakeHttp.payload = [], 200, {"Services": [{"ServiceNo": "143"}, "junk"]}
        LtaDataMallClient._bus_arrival_cache.clear()
        self.addCleanup(LtaDataMallClient._bus_arrival_cache.clear)
        settings = SimpleNamespace(lta_datamall_account_key="key", http_timeout_seconds=5)
        for target, value in (("clients.lta_datamall_client.httpx.AsyncClient", FakeHttp), ("clients.lta_datamall_client.get_settings", lambda: settings)):
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_requests_stop_and_keeps_only_service_objects(self):
        services = asyncio.run(LtaDataMallClient().bus_arrivals("40189"))
        self.assertEqual(services, [{"ServiceNo": "143"}])
        url, params, headers = FakeHttp.calls[0]
        self.assertTrue(url.endswith("/v3/BusArrival"))
        self.assertEqual(params, {"BusStopCode": "40189"})
        self.assertEqual(headers["AccountKey"], "key")

    def test_cached_across_instances_until_ttl(self):
        asyncio.run(LtaDataMallClient().bus_arrivals("40189"))
        asyncio.run(LtaDataMallClient().bus_arrivals("40189"))
        self.assertEqual(len(FakeHttp.calls), 1)
        until, services = LtaDataMallClient._bus_arrival_cache["40189"]
        LtaDataMallClient._bus_arrival_cache["40189"] = (datetime.now(SGT) - timedelta(seconds=1), services)
        asyncio.run(LtaDataMallClient().bus_arrivals("40189"))
        self.assertEqual(len(FakeHttp.calls), 2)

    def test_rate_limit_returns_none_and_is_not_retried_immediately(self):
        FakeHttp.status = 429
        self.assertIsNone(asyncio.run(LtaDataMallClient().bus_arrivals("40189")))
        self.assertIsNone(asyncio.run(LtaDataMallClient().bus_arrivals("40189")))
        self.assertEqual(len(FakeHttp.calls), 1)

    def test_retries_after_failure_cache_expires(self):
        FakeHttp.status = 429
        self.assertIsNone(asyncio.run(LtaDataMallClient().bus_arrivals("40189")))
        _, services = LtaDataMallClient._bus_arrival_cache["40189"]
        LtaDataMallClient._bus_arrival_cache["40189"] = (datetime.now(SGT) - timedelta(seconds=1), services)
        FakeHttp.status = 200
        self.assertEqual(asyncio.run(LtaDataMallClient().bus_arrivals("40189")), [{"ServiceNo": "143"}])
        self.assertEqual(len(FakeHttp.calls), 2)

    def test_non_list_services_is_unavailable(self):
        FakeHttp.payload = {"Services": "oops"}
        self.assertIsNone(asyncio.run(LtaDataMallClient().bus_arrivals("40189")))

    def test_cache_is_bounded(self):
        with patch.object(LtaDataMallClient, "BUS_ARRIVAL_CACHE_MAX", 3):
            for code in ("10001", "10002", "10003", "10004"):
                asyncio.run(LtaDataMallClient().bus_arrivals(code))
        self.assertLessEqual(len(LtaDataMallClient._bus_arrival_cache), 3)
        self.assertIn("10004", LtaDataMallClient._bus_arrival_cache)


# --- HTTP endpoints ---------------------------------------------------------------------

class RecordingPipeline:
    """Stands in for RoutePipeline and records what the endpoint asked it to plan."""
    def __init__(self):
        self.calls = []

    async def run(self, origin, destination, departure_date, departure_time, preferences):
        self.calls.append({"origin": origin, "departure_date": departure_date, "departure_time": departure_time, "preferences": preferences})
        exits = ExitRoutingMetadata(enabled=True, fallback_to_station_centroid=False, candidate_exits=[
            ExitMarker(id=f"X-{i}", station_id="X", station_name="X", exit_id=str(i), exit_name=f"Exit {i}", lat=1.3, lon=103.8) for i in range(3)
        ])
        return RouteResponse(
            request_id="r", origin=origin, destination=destination,
            recommended_route=Route(total_duration_min=10, distance_m=100, legs=[], exit_routing=exits),
            accessibility=AccessibilityResult(step_free=True, accessible=True, verification="verified", stairs_used=False, unknown_segments=0),
            decision=RouteDecision(reason="step_free_preference", summary="ok"),
        )


class FakeGeocoder:
    async def resolve_location(self, location):
        return location.coordinates() or Coordinates(lat=1.3, lon=103.8, label=location.address)


class TestRouteEndpoints(unittest.TestCase):
    def setUp(self):
        self.pipeline = RecordingPipeline()
        app.dependency_overrides[routes.get_route_pipeline] = lambda: self.pipeline
        app.dependency_overrides[routes.get_geocoding_service] = FakeGeocoder
        app.dependency_overrides[routes.get_live_transit_service] = lambda: LiveTransitService(FakeLta([{"ServiceNo": "143", "NextBus": eta(3)}, {"ServiceNo": "124", "NextBus": eta(5)}]), clock=lambda: NOW)
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def body(self, **extra):
        return {"origin": {"address": "Ang Mo Kio MRT Station"}, "destination": {"address": "SGH"}, "departure_date": "2026-01-01", "departure_time": "08:00", "preferences": {"stepFree": True}, **extra}

    def test_reroute_runs_pipeline_from_current_location_departing_now(self):
        response = self.client.post("/api/v1/routes/reroute", json=self.body(current_location={"lat": 1.31, "lon": 103.85}, reason="missed_bus"))
        self.assertEqual(response.status_code, 200, response.text)
        (call,) = self.pipeline.calls
        self.assertEqual((call["origin"].lat, call["origin"].lon), (1.31, 103.85))
        self.assertEqual(call["origin"].label, "Your current location")
        departs = datetime.combine(call["departure_date"], call["departure_time"], SGT)
        self.assertLess(abs(departs - datetime.now(SGT)), timedelta(minutes=2), "reroute departs now (SGT), not at the original time")
        self.assertTrue(call["preferences"].step_free)
        reroute = response.json()["reroute"]
        self.assertEqual((reroute["origin_source"], reroute["reason"], reroute["exits_checked"]), ("current_location", "missed_bus", 3))

    def test_reroute_without_location_uses_original_origin(self):
        response = self.client.post("/api/v1/routes/reroute", json=self.body())
        self.assertEqual(response.json()["reroute"]["origin_source"], "original_origin")
        self.assertEqual(self.pipeline.calls[0]["origin"].label, "Ang Mo Kio MRT Station")

    def test_plan_uses_same_pipeline_with_requested_time(self):
        response = self.client.post("/api/v1/routes/plan", json=self.body())
        self.assertEqual(response.status_code, 200, response.text)
        (call,) = self.pipeline.calls
        self.assertEqual((call["departure_date"], call["departure_time"]), (date(2026, 1, 1), time(8, 0)))
        self.assertIsNone(response.json()["reroute"])

    def test_bus_arrivals_endpoint_filters_service(self):
        response = self.client.get("/api/v1/transit/bus-arrivals", params={"stop_code": "40189", "service_no": "143"})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "live")
        self.assertEqual([service["service_no"] for service in body["services"]], ["143"])
        self.assertTrue(body["services"][0]["next_buses"][0]["wheelchair_accessible"])

    def test_bus_arrivals_endpoint_rejects_bad_stop_code(self):
        self.assertEqual(self.client.get("/api/v1/transit/bus-arrivals", params={"stop_code": "../x"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
