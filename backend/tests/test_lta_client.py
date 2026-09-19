import unittest
from unittest.mock import AsyncMock, patch
import httpx
from clients.lta_client import LTAClient
from config import Settings


class TestLTAClient(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = Settings(
            lta_datamall_account_key="test-key",
            lta_train_service_alerts_url="https://example.com/alerts",
        )
        self.client = LTAClient(self.settings)

    def test_parse_normal_response(self):
        payload = {
            "value": {
                "Status": 1,
                "AffectedSegments": [],
                "Message": [],
            }
        }
        status = self.client._parse_payload(payload)
        self.assertEqual(status.status, 1)
        self.assertEqual(status.affected_segments, [])
        self.assertEqual(status.data_status, "ok")

    def test_parse_disrupted_response(self):
        payload = {
            "value": {
                "Status": 2,
                "AffectedSegments": [
                    {
                        "Line": "CCL",
                        "Direction": "Dhoby Ghaut",
                        "Stations": "CC10,CC9,CC8",
                        "FreePublicBus": "Available between CC10 and CC8",
                        "FreeMRTShuttle": "Shuttle A, Shuttle B",
                        "MRTShuttleDirection": "Both",
                    }
                ],
                "Message": [
                    {
                        "Content": "Train service disrupted between CC10 and CC8.",
                        "CreatedDate": "2026-09-19 10:00",
                    }
                ],
            }
        }
        status = self.client._parse_payload(payload)
        self.assertEqual(status.status, 2)
        self.assertEqual(len(status.affected_segments), 1)
        seg = status.affected_segments[0]
        self.assertEqual(seg.line, "CCL")
        self.assertEqual(seg.direction, "Dhoby Ghaut")
        self.assertEqual(seg.stations, ["CC10", "CC9", "CC8"])
        self.assertEqual(seg.free_public_bus, ["AVAILABLE BETWEEN CC10 AND CC8"])
        self.assertEqual(seg.free_mrt_shuttle, ["SHUTTLE A", "SHUTTLE B"])
        self.assertEqual(seg.mrt_shuttle_direction, "Both")
        self.assertIn("Train service disrupted between CC10 and CC8.", status.messages[0])

    def test_parse_multiple_affected_segments(self):
        payload = {
            "value": {
                "Status": 2,
                "AffectedSegments": [
                    {"Line": "CCL", "Stations": "CC8,CC9"},
                    {"Line": "NEL", "Stations": ["NE6", "NE7"]},
                ],
                "Message": ["Disruptions on CCL and NEL"],
            }
        }
        status = self.client._parse_payload(payload)
        self.assertEqual(status.status, 2)
        self.assertEqual(len(status.affected_segments), 2)
        self.assertEqual(status.affected_segments[0].line, "CCL")
        self.assertEqual(status.affected_segments[1].line, "NEL")
        self.assertEqual(status.affected_segments[1].stations, ["NE6", "NE7"])

    async def test_missing_account_key(self):
        client = LTAClient(Settings(lta_datamall_account_key=None))
        status = await client.get_train_service_alerts()
        self.assertEqual(status.data_status, "unavailable")
        self.assertEqual(status.status, 1)

    @patch("httpx.AsyncClient.get")
    async def test_api_http_error_falls_back_to_stale(self, mock_get):
        # First call succeeds
        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None
        mock_response.json = lambda: {
            "value": {
                "Status": 2,
                "AffectedSegments": [{"Line": "CCL", "Stations": "CC9"}],
                "Message": ["Disruption"],
            }
        }
        mock_get.return_value = mock_response

        status1 = await self.client.get_train_service_alerts()
        self.assertEqual(status1.data_status, "ok")
        self.assertEqual(status1.status, 2)

        # Second call fails with HTTP 500
        mock_get.side_effect = httpx.HTTPStatusError("500 Server Error", request=None, response=None)
        status2 = await self.client.get_train_service_alerts()
        self.assertEqual(status2.data_status, "stale")
        self.assertEqual(status2.status, 2)
        self.assertEqual(len(status2.affected_segments), 1)

    @patch("httpx.AsyncClient.get")
    async def test_station_exits_fetch_and_cache(self, mock_get):
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.json = lambda: {
            "features": [
                {
                    "geometry": {"coordinates": [103.9463, 1.3273]},
                    "properties": {
                        "STATION_NA": "TANAH MERAH MRT STATION",
                        "STN_NO": "EW4",
                        "EXIT_CODE": "B",
                    },
                }
            ]
        }
        mock_get.return_value = mock_resp

        # Clear cache first
        LTAClient._exit_cache = []
        from datetime import datetime, timezone
        LTAClient._exit_cache_until = datetime.min.replace(tzinfo=timezone.utc)

        exits = await self.client.station_exits()
        self.assertEqual(len(exits), 1)
        self.assertEqual(exits[0]["station_code"], "EW4")
        self.assertEqual(exits[0]["station_name"], "TANAH MERAH MRT STATION")
        self.assertEqual(exits[0]["exit_id"], "B")
        self.assertAlmostEqual(exits[0]["lat"], 1.3273)
        self.assertAlmostEqual(exits[0]["lon"], 103.9463)

        # Call again, should use cache without calling mock_get again
        mock_get.reset_mock()
        cached_exits = await self.client.station_exits()
        self.assertEqual(len(cached_exits), 1)
        mock_get.assert_not_called()

    def test_datamall_client_backwards_compatibility(self):
        from clients.lta_datamall_client import LtaDataMallClient
        self.assertIs(LtaDataMallClient, LTAClient)


if __name__ == "__main__":
    unittest.main()

