import unittest
from unittest.mock import AsyncMock
from clients.lta_client import LTAClient
from models.disruptions import TrainDisruption, TrainServiceStatus
from models.journeys import CreateJourneyRequest, JourneyLegInput
from models.responses import Coordinates
from services.disruption_monitor import DisruptionMonitor
from services.journey_service import JourneyService


class TestDisruptionMonitor(unittest.IsolatedAsyncioTestCase):
    def test_meaningful_change_detection(self):
        # 1. Initially None -> any status is meaningful
        normal = TrainServiceStatus(status=1, affected_segments=[])
        self.assertTrue(DisruptionMonitor.is_meaningful_change(None, normal))

        # 2. Normal -> Disrupted
        disrupted = TrainServiceStatus(
            status=2,
            affected_segments=[
                TrainDisruption(line="CCL", stations=["CC10", "CC9", "CC8"])
            ],
        )
        self.assertTrue(DisruptionMonitor.is_meaningful_change(normal, disrupted))

        # 3. Disrupted -> Same disruption (order or spacing shouldn't matter)
        same_disrupted = TrainServiceStatus(
            status=2,
            affected_segments=[
                TrainDisruption(line="CCL", stations=["CC8", "CC9", "CC10"])
            ],
        )
        self.assertFalse(DisruptionMonitor.is_meaningful_change(disrupted, same_disrupted))

        # 4. Disruption expands (CC10, CC9, CC8 -> CC10, CC9, CC8, CC7)
        expanded = TrainServiceStatus(
            status=2,
            affected_segments=[
                TrainDisruption(line="CCL", stations=["CC10", "CC9", "CC8", "CC7"])
            ],
        )
        self.assertTrue(DisruptionMonitor.is_meaningful_change(disrupted, expanded))

        # 5. Disruption clears (Status 2 -> Status 1)
        self.assertTrue(DisruptionMonitor.is_meaningful_change(expanded, normal))

    async def test_monitor_updates_active_journeys(self):
        journey_service = JourneyService()
        journey = journey_service.create_journey(
            CreateJourneyRequest(
                route_id="r1",
                origin=Coordinates(lat=1.2966, lon=103.7764),
                destination=Coordinates(lat=1.2847, lon=103.8511),
                legs=[
                    JourneyLegInput(
                        mode="mrt",
                        line="CCL",
                        from_location="Kent Ridge",
                        to_location="Dhoby Ghaut",
                        stations=["CC24", "CC10", "CC9", "CC8", "CC1"],
                    )
                ],
            )
        )
        self.assertEqual(journey.status, "active")

        # Mock LTAClient
        mock_lta = AsyncMock(spec=LTAClient)
        mock_lta.get_train_service_alerts.return_value = TrainServiceStatus(
            status=2,
            affected_segments=[
                TrainDisruption(line="CCL", stations=["CC10", "CC9", "CC8"])
            ],
        )

        monitor = DisruptionMonitor(lta_client=mock_lta, journey_service=journey_service)
        status = await monitor.check_for_updates()

        self.assertEqual(status.status, 2)
        self.assertEqual(journey.status, "reroute_required")
        self.assertIsNotNone(journey.active_disruption)
        self.assertEqual(journey.disruption_stations_affected, ["CC10", "CC8", "CC9"])

        # Second poll with same disruption should not change or duplicate
        await monitor.check_for_updates()
        self.assertEqual(journey.status, "reroute_required")

        # Third poll with cleared disruption
        mock_lta.get_train_service_alerts.return_value = TrainServiceStatus(
            status=1,
            affected_segments=[],
        )
        await monitor.check_for_updates()
        self.assertEqual(journey.status, "active")
        self.assertIsNone(journey.active_disruption)


if __name__ == "__main__":
    unittest.main()

