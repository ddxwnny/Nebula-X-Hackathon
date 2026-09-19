import asyncio
import unittest

from clients.lta_datamall_client import LtaDataMallClient, station_key
from services.station_exit_service import StationExitService


class FakeLtaClient(LtaDataMallClient):
    """Real station/outage matching over canned LTA payloads."""
    def __init__(self, exits, maintenance):
        self._exits, self._maintenance = exits, maintenance
        self._maintenance_cache = {}

    async def station_exits(self):
        return self._exits

    async def all_lift_maintenance(self):
        return self._maintenance


def exit_(station, code, lat=1.37, lon=103.89):
    return {"id": f"{station}-EXIT-{code}", "station_id": station, "exit_id": code, "lat": lat, "lon": lon}


class TestStationExitMarkers(unittest.TestCase):
    def setUp(self):
        self.client = FakeLtaClient(
            exits=[
                exit_("HOUGANG MRT STATION", "Exit A"),
                exit_("HOUGANG MRT STATION", "Exit B"),
                exit_("HOUGANG MRT STATION", "Exit C"),
                exit_("PUNGGOL MRT STATION", "Exit A"),
            ],
            maintenance=[
                {"StationName": "Hougang", "LiftID": "B1 L01", "LiftDesc": "Exit A Street level - Concourse"},
                {"StationName": "Hougang", "LiftID": "B2 L01", "LiftDesc": "Lift 1 (connecting concourse to Platform 1)"},
                {"StationName": "Punggol Point", "LiftID": "X", "LiftDesc": "Exit B Street level"},
            ],
        )
        self.service = StationExitService(self.client)

    def markers(self, name, selected=None):
        return asyncio.run(self.service.exit_markers(name, selected))

    def test_station_key_normalises_lta_and_onemap_names(self):
        self.assertEqual(station_key("HOUGANG MRT STATION"), "HOUGANG")
        self.assertEqual(station_key("Hougang"), "HOUGANG")
        self.assertEqual(station_key("PUNGGOL POINT LRT STATION"), "PUNGGOL POINT")

    def test_returns_all_exits_of_station_only(self):
        markers = self.markers("HOUGANG MRT STATION")
        self.assertEqual([m.exit_name for m in markers], ["Exit A", "Exit B", "Exit C"])

    def test_exit_specific_outage_marks_only_that_exit(self):
        by_name = {m.exit_name: m for m in self.markers("HOUGANG MRT STATION")}
        self.assertEqual(by_name["Exit A"].lift_status, "maintenance")
        self.assertEqual(by_name["Exit A"].lift_alerts, ["Exit A Street level - Concourse"])
        self.assertEqual(by_name["Exit B"].lift_status, "no_reported_outage")

    def test_station_wide_outage_attached_to_every_exit(self):
        for marker in self.markers("HOUGANG MRT STATION"):
            self.assertEqual(marker.station_lift_alerts, ["Lift 1 (connecting concourse to Platform 1)"])

    def test_similarly_named_station_outage_not_applied(self):
        (marker,) = self.markers("PUNGGOL MRT STATION")
        self.assertEqual(marker.lift_status, "no_reported_outage")
        self.assertEqual(marker.station_lift_alerts, [])

    def test_selected_exit_flagged(self):
        markers = self.markers("HOUGANG MRT STATION", {"HOUGANG MRT STATION-EXIT-Exit B"})
        self.assertEqual([m.exit_name for m in markers if m.is_selected], ["Exit B"])

    def test_unknown_station_returns_no_markers(self):
        self.assertEqual(self.markers("NOWHERE MRT STATION"), [])


if __name__ == "__main__":
    unittest.main()
