import unittest
from services.covered_linkway_service import CoveredLinkwayService


class TestCoveredLinkwayService(unittest.TestCase):
    def setUp(self):
        self.service = CoveredLinkwayService()

    def test_data_loaded(self):
        features = self.service._data
        self.assertGreater(len(features), 5000, "Should load over 5000 covered linkways")

    def test_find_linkways_near_ang_mo_kio(self):
        # Ang Mo Kio coordinates
        results = self.service.find_linkways_near_route(
            min_lat=1.365,
            max_lat=1.375,
            min_lon=103.845,
            max_lon=103.855,
            buffer=0.005,
        )
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0, "Should find linkways around Ang Mo Kio")
        first = results[0]
        self.assertEqual(first.get("type"), "Feature")
        self.assertIn(first.get("geometry", {}).get("type"), ["LineString", "MultiLineString"])

    def test_find_linkways_outside_singapore(self):
        # Coordinates in the ocean / far outside SG
        results = self.service.find_linkways_near_route(
            min_lat=0.0,
            max_lat=0.1,
            min_lon=0.0,
            max_lon=0.1,
        )
        self.assertEqual(len(results), 0, "Should return empty list for coordinates outside Singapore")


if __name__ == "__main__":
    unittest.main()
