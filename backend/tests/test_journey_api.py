import unittest
from unittest.mock import AsyncMock, patch
import httpx
from main import app
from models.disruptions import TrainDisruption, TrainServiceStatus
from models.responses import Coordinates, Route, RouteLeg


class TestJourneyAPI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_full_journey_lifecycle_api(self):
        # 1. Create a journey
        create_payload = {
            "route_id": "route_123",
            "origin": {"lat": 1.2966, "lon": 103.7764},
            "destination": {"lat": 1.2847, "lon": 103.8511},
            "legs": [
                {
                    "mode": "walk",
                    "from": "Origin",
                    "to": "Kent Ridge MRT",
                    "duration_min": 5.0,
                },
                {
                    "mode": "mrt",
                    "line": "CCL",
                    "from": "Kent Ridge",
                    "to": "Dhoby Ghaut",
                    "duration_min": 27.0,
                },
            ],
        }

        resp = await self.client.post("/api/v1/journeys", json=create_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("journey_id", data)
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["route_id"], "route_123")
        journey_id = data["journey_id"]

        # 2. Check status when no disruption is present
        with patch("services.disruption_monitor.DisruptionMonitor.check_for_updates") as mock_check:
            mock_check.return_value = TrainServiceStatus(status=1, affected_segments=[])
            status_resp = await self.client.get(f"/api/v1/journeys/{journey_id}/status")
            self.assertEqual(status_resp.status_code, 200)
            status_data = status_resp.json()
            self.assertEqual(status_data["journey_id"], journey_id)
            self.assertEqual(status_data["status"], "unaffected")
            self.assertIsNone(status_data["disruption"])

        # 3. Simulate disruption detection on CCL affecting Kent Ridge -> Dhoby Ghaut
        with patch("services.disruption_monitor.DisruptionMonitor.check_for_updates") as mock_check:
            mock_check.return_value = TrainServiceStatus(
                status=2,
                affected_segments=[
                    TrainDisruption(
                        line="CCL",
                        direction="Dhoby Ghaut",
                        stations=["CC10", "CC9", "CC8"],
                        free_public_bus=["Between CC10 and CC8"],
                        free_mrt_shuttle=["Loop shuttle A"],
                    )
                ],
                messages=["Circle Line disruption at CC10-CC8"],
            )
            status_resp = await self.client.get(f"/api/v1/journeys/{journey_id}/status")
            self.assertEqual(status_resp.status_code, 200)
            status_data = status_resp.json()
            self.assertEqual(status_data["status"], "reroute_required")
            self.assertIsNotNone(status_data["disruption"])
            self.assertEqual(status_data["disruption"]["line"], "CCL")
            self.assertEqual(status_data["disruption"]["affected_stations"], ["CC10", "CC8", "CC9"])

        # 4. Request reroute from current position
        mock_route = Route(
            total_duration_min=39.0,
            distance_m=6000.0,
            legs=[
                RouteLeg(
                    mode="bus",
                    duration_min=35.0,
                    distance_m=5500.0,
                    from_location="Kent Ridge Bus Stop",
                    to_location="Raffles Place",
                ),
                RouteLeg(
                    mode="walk",
                    duration_min=4.0,
                    distance_m=500.0,
                    from_location="Raffles Place",
                    to_location="Destination",
                ),
            ],
        )

        with patch("services.routing_service.RoutingService.get_route", new_callable=AsyncMock) as mock_get_route:
            mock_get_route.return_value = mock_route
            reroute_resp = await self.client.post(f"/api/v1/journeys/{journey_id}/reroute")
            self.assertEqual(reroute_resp.status_code, 200)
            reroute_data = reroute_resp.json()
            self.assertEqual(reroute_data["status"], "rerouted")
            self.assertEqual(reroute_data["previous_route"]["remaining_duration_min"], 32.0)
            self.assertEqual(reroute_data["new_route"]["remaining_duration_min"], 39.0)
            self.assertEqual(reroute_data["change"]["additional_duration_min"], 7.0)
            self.assertIn("reason", reroute_data["change"])

    async def test_non_existent_journey_returns_404(self):
        resp = await self.client.get("/api/v1/journeys/journey_nonexistent/status")
        self.assertEqual(resp.status_code, 404)

        resp = await self.client.post("/api/v1/journeys/journey_nonexistent/reroute")
        self.assertEqual(resp.status_code, 404)

    async def test_get_disruptions_status(self):
        with patch("services.disruption_monitor.DisruptionMonitor.check_for_updates") as mock_check:
            mock_check.return_value = TrainServiceStatus(
                status=2,
                affected_segments=[
                    TrainDisruption(line="CCL", stations=["CC10", "CC9", "CC8"])
                ],
                messages=["Disruption test"],
            )
            resp = await self.client.get("/api/v1/disruptions/status")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], 2)
            self.assertEqual(len(data["affected_segments"]), 1)
            self.assertEqual(data["affected_segments"][0]["line"], "CCL")


if __name__ == "__main__":
    unittest.main()
