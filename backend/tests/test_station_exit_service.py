import unittest
from unittest.mock import AsyncMock
from models.responses import Coordinates
from services.station_exit_service import StationExitService


class TestStationExitService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_client = AsyncMock()
        self.mock_client.station_exits.return_value = [
            {
                "id": "EW4-EXIT-A",
                "station_id": "TANAH MERAH MRT STATION",
                "station_code": "EW4",
                "station_name": "TANAH MERAH MRT STATION",
                "exit_id": "A",
                "lat": 1.3270,
                "lon": 103.9460,
            },
            {
                "id": "EW4-EXIT-B",
                "station_id": "TANAH MERAH MRT STATION",
                "station_code": "EW4",
                "station_name": "TANAH MERAH MRT STATION",
                "exit_id": "B",
                "lat": 1.3275,
                "lon": 103.9465,
            },
            {
                "id": "CC22-EXIT-A",
                "station_id": "BUONA VISTA MRT STATION",
                "station_code": "CC22",
                "station_name": "BUONA VISTA MRT STATION",
                "exit_id": "A",
                "lat": 1.3072,
                "lon": 103.7900,
            },
        ]
        self.service = StationExitService(self.mock_client)

    async def test_exits_for_station_name_full_name(self):
        exits = await self.service.exits_for_station_name("TANAH MERAH MRT STATION")
        self.assertEqual(len(exits), 2)
        self.assertEqual({e["exit_id"] for e in exits}, {"A", "B"})

    async def test_exits_for_station_name_short_name(self):
        exits = await self.service.exits_for_station_name("Tanah Merah")
        self.assertEqual(len(exits), 2)
        self.assertEqual({e["exit_id"] for e in exits}, {"A", "B"})

    async def test_exits_for_station_name_by_code(self):
        exits = await self.service.exits_for_station_name("EW4")
        self.assertEqual(len(exits), 2)
        self.assertEqual({e["exit_id"] for e in exits}, {"A", "B"})

    async def test_exits_for_station_by_id_or_code(self):
        exits = await self.service.exits_for_station("EW4")
        self.assertEqual(len(exits), 2)

        exits_full = await self.service.exits_for_station("TANAH MERAH MRT STATION")
        self.assertEqual(len(exits_full), 2)

    async def test_nearest_exits(self):
        # Point close to EW4 exit B
        target = Coordinates(lat=1.3276, lon=103.9466)
        exits = await self.service.nearest_exits(target, limit=2)
        self.assertEqual(len(exits), 2)
        self.assertEqual(exits[0]["exit_id"], "B")
        self.assertEqual(exits[1]["exit_id"], "A")


if __name__ == "__main__":
    unittest.main()

