import unittest
from services.weather_service import WeatherService
from models.requests import RoutePreferences


class TestWeatherServiceNowcastAndRainfall(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = WeatherService()

    def test_map_rain_severity_codes(self):
        # Direct lookup tests
        self.assertEqual(self.service._map_rain_severity("Showers"), (True, "rain"))
        self.assertEqual(self.service._map_rain_severity("Thundery Showers"), (True, "thunderstorm"))
        self.assertEqual(self.service._map_rain_severity("Heavy Rain"), (True, "heavy_rain"))
        self.assertEqual(self.service._map_rain_severity("Light Rain"), (True, "light_rain"))
        self.assertEqual(self.service._map_rain_severity("Fair (Day)"), (False, "none"))
        self.assertEqual(self.service._map_rain_severity("Cloudy"), (False, "none"))
        
        # Substring / dynamic fallback tests
        self.assertEqual(self.service._map_rain_severity("Passing Showers"), (True, "light_rain"))
        self.assertEqual(self.service._map_rain_severity("Scattered Thundery Showers"), (True, "thunderstorm"))

    def test_parse_nowcast_v2_with_area_metadata(self):
        # Realistic data.gov.sg v2 payload sample
        mock_nowcast = {
            "code": 0,
            "data": {
                "area_metadata": [
                    {"name": "Bukit Batok", "label_location": {"latitude": 1.353, "longitude": 103.754}},
                    {"name": "Bedok", "label_location": {"latitude": 1.321, "longitude": 103.924}},
                ],
                "items": [
                    {
                        "update_timestamp": "2026-09-19T14:30:00+08:00",
                        "timestamp": "2026-09-19T14:30:00+08:00",
                        "valid_period": {"text": "2.30 pm to 4.30 pm"},
                        "forecasts": [
                            {"area": "Bukit Batok", "forecast": "Showers"},
                            {"area": "Bedok", "forecast": "Fair (Day)"},
                        ],
                    }
                ],
            },
        }

        # Point near Bukit Batok MRT (lat 1.3490, lon 103.7496)
        parsed_bb = self.service._parse_nowcast_for_point(mock_nowcast, 1.3490, 103.7496)
        self.assertTrue(parsed_bb["rain_expected"])
        self.assertEqual(parsed_bb["rain_severity"], "rain")
        self.assertEqual(parsed_bb["forecast_area"], "Bukit Batok")
        self.assertEqual(parsed_bb["forecast_text"], "Showers")
        self.assertEqual(parsed_bb["valid_period"], "2.30 pm to 4.30 pm")

        # Point near Bedok MRT (lat 1.3240, lon 103.9300)
        parsed_bedok = self.service._parse_nowcast_for_point(mock_nowcast, 1.3240, 103.9300)
        self.assertFalse(parsed_bedok["rain_expected"])
        self.assertEqual(parsed_bedok["rain_severity"], "none")
        self.assertEqual(parsed_bedok["forecast_area"], "Bedok")

    def test_parse_rainfall_v2(self):
        # Realistic data.gov.sg v2 rainfall payload sample
        mock_rainfall = {
            "code": 0,
            "data": {
                "readingType": "rainfall",
                "readingUnit": "mm",
                "stations": [
                    {
                        "id": "S218",
                        "deviceId": "S218",
                        "name": "Bukit Batok Street 34",
                        "location": {"latitude": 1.36491, "longitude": 103.75065},
                    },
                    {
                        "id": "S64",
                        "deviceId": "S64",
                        "name": "Bukit Panjang Road",
                        "location": {"latitude": 1.3823, "longitude": 103.7607},
                    },
                ],
                "readings": [
                    {
                        "timestamp": "2026-09-19T14:35:00+08:00",
                        "data": [
                            {"stationId": "S218", "value": 0.0},
                            {"stationId": "S64", "value": 4.2},
                        ],
                    }
                ],
            },
        }

        # Point close to station S64 (Bukit Panjang)
        parsed_bp = self.service._parse_rainfall_for_point(mock_rainfall, 1.3820, 103.7600)
        self.assertTrue(parsed_bp["currently_raining"])
        self.assertEqual(parsed_bp["rainfall_mm"], 4.2)
        self.assertEqual(parsed_bp["nearest_station"], "Bukit Panjang Road")

    async def test_assess_route_rain_risk_simulated(self):
        result = await self.service.assess_route_rain_risk(
            [(1.35, 103.82)],
            simulate_rain=True,
            dry_route=True,
        )
        self.assertTrue(result["rain_along_route"])
        self.assertEqual(result["rain_severity"], "thunderstorm")
        self.assertTrue(result["current_rain"]["currently_raining"])
        self.assertIn("100% Dry Route Activated", result["recommendation"])

    def test_preferences_dry_route_and_simulate_rain(self):
        prefs = RoutePreferences(dryRoute=True, simulateRain=True)
        self.assertTrue(prefs.dry_route)
        self.assertTrue(prefs.simulate_rain)


if __name__ == "__main__":
    unittest.main()
