import unittest
from unittest.mock import AsyncMock
from models.requests import RoutePreferences
from models.responses import Coordinates, ExitRoutingMetadata, Route, RouteLeg, StationAccess
from services.accessibility_service import AccessibilityService


class TestAccessibilityService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_exits_service = AsyncMock()
        self.mock_lta_client = AsyncMock()
        self.mock_lta_client.lift_statuses.return_value = {}
        self.service = AccessibilityService(
            station_exits=self.mock_exits_service,
            lta_client=self.mock_lta_client,
        )

    async def test_step_free_not_requested(self):
        route = Route(
            total_duration_min=20.0,
            distance_m=5000.0,
            legs=[RouteLeg(mode="walk", duration_min=5.0, from_location="A", to_location="B")],
        )
        res, dec = await self.service.apply(route, RoutePreferences(step_free=False))
        self.assertFalse(res.step_free)
        self.assertTrue(res.accessible)
        self.assertEqual(res.verification, "not_requested")
        self.assertEqual(dec.reason, "normal")

    async def test_step_free_verified_with_exit_routing(self):
        # A route where exit routing successfully resolved origin and destination exits
        route = Route(
            total_duration_min=25.0,
            distance_m=8000.0,
            legs=[
                RouteLeg(mode="walk", duration_min=4.0, from_location="Origin", to_location="Exit B", accessibility="step_free"),
                RouteLeg(mode="mrt", duration_min=15.0, from_location="Tanah Merah", to_location="Paya Lebar", line_name="EWL", accessibility="step_free"),
                RouteLeg(mode="walk", duration_min=6.0, from_location="Exit A", to_location="Destination", accessibility="step_free"),
            ],
            exit_routing=ExitRoutingMetadata(
                enabled=True,
                fallback_to_station_centroid=False,
                origin=StationAccess(station_id="EW4", station_name="Tanah Merah", exit_id="B", exit_name="Exit B", lat=1.32, lon=103.94),
                destination=StationAccess(station_id="EW8", station_name="Paya Lebar", exit_id="A", exit_name="Exit A", lat=1.31, lon=103.89),
            ),
        )
        # Mock operational lifts at EW4 and EW8
        self.mock_lta_client.lift_statuses.side_effect = lambda stn: {
            "L1": {"status": "available", "exit_id": "B"} if stn == "EW4" else {"status": "available", "exit_id": "A"}
        }

        res, dec = await self.service.apply(route, RoutePreferences(step_free=True))
        self.assertTrue(res.step_free)
        self.assertTrue(res.accessible)
        self.assertEqual(res.verification, "verified")
        self.assertFalse(res.stairs_used)
        self.assertEqual(res.unavailable_facilities, 0)
        self.assertIn("verified step-free", dec.summary)

    async def test_step_free_unverified_when_centroid_fallback(self):
        # Destination exit data unavailable -> fallback_to_station_centroid is True
        route = Route(
            total_duration_min=25.0,
            distance_m=8000.0,
            legs=[
                RouteLeg(mode="walk", duration_min=4.0, from_location="Origin", to_location="Exit B", accessibility="step_free"),
                RouteLeg(mode="mrt", duration_min=15.0, from_location="Tanah Merah", to_location="Prince Edward Road", line_name="CCL", accessibility="step_free"),
                RouteLeg(mode="walk", duration_min=6.0, from_location="Prince Edward Road", to_location="Destination", accessibility="unknown"),
            ],
            exit_routing=ExitRoutingMetadata(
                enabled=True,
                fallback_to_station_centroid=True,
                fallback_reason="destination_exit_data_unavailable",
                origin=StationAccess(station_id="EW4", station_name="Tanah Merah", exit_id="B", exit_name="Exit B", lat=1.32, lon=103.94),
            ),
        )
        res, dec = await self.service.apply(route, RoutePreferences(step_free=True))
        self.assertTrue(res.step_free)
        self.assertFalse(res.accessible)
        self.assertEqual(res.verification, "unverified")
        self.assertIn("No fully verified step-free route", dec.summary)

    async def test_step_free_blocked_by_stairs(self):
        route = Route(
            total_duration_min=20.0,
            distance_m=5000.0,
            legs=[
                RouteLeg(mode="walk", duration_min=5.0, from_location="A", to_location="B", accessibility="stairs"),
            ],
            exit_routing=ExitRoutingMetadata(enabled=False, fallback_to_station_centroid=False),
        )
        res, dec = await self.service.apply(route, RoutePreferences(step_free=True))
        self.assertTrue(res.step_free)
        self.assertFalse(res.accessible)
        self.assertEqual(res.verification, "stairs_detected")
        self.assertTrue(res.stairs_used)
        self.assertEqual(dec.reason, "stairs_detected")

    async def test_step_free_blocked_by_lift_maintenance(self):
        route = Route(
            total_duration_min=25.0,
            distance_m=8000.0,
            legs=[
                RouteLeg(mode="walk", duration_min=4.0, from_location="Origin", to_location="Exit B", accessibility="step_free"),
                RouteLeg(mode="mrt", duration_min=15.0, from_location="Tanah Merah", to_location="Paya Lebar", line_name="EWL", accessibility="step_free"),
                RouteLeg(mode="walk", duration_min=6.0, from_location="Exit A", to_location="Destination", accessibility="step_free"),
            ],
            exit_routing=ExitRoutingMetadata(
                enabled=True,
                fallback_to_station_centroid=False,
                origin=StationAccess(station_id="EW4", station_name="Tanah Merah", exit_id="B", exit_name="Exit B", lat=1.32, lon=103.94),
                destination=StationAccess(station_id="EW8", station_name="Paya Lebar", exit_id="A", exit_name="Exit A", lat=1.31, lon=103.89),
            ),
        )
        # Mock lift maintenance at EW4 Exit B
        self.mock_lta_client.lift_statuses.side_effect = lambda stn: {
            "L1": {"status": "maintenance", "exit_id": "B"} if stn == "EW4" else {"status": "available", "exit_id": "A"}
        }

        res, dec = await self.service.apply(route, RoutePreferences(step_free=True))
        self.assertTrue(res.step_free)
        self.assertFalse(res.accessible)
        self.assertEqual(res.verification, "lift_maintenance")
        self.assertEqual(res.unavailable_facilities, 1)
        self.assertEqual(dec.reason, "lift_maintenance")


if __name__ == "__main__":
    unittest.main()

