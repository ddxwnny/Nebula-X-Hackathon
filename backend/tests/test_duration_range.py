import math
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from main import app
from models.requests import RoutePreferences
from models.responses import (
    AccessibilityResult,
    Coordinates,
    DurationRange,
    Route,
    RouteDecision,
    RouteLeg,
)
from utils.duration import (
    DISPLAY_INTERVAL_MINUTES,
    duration_to_range,
    format_duration_range,
    format_duration_unit,
)


class TestDurationRangeUnit(unittest.TestCase):
    def test_duration_52_4_returns_50_to_55(self):
        result = duration_to_range(52.4)
        self.assertEqual(result.min, 50)
        self.assertEqual(result.max, 55)

    def test_duration_57_1_returns_55_to_60(self):
        result = duration_to_range(57.1)
        self.assertEqual(result.min, 55)
        self.assertEqual(result.max, 60)

    def test_exact_boundary_returns_non_zero_range(self):
        result = duration_to_range(50.0)
        self.assertEqual(result.min, 50)
        self.assertEqual(result.max, 55)

        boundary_5 = duration_to_range(5.0)
        self.assertEqual(boundary_5.min, 5)
        self.assertEqual(boundary_5.max, 10)

    def test_short_duration_returns_rounded_single_value(self):
        r_1_2 = duration_to_range(1.2)
        self.assertEqual(r_1_2.min, 1)
        self.assertEqual(r_1_2.max, 1)

        r_2_1 = duration_to_range(2.1)
        self.assertEqual(r_2_1.min, 2)
        self.assertEqual(r_2_1.max, 2)

        r_3_4 = duration_to_range(3.4)
        self.assertEqual(r_3_4.min, 3)
        self.assertEqual(r_3_4.max, 3)

        r_4_8 = duration_to_range(4.8)
        self.assertEqual(r_4_8.min, 5)
        self.assertEqual(r_4_8.max, 5)

        r_zero = duration_to_range(0.0)
        self.assertEqual(r_zero.min, 0)
        self.assertEqual(r_zero.max, 0)

    def test_duration_is_inside_range(self):
        test_durations = [5.0, 12.7, 37.2, 52.4, 61.8, 84.1, 118.0]
        for duration in test_durations:
            with self.subTest(duration=duration):
                result = duration_to_range(duration)
                self.assertLessEqual(result.min, duration)
                self.assertLessEqual(duration, result.max)
                self.assertGreater(result.max, result.min)
                self.assertEqual(result.max - result.min, DISPLAY_INTERVAL_MINUTES)

    def test_format_duration_unit(self):
        self.assertEqual(format_duration_unit(45), "45 min")
        self.assertEqual(format_duration_unit(60), "1 hour")
        self.assertEqual(format_duration_unit(67), "1 hour 7 min")
        self.assertEqual(format_duration_unit(120), "2 hours")
        self.assertEqual(format_duration_unit(125), "2 hours 5 min")
        self.assertEqual(format_duration_unit(0), "0 min")
        self.assertEqual(format_duration_unit(1), "1 min")

    def test_format_duration_range(self):
        # Durations under 60 minutes
        self.assertEqual(format_duration_range(DurationRange(min=50, max=55)), "50–55 min")
        self.assertEqual(format_duration_range(DurationRange(min=35, max=40)), "35–40 min")
        # Crossing hour boundary
        self.assertEqual(format_duration_range(DurationRange(min=55, max=60)), "55 min–1 hour")
        self.assertEqual(format_duration_range(DurationRange(min=60, max=65)), "1 hour–1 hour 5 min")
        self.assertEqual(format_duration_range(DurationRange(min=65, max=70)), "1 hour 5 min–1 hour 10 min")
        self.assertEqual(format_duration_range(DurationRange(min=90, max=95)), "1 hour 30 min–1 hour 35 min")
        self.assertEqual(format_duration_range(DurationRange(min=115, max=120)), "1 hour 55 min–2 hours")
        self.assertEqual(format_duration_range(DurationRange(min=115, max=125)), "1 hour 55 min–2 hours 5 min")
        self.assertEqual(format_duration_range(DurationRange(min=120, max=125)), "2 hours–2 hours 5 min")
        # Short journeys (< 5 min)
        self.assertEqual(format_duration_range(3.2), "3 min")
        self.assertEqual(format_duration_range(2.1), "2 min")
        self.assertEqual(format_duration_range(4.8), "5 min")
        self.assertEqual(format_duration_range(0.0), "0 min")
        # Direct float conversion
        self.assertEqual(format_duration_range(52.4), "50–55 min")
        self.assertEqual(format_duration_range(67.2), "1 hour 5 min–1 hour 10 min")
        self.assertEqual(format_duration_range(121.3), "2 hours–2 hours 5 min")

    def test_invalid_values_raise_error(self):
        invalid_inputs = [None, -1, -0.1, float("nan"), float("inf"), float("-inf")]
        for val in invalid_inputs:
            with self.subTest(val=val):
                with self.assertRaises(ValueError):
                    duration_to_range(val)

    def test_non_number_inputs_raise_error(self):
        invalid_types = ["52.4", True, False, [52.4], {"duration": 52.4}]
        for val in invalid_types:
            with self.subTest(val=val):
                with self.assertRaises(ValueError):
                    duration_to_range(val)


class TestDurationRangeAPIIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_plan_route_returns_duration_range_and_preserves_fields(self):
        underlying_duration = 52.4

        mock_route = Route(
            total_duration_min=underlying_duration,
            distance_m=12400.0,
            legs=[
                RouteLeg(
                    mode="walk",
                    duration_min=7.4,
                    distance_m=500.0,
                    from_location="Origin",
                    to_location="MRT Station",
                ),
                RouteLeg(
                    mode="mrt",
                    duration_min=40.0,
                    distance_m=11000.0,
                    from_location="MRT Station",
                    to_location="Destination Station",
                    line_name="EWL",
                ),
                RouteLeg(
                    mode="walk",
                    duration_min=5.0,
                    distance_m=900.0,
                    from_location="Destination Station",
                    to_location="Destination",
                ),
            ],
        )

        with (
            patch("services.geocoding_service.GeocodingService.resolve_location") as mock_geocode,
            patch("services.routing_service.RoutingService.get_route", new_callable=AsyncMock) as mock_get_route,
            patch("services.exit_routing_service.ExitRoutingService.apply", new_callable=AsyncMock) as mock_exit,
            patch("services.accessibility_service.AccessibilityService.apply", new_callable=AsyncMock) as mock_access,
        ):
            mock_geocode.side_effect = [
                Coordinates(lat=1.300, lon=103.800, label="Origin"),
                Coordinates(lat=1.280, lon=103.850, label="Destination"),
            ]
            mock_get_route.return_value = mock_route
            mock_exit.return_value = mock_route
            mock_access.return_value = (
                AccessibilityResult(
                    step_free=True,
                    accessible=True,
                    verification="verified",
                    stairs_used=False,
                    unknown_segments=0,
                ),
                RouteDecision(reason="optimal", summary="Optimal route selected", details=[]),
            )

            request_payload = {
                "origin": {"address": "Origin"},
                "destination": {"address": "Destination"},
                "preferences": {"stepFree": False},
            }

            response = await self.client.post("/api/v1/routes/plan", json=request_payload)

            # 1. HTTP status remains unchanged (200)
            self.assertEqual(response.status_code, 200)
            data = response.json()

            # 2. Existing route fields remain present
            self.assertIn("request_id", data)
            self.assertIn("origin", data)
            self.assertIn("destination", data)
            self.assertIn("recommended_route", data)
            self.assertIn("accessibility", data)
            self.assertIn("decision", data)

            rec_route = data["recommended_route"]
            self.assertIn("distance_m", rec_route)
            self.assertIn("legs", rec_route)
            self.assertEqual(len(rec_route["legs"]), 3)

            # 3. duration_minutes preserves numerical float
            self.assertIn("duration_minutes", data)
            self.assertEqual(data["duration_minutes"], 52.4)
            self.assertEqual(rec_route["duration_minutes"], 52.4)

            # 4. duration_range provides min and max integers
            self.assertIn("duration_range", data)
            self.assertEqual(data["duration_range"], {"min": 50, "max": 55})
            self.assertEqual(rec_route["duration_range"], {"min": 50, "max": 55})

            # 5. duration_display provides human-readable formatted string
            self.assertIn("duration_display", data)
            self.assertEqual(data["duration_display"], "50–55 min")
            self.assertEqual(rec_route["duration_display"], "50–55 min")


if __name__ == "__main__":
    unittest.main()
