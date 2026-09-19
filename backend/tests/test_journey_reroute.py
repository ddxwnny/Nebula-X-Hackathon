import unittest
from unittest.mock import AsyncMock
from fastapi import HTTPException
from models.disruptions import TrainDisruption
from models.journeys import CreateJourneyRequest, JourneyLegInput
from models.responses import Coordinates, Route, RouteLeg
from services.journey_service import JourneyService
from services.routing_service import RoutingService


class TestJourneyReroute(unittest.IsolatedAsyncioTestCase):
    async def test_reroute_from_current_position(self):
        journey_service = JourneyService()
        origin = Coordinates(lat=1.2966, lon=103.7764, label="NUS")
        destination = Coordinates(lat=1.2847, lon=103.8511, label="Raffles Place")
        current_pos = Coordinates(lat=1.2980, lon=103.7870, label="Approaching Dhoby Ghaut")

        journey = journey_service.create_journey(
            CreateJourneyRequest(
                route_id="r100",
                origin=origin,
                destination=destination,
                current_position=current_pos,
                legs=[
                    JourneyLegInput(mode="mrt", line="CCL", from_location="Kent Ridge", to_location="Dhoby Ghaut", duration_min=25.0),
                    JourneyLegInput(mode="walk", from_location="Dhoby Ghaut", to_location="Destination", duration_min=7.0),
                ],
            )
        )
        journey.active_disruption = TrainDisruption(
            line="CCL",
            stations=["CC10", "CC9", "CC8"],
            free_mrt_shuttle=["Between CC10 and CC8"],
        )
        journey.status = "reroute_required"

        mock_router = AsyncMock(spec=RoutingService)
        # The new route returned from current_position
        mock_router.get_route.return_value = Route(
            total_duration_min=39.0,
            distance_m=5000.0,
            legs=[
                RouteLeg(
                    mode="bus",
                    duration_min=30.0,
                    distance_m=4500.0,
                    from_location="Dhoby Ghaut Shuttle",
                    to_location="Raffles Place",
                    line_name="Bus 190",
                ),
                RouteLeg(
                    mode="walk",
                    duration_min=9.0,
                    distance_m=500.0,
                    from_location="Bus Stop",
                    to_location="Raffles Place",
                ),
            ],
        )

        response = await journey_service.reroute_journey(journey.journey_id, routing_service=mock_router)

        # 1. Router must be called with current_position, NOT original origin
        mock_router.get_route.assert_called_once_with(current_pos, destination)

        # 2. Response verifies comparison
        self.assertEqual(response.status, "rerouted")
        self.assertEqual(response.previous_route.remaining_duration_min, 32.0)  # 25 + 7
        self.assertEqual(response.new_route.remaining_duration_min, 39.0)
        self.assertEqual(response.change.additional_duration_min, 7.0)  # 39 - 32

        # 3. Reason provides machine-readable explanation mentioning LTA shuttle
        self.assertIsInstance(response.change.reason, dict)
        self.assertEqual(response.change.reason.get("type"), "train_disruption")
        self.assertIn("free MRT shuttle is available", response.change.reason.get("message", ""))

        # 4. Journey state is updated
        self.assertEqual(journey.status, "rerouted")
        self.assertEqual(len(journey.remaining_legs), 2)
        self.assertEqual(journey.remaining_duration_min, 39.0)

    async def test_reroute_failure_transitions_to_reroute_failed(self):
        journey_service = JourneyService()
        journey = journey_service.create_journey(
            CreateJourneyRequest(
                route_id="r101",
                origin=Coordinates(lat=1.2966, lon=103.7764),
                destination=Coordinates(lat=1.2847, lon=103.8511),
                legs=[
                    JourneyLegInput(mode="mrt", line="CCL", from_location="Kent Ridge", to_location="Dhoby Ghaut", duration_min=20.0),
                ],
            )
        )
        journey.status = "reroute_required"

        mock_router = AsyncMock(spec=RoutingService)
        mock_router.get_route.side_effect = RuntimeError("Routing service unavailable")

        with self.assertRaises(HTTPException) as ctx:
            await journey_service.reroute_journey(journey.journey_id, routing_service=mock_router)

        self.assertEqual(ctx.exception.status_code, 502)
        self.assertEqual(journey.status, "reroute_failed")


if __name__ == "__main__":
    unittest.main()

