import unittest
from unittest.mock import AsyncMock
from models.requests import RoutePreferences
from models.responses import Coordinates, Route, RouteLeg
from services.exit_routing_service import ExitRoutingService


class TestExitRoutingService(unittest.IsolatedAsyncioTestCase):
    async def test_origin_and_destination_exits_selected(self):
        mock_routing_client = AsyncMock()
        mock_routing_client.get_walking_route.return_value = {
            "route_summary": {"total_time": 240, "total_distance": 300},
            "route_geometry": "",
        }
        mock_station_exits = AsyncMock()
        mock_station_exits.exits_for_station_name.side_effect = lambda name: [
            {"id": "E1", "station_id": name, "exit_id": "A", "lat": 1.3, "lon": 103.8}
        ]

        service = ExitRoutingService(
            routing_client=mock_routing_client,
            station_exits=mock_station_exits,
        )

        origin = Coordinates(lat=1.29, lon=103.77)
        destination = Coordinates(lat=1.31, lon=103.85)
        route = Route(
            total_duration_min=30.0,
            distance_m=10000.0,
            legs=[
                RouteLeg(mode="walk", duration_min=5.0, distance_m=350.0, from_location="Origin", to_location="Tanah Merah MRT Station", geometry=[origin, Coordinates(lat=1.3, lon=103.8)]),
                RouteLeg(mode="mrt", duration_min=20.0, distance_m=9000.0, from_location="Tanah Merah MRT Station", to_location="Farrer Park MRT Station", line_name="EWL"),
                RouteLeg(mode="walk", duration_min=5.0, distance_m=350.0, from_location="Farrer Park MRT Station", to_location="Destination", geometry=[Coordinates(lat=1.31, lon=103.85), destination]),
            ],
        )

        result = await service.apply(route, origin, destination, RoutePreferences())

        self.assertTrue(result.exit_routing.enabled)
        self.assertFalse(result.exit_routing.fallback_to_station_centroid)
        self.assertIsNotNone(result.exit_routing.origin)
        self.assertIsNotNone(result.exit_routing.destination)
        self.assertEqual(result.exit_routing.origin.station_name, "Tanah Merah MRT Station")
        self.assertEqual(result.exit_routing.origin.exit_name, "Exit A")
        self.assertEqual(result.exit_routing.destination.station_name, "Farrer Park MRT Station")
        self.assertEqual(result.exit_routing.destination.exit_name, "Exit A")
        self.assertIsNone(result.exit_routing.fallback_reason)

    async def test_origin_only_exit_fallback(self):
        mock_routing_client = AsyncMock()
        mock_routing_client.get_walking_route.return_value = {
            "route_summary": {"total_time": 240, "total_distance": 300},
            "route_geometry": "",
        }
        mock_station_exits = AsyncMock()
        # Only origin station has exits; destination station (Prince Edward Road) returns []
        mock_station_exits.exits_for_station_name.side_effect = lambda name: (
            [{"id": "E1", "station_id": name, "exit_id": "B", "lat": 1.32, "lon": 103.93}]
            if "Tanah Merah" in name
            else []
        )

        service = ExitRoutingService(
            routing_client=mock_routing_client,
            station_exits=mock_station_exits,
        )

        origin = Coordinates(lat=1.32, lon=103.93)
        destination = Coordinates(lat=1.27, lon=103.84)
        route = Route(
            total_duration_min=35.0,
            distance_m=12000.0,
            legs=[
                RouteLeg(mode="walk", duration_min=5.0, distance_m=350.0, from_location="Origin", to_location="Tanah Merah MRT Station", geometry=[origin, Coordinates(lat=1.32, lon=103.93)]),
                RouteLeg(mode="mrt", duration_min=25.0, distance_m=11000.0, from_location="Tanah Merah MRT Station", to_location="Prince Edward Road MRT Station", line_name="EWL"),
                RouteLeg(mode="walk", duration_min=5.0, distance_m=400.0, from_location="Prince Edward Road MRT Station", to_location="Destination", geometry=[Coordinates(lat=1.27, lon=103.84), destination]),
            ],
        )

        result = await service.apply(route, origin, destination, RoutePreferences())

        self.assertTrue(result.exit_routing.enabled)
        self.assertTrue(result.exit_routing.fallback_to_station_centroid)
        self.assertIsNotNone(result.exit_routing.origin)
        self.assertIsNone(result.exit_routing.destination)
        self.assertEqual(result.exit_routing.fallback_reason, "destination_exit_data_unavailable")
        self.assertIn("origin station", result.exit_routing.explanation)


if __name__ == "__main__":
    unittest.main()

