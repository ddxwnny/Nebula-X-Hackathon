import unittest
from models.disruptions import TrainDisruption
from models.journeys import CreateJourneyRequest, DisruptionInfo, JourneyLegInput
from models.requests import Location, RoutePreferences, RouteRequest
from models.responses import Coordinates, LocationSuggestion, RouteLeg, StationAccess


class TestModelFieldAliases(unittest.TestCase):
    def test_location_and_coordinates_label_address_interchange(self):
        # Location initialized with label
        loc1 = Location.model_validate({"label": "123 Orchard Road", "lat": 1.30, "lon": 103.83})
        self.assertEqual(loc1.address, "123 Orchard Road")
        self.assertEqual(loc1.label, "123 Orchard Road")

        # Location initialized with address
        loc2 = Location.model_validate({"address": "123 Orchard Road", "lat": 1.30, "lon": 103.83})
        self.assertEqual(loc2.address, "123 Orchard Road")
        self.assertEqual(loc2.label, "123 Orchard Road")

        # Coordinates initialized with address
        coord1 = Coordinates.model_validate({"lat": 1.30, "lon": 103.83, "address": "123 Orchard Road"})
        self.assertEqual(coord1.label, "123 Orchard Road")

        # LocationSuggestion handles both address and label
        sug = LocationSuggestion.model_validate({"lat": 1.30, "lon": 103.83, "address": "123 Orchard Road"})
        self.assertEqual(sug.address, "123 Orchard Road")
        self.assertEqual(sug.label, "123 Orchard Road")

    def test_route_leg_and_journey_leg_cross_compatibility(self):
        # RouteLeg initialized with from/to and line
        rleg1 = RouteLeg.model_validate({
            "mode": "mrt",
            "duration_min": 12.5,
            "from": "Tanah Merah",
            "to": "Paya Lebar",
            "line": "EWL",
        })
        self.assertEqual(rleg1.from_location, "Tanah Merah")
        self.assertEqual(rleg1.to_location, "Paya Lebar")
        self.assertEqual(rleg1.line_name, "EWL")
        self.assertEqual(rleg1.line, "EWL")

        # RouteLeg serialization uses from and to
        dumped = rleg1.model_dump(by_alias=True)
        self.assertEqual(dumped["from"], "Tanah Merah")
        self.assertEqual(dumped["to"], "Paya Lebar")

        # JourneyLegInput created from RouteLeg dump (both standard and by_alias)
        jleg1 = JourneyLegInput.model_validate(dumped)
        self.assertEqual(jleg1.from_location, "Tanah Merah")
        self.assertEqual(jleg1.to_location, "Paya Lebar")
        self.assertEqual(jleg1.line, "EWL")
        self.assertEqual(jleg1.line_name, "EWL")

        jleg2 = JourneyLegInput.model_validate(rleg1.model_dump())
        self.assertEqual(jleg2.from_location, "Tanah Merah")
        self.assertEqual(jleg2.to_location, "Paya Lebar")
        self.assertEqual(jleg2.line, "EWL")

    def test_station_access_aliases(self):
        sa = StationAccess.model_validate({
            "stationCode": "EW4",
            "stationName": "Tanah Merah MRT Station",
            "exitId": "B",
            "exitName": "Exit B",
            "lat": 1.327,
            "lon": 103.946,
        })
        self.assertEqual(sa.station_id, "EW4")
        self.assertEqual(sa.station_code, "EW4")
        self.assertEqual(sa.station_name, "Tanah Merah MRT Station")
        self.assertEqual(sa.exit_id, "B")
        self.assertEqual(sa.exit_name, "Exit B")

    def test_disruption_info_and_train_disruption_station_aliases(self):
        # DisruptionInfo initialized with stations
        dinfo = DisruptionInfo.model_validate({
            "line": "CCL",
            "stations": ["CC10", "CC9", "CC8"],
        })
        self.assertEqual(dinfo.affected_stations, ["CC10", "CC9", "CC8"])
        self.assertEqual(dinfo.stations, ["CC10", "CC9", "CC8"])

        # TrainDisruption initialized with affected_stations
        td = TrainDisruption.model_validate({
            "line": "CCL",
            "affected_stations": ["CC10", "CC9", "CC8"],
        })
        self.assertEqual(td.stations, ["CC10", "CC9", "CC8"])
        self.assertEqual(td.affected_stations, ["CC10", "CC9", "CC8"])

    def test_camel_case_request_options(self):
        req = RouteRequest.model_validate({
            "origin": {"address": "City Hall"},
            "destination": {"address": "Bugis"},
            "departureDate": "2026-09-19",
            "departureTime": "14:00:00",
            "preferences": {"stepFree": True},
        })
        self.assertTrue(req.preferences.step_free)
        self.assertEqual(str(req.departure_date), "2026-09-19")
        self.assertEqual(str(req.departure_time), "14:00:00")

    def test_route_duration_range_aliases(self):
        from models.responses import Route

        # Validate with total_duration_min float
        r1 = Route.model_validate({
            "total_duration_min": 52.4,
            "distance_m": 5000.0,
            "legs": [],
        })
        self.assertEqual(r1.duration_minutes.min, 50)
        self.assertEqual(r1.duration_minutes.max, 55)
        self.assertEqual(r1.total_duration_min, 52.4)

        # Validate with camelCase totalDurationMin
        r2 = Route.model_validate({
            "totalDurationMin": 30.0,
            "distance_m": 5000.0,
            "legs": [],
        })
        self.assertEqual(r2.duration_minutes.min, 30)
        self.assertEqual(r2.duration_minutes.max, 35)

        # Validate with duration_minutes object
        r3 = Route.model_validate({
            "duration_minutes": {"min": 50, "max": 55},
            "distance_m": 5000.0,
            "legs": [],
        })
        self.assertEqual(r3.duration_minutes.min, 50)
        self.assertEqual(r3.duration_minutes.max, 55)

        # Validate with camelCase durationMinutes object
        r4 = Route.model_validate({
            "durationMinutes": {"min": 50, "max": 55},
            "distance_m": 5000.0,
            "legs": [],
        })
        self.assertEqual(r4.duration_minutes.min, 50)
        self.assertEqual(r4.duration_minutes.max, 55)



if __name__ == "__main__":
    unittest.main()

