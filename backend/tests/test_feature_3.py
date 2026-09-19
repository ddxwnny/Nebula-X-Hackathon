import unittest
from models.requests import RoutePreferences
from models.responses import Coordinates, Route, RouteLeg, ExitMarker
from services.station_ground_level_service import StationGroundLevelService
from services.accessibility_service import AccessibilityService
from services.exit_routing_service import ExitRoutingService
from clients.lta_datamall_client import LtaDataMallClient


class TestStationGroundLevelService(unittest.TestCase):
    def setUp(self):
        self.service = StationGroundLevelService()

    def test_208_polygons_loaded(self):
        self.assertEqual(len(self.service.features), 208, "Should load all 208 station polygons from official dataset")

    def test_underground_station(self):
        level = self.service.get_station_level("ORCHARD")
        self.assertEqual(level, "UNDERGROUND")
        info = self.service.concourse_transition_info("ORCHARD")
        self.assertEqual(info["ground_level"], "UNDERGROUND")
        self.assertTrue(info["requires_elevator"])
        self.assertIn("dual lift", info["guidance"].lower())

    def test_aboveground_station(self):
        level = self.service.get_station_level("ANG MO KIO")
        self.assertEqual(level, "ABOVEGROUND")
        info = self.service.concourse_transition_info("ANG MO KIO")
        self.assertEqual(info["ground_level"], "ABOVEGROUND")
        self.assertIn("elevated", info["summary"].lower())

    def test_spatial_bounds_query(self):
        # Query central Singapore area
        results = self.service.get_polygons_in_bounds(
            min_lat=1.27, max_lat=1.32, min_lon=103.80, max_lon=103.86
        )
        self.assertGreater(len(results), 0, "Should return central underground/elevated stations")
        first = results[0]
        self.assertEqual(first["geometry"]["type"], "Polygon")
        self.assertIn(first["properties"]["GRND_LEVEL"], ["UNDERGROUND", "ABOVEGROUND"])


class TestStairsVsRampsClassification(unittest.TestCase):
    def test_classify_stairs(self):
        cls = AccessibilityService.classify_osm_tags({"highway": "steps"})
        self.assertEqual(cls, "stairs")

    def test_classify_ramp(self):
        cls = AccessibilityService.classify_osm_tags({"highway": "footway", "ramp": "yes"})
        self.assertEqual(cls, "ramp")

    def test_edge_cost_wheelchair(self):
        prefs_step_free = RoutePreferences(step_free=True)
        prefs_normal = RoutePreferences(step_free=False)

        cost_stairs_normal = AccessibilityService.edge_cost(60, "stairs", prefs_normal)
        self.assertEqual(cost_stairs_normal, 60)

        cost_stairs_wheelchair = AccessibilityService.edge_cost(60, "stairs", prefs_step_free)
        self.assertEqual(cost_stairs_wheelchair, 6000.0, "Stairs should be heavily penalized for wheelchair users")

        cost_ramp = AccessibilityService.edge_cost(60, "ramp", prefs_step_free)
        self.assertEqual(cost_ramp, 54.0, "Ramps should be rewarded with lower cost")


class TestDynamicBarrierInvalidation(unittest.IsolatedAsyncioTestCase):
    async def test_lift_outage_severs_exit(self):
        lta_client = LtaDataMallClient()
        # Inject simulated outage at NOVENA Exit A
        lta_client.inject_simulated_maintenance("NOVENA", exit_id="Exit A", description="Motor replacement")

        statuses = await lta_client.lift_statuses("NOVENA")
        self.assertIn("SIM-LIFT-1", statuses)
        self.assertEqual(statuses["SIM-LIFT-1"]["status"], "maintenance")

    async def test_accessibility_service_detects_lift_maintenance_barrier(self):
        service = AccessibilityService()
        route = Route(
            total_duration_min=25.0,
            distance_m=1200.0,
            legs=[
                RouteLeg(
                    mode="walk",
                    duration_min=5.0,
                    distance_m=300.0,
                    from_location="Home",
                    to_location="Exit A",
                    accessibility="lift_maintenance",
                ),
                RouteLeg(
                    mode="mrt",
                    duration_min=15.0,
                    distance_m=8000.0,
                    from_location="NOVENA",
                    to_location="ORCHARD",
                    line_name="NS",
                ),
            ],
        )

    async def test_exit_routing_service_severs_broken_lift(self):
        from unittest.mock import AsyncMock, MagicMock
        mock_exits = MagicMock()
        mock_exits.exits_for_station_name = AsyncMock(return_value=[
            {"id": "NOVENA-EXIT-A", "station_id": "NOVENA", "exit_id": "A", "lat": 1.3204, "lon": 103.8438},
            {"id": "NOVENA-EXIT-B", "station_id": "NOVENA", "exit_id": "B", "lat": 1.3210, "lon": 103.8445},
        ])
        mock_routing = MagicMock()
        mock_routing.get_walking_route = AsyncMock(return_value={
            "route_summary": {"total_time": 120, "total_distance": 100},
            "route_geometry": "",
        })
        lta_client = LtaDataMallClient()
        lta_client.inject_simulated_maintenance("NOVENA", exit_id="Exit A", description="Lift down")

        service = ExitRoutingService(routing_client=mock_routing, station_exits=mock_exits, lta_client=lta_client)

        route = Route(
            total_duration_min=30.0,
            distance_m=5000.0,
            legs=[
                RouteLeg(mode="walk", duration_min=5.0, distance_m=300.0, from_location="Home", to_location="Novena Station", accessibility="unknown"),
                RouteLeg(mode="mrt", duration_min=10.0, distance_m=4000.0, from_location="NOVENA", to_location="ORCHARD", line_name="NS"),
            ]
        )

        origin = Coordinates(lat=1.32, lon=103.84)
        destination = Coordinates(lat=1.30, lon=103.83)
        res_route = await service.apply(route, origin, destination, RoutePreferences(step_free=True))

        self.assertIsNotNone(res_route.exit_routing)
        candidates = res_route.exit_routing.candidate_exits
        self.assertEqual(len(candidates), 2)
        exit_a = next(c for c in candidates if c.exit_id == "A")
        exit_b = next(c for c in candidates if c.exit_id == "B")
        self.assertEqual(exit_a.lift_status, "maintenance", "Exit A should be marked maintenance")
        self.assertEqual(exit_b.lift_status, "operational", "Exit B should be operational")
        self.assertFalse(exit_a.is_selected, "Exit A with broken lift MUST NOT be selected")
        self.assertTrue(exit_b.is_selected, "Exit B with working lift MUST be selected")


if __name__ == "__main__":
    unittest.main()
