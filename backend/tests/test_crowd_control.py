import unittest

from models.requests import RoutePreferences
from models.responses import Route, RouteLeg
from services.crowd_service import CrowdService, normalise_level, normalise_line


class FakeCrowdClient:
    async def train_crowd(self, line: str, *, forecast: bool = False):
        if forecast:
            return [{"Station": "NS16", "CrowdLevel": "h"}]
        return [{"Station": "NS16", "CrowdLevel": "m"}]


class TestCrowdControl(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.route = Route(
            total_duration_min=30,
            distance_m=5000,
            legs=[RouteLeg(mode="mrt", duration_min=20, distance_m=4000, from_location="Ang Mo Kio", to_location="Orchard", line_name="North South Line")],
        )

    def test_normalises_lta_levels_and_line_names(self):
        self.assertEqual(normalise_level("l"), "low")
        self.assertEqual(normalise_level("M"), "medium")
        self.assertEqual(normalise_level("heavy"), "high")
        self.assertEqual(normalise_line("North South Line"), "NSL")

    async def test_combines_live_and_forecast_and_explains_tradeoff(self):
        assessment = await CrowdService(FakeCrowdClient()).assess(self.route)
        self.assertEqual(assessment.status, "live")
        self.assertEqual(assessment.overall_level, "high")
        self.assertEqual(assessment.stations[0].live_level, "medium")
        self.assertEqual(assessment.stations[0].forecast_level, "high")
        self.assertIn("calmer boarding window", assessment.tradeoff)

    async def test_disabled_control_does_not_fetch_or_change_route(self):
        assessment = await CrowdService(FakeCrowdClient()).assess(self.route, enabled=False)
        self.assertEqual(assessment.status, "unavailable")
        self.assertEqual(assessment.overall_level, "unknown")

    def test_camel_case_preference(self):
        self.assertFalse(RoutePreferences(crowdControl=False).crowd_control)


if __name__ == "__main__":
    unittest.main()
