import unittest
from models.disruptions import TrainDisruption, TrainServiceStatus
from models.journeys import CreateJourneyRequest, JourneyLegInput
from models.responses import Coordinates
from services.journey_service import JourneyService
from services.mrt_network import get_stations_traversed


class TestJourneyMatching(unittest.TestCase):
    def setUp(self):
        self.journey_service = JourneyService()
        self.origin = Coordinates(lat=1.2966, lon=103.7764)
        self.destination = Coordinates(lat=1.2847, lon=103.8511)

    def test_stations_traversed_expansion(self):
        stations = get_stations_traversed("CCL", "Kent Ridge", "Dhoby Ghaut")
        self.assertIn("CC24", stations)
        self.assertIn("CC10", stations)
        self.assertIn("CC9", stations)
        self.assertIn("CC8", stations)
        self.assertIn("CC1", stations)

    def test_affected_line_and_station_triggers_reroute(self):
        journey = self.journey_service.create_journey(
            CreateJourneyRequest(
                route_id="r1",
                origin=self.origin,
                destination=self.destination,
                legs=[
                    JourneyLegInput(mode="walk", from_location="Origin", to_location="Kent Ridge"),
                    JourneyLegInput(mode="mrt", line="CCL", from_location="Kent Ridge", to_location="Dhoby Ghaut"),
                ],
            )
        )
        alert = TrainServiceStatus(
            status=2,
            affected_segments=[
                TrainDisruption(line="CCL", stations=["CC10", "CC9", "CC8"])
            ],
        )
        status, disruption = self.journey_service.evaluate_journey_disruption(journey, alert)
        self.assertEqual(status, "reroute_required")
        self.assertIsNotNone(disruption)
        self.assertEqual(journey.status, "reroute_required")
        self.assertEqual(set(journey.disruption_stations_affected), {"CC10", "CC9", "CC8"})

    def test_affected_line_different_station_is_unaffected(self):
        # Journey only between CC24 (Kent Ridge) and CC22 (Buona Vista)
        journey = self.journey_service.create_journey(
            CreateJourneyRequest(
                route_id="r2",
                origin=self.origin,
                destination=self.destination,
                legs=[
                    JourneyLegInput(mode="mrt", line="CCL", from_location="Kent Ridge", to_location="Buona Vista"),
                ],
            )
        )
        alert = TrainServiceStatus(
            status=2,
            affected_segments=[
                TrainDisruption(line="CCL", stations=["CC10", "CC9", "CC8"])
            ],
        )
        status, disruption = self.journey_service.evaluate_journey_disruption(journey, alert)
        self.assertEqual(status, "unaffected")
        self.assertIsNone(disruption)
        self.assertEqual(journey.status, "unaffected")

    def test_different_line_is_unaffected(self):
        # Journey on DTL
        journey = self.journey_service.create_journey(
            CreateJourneyRequest(
                route_id="r3",
                origin=self.origin,
                destination=self.destination,
                legs=[
                    JourneyLegInput(mode="mrt", line="DTL", from_location="Botanic Gardens", to_location="Bugis"),
                ],
            )
        )
        alert = TrainServiceStatus(
            status=2,
            affected_segments=[
                TrainDisruption(line="CCL", stations=["CC10", "CC9", "CC8"])
            ],
        )
        status, disruption = self.journey_service.evaluate_journey_disruption(journey, alert)
        self.assertEqual(status, "unaffected")
        self.assertIsNone(disruption)
        self.assertEqual(journey.status, "unaffected")

    def test_bus_only_journey_is_unaffected(self):
        # Journey with only walking and buses
        journey = self.journey_service.create_journey(
            CreateJourneyRequest(
                route_id="r4",
                origin=self.origin,
                destination=self.destination,
                legs=[
                    JourneyLegInput(mode="walk", from_location="Origin", to_location="Bus Stop A"),
                    JourneyLegInput(mode="bus", line="133", from_location="Bus Stop A", to_location="Bus Stop B"),
                ],
            )
        )
        alert = TrainServiceStatus(
            status=2,
            affected_segments=[
                TrainDisruption(line="CCL", stations=["CC10", "CC9", "CC8"])
            ],
        )
        status, disruption = self.journey_service.evaluate_journey_disruption(journey, alert)
        self.assertEqual(status, "active")
        self.assertIsNone(disruption)


if __name__ == "__main__":
    unittest.main()

