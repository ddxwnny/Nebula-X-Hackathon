import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from clients.lta_datamall_client import LtaDataMallClient, station_key
from models.requests import RoutePreferences
from models.responses import Coordinates, Route, RouteLeg
from services.exit_routing_service import ExitRoutingService
from services.station_exit_service import StationExitService, _outage_exits, build_exit_markers


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


HOUGANG = "HOUGANG MRT STATION"


class TestStationExitMarkers(unittest.TestCase):
    def setUp(self):
        self.client = FakeLtaClient(
            exits=[
                exit_(HOUGANG, "Exit A"),
                exit_(HOUGANG, "Exit B"),
                exit_(HOUGANG, "Exit C"),
                exit_("PUNGGOL MRT STATION", "Exit A"),
            ],
            maintenance=[
                {"StationName": "Hougang", "LiftID": "B1 L01", "LiftDesc": "Exit A Street level - Concourse"},
                {"StationName": "Hougang", "LiftID": "B2 L01", "LiftDesc": "Lift 1 (connecting concourse to Platform 1)"},
                {"StationName": "Punggol Point", "LiftID": "X", "LiftDesc": "Exit B Street level"},
                {"StationName": "", "LiftID": "Z", "LiftDesc": "Lift with no station name"},
            ],
        )
        self.service = StationExitService(self.client)

    def markers(self, name, selected=None):
        async def run():
            exits = await self.service.exits_for_station_name(name)
            return build_exit_markers(exits, (await self.client.lift_statuses(name)).values(), selected)
        return asyncio.run(run())

    def test_station_key_normalises_lta_and_onemap_names(self):
        self.assertEqual(station_key("HOUGANG MRT STATION"), "HOUGANG")
        self.assertEqual(station_key("Hougang"), "HOUGANG")
        self.assertEqual(station_key("PUNGGOL POINT LRT STATION"), "PUNGGOL POINT")

    def test_returns_all_exits_of_station_only(self):
        self.assertEqual([m.exit_name for m in self.markers(HOUGANG)], ["Exit A", "Exit B", "Exit C"])

    def test_exit_specific_outage_marks_only_that_exit(self):
        by_name = {m.exit_name: m for m in self.markers(HOUGANG)}
        self.assertEqual(by_name["Exit A"].lift_status, "maintenance")
        self.assertEqual(by_name["Exit A"].lift_alerts, ["Exit A Street level - Concourse"])
        self.assertEqual(by_name["Exit B"].lift_status, "no_reported_outage")

    def test_station_wide_outage_attached_to_every_exit(self):
        for marker in self.markers(HOUGANG):
            self.assertEqual(marker.station_lift_alerts, ["Lift 1 (connecting concourse to Platform 1)"])

    def test_similarly_named_or_blank_station_outage_not_applied(self):
        (marker,) = self.markers("PUNGGOL MRT STATION")
        self.assertEqual(marker.lift_status, "no_reported_outage")
        self.assertEqual(marker.station_lift_alerts, [])

    def test_blank_station_name_matches_nothing(self):
        self.assertEqual(asyncio.run(self.client.lift_statuses("")), {})

    def test_selected_exit_flagged(self):
        markers = self.markers(HOUGANG, {f"{HOUGANG}-EXIT-Exit B"})
        self.assertEqual([m.exit_name for m in markers if m.is_selected], ["Exit B"])

    def test_unknown_station_returns_no_markers(self):
        self.assertEqual(self.markers("NOWHERE MRT STATION"), [])


class TestOutageExitParsing(unittest.TestCase):
    def test_exit_codes_read_from_descriptions(self):
        cases = {
            "Exit A Street level - Concourse": {"EXIT A"},
            "(TEL) EXIT A STREET LEVEL - PLATFORM B - PLATFORM A": {"EXIT A"},
            "Exit A/B street level": {"EXIT A", "EXIT B"},
            "Exits 1 and 2A lift": {"EXIT 1", "EXIT 2A"},
            "Near exit Street level then Exit C": {"EXIT C"},
            "Lift 2 (Exit to Bus Interchange)": set(),
            "Lift 1 (connecting concourse to Platform 1)": set(),
        }
        for description, expected in cases.items():
            with self.subTest(description=description):
                self.assertEqual(_outage_exits({"description": description}), expected)

    def test_outage_naming_unknown_exit_becomes_station_wide(self):
        exits = [exit_(HOUGANG, "Exit A"), exit_(HOUGANG, "Exit B")]
        markers = build_exit_markers(exits, [
            {"status": "maintenance", "description": "Exit F Street level"},
            {"status": "maintenance", "description": "Lift 2 (Exit to Bus Interchange)"},
        ])
        for marker in markers:
            self.assertEqual(marker.lift_status, "no_reported_outage")
            self.assertEqual(marker.station_lift_alerts, ["Exit F Street level", "Lift 2 (Exit to Bus Interchange)"])

    def test_outage_naming_two_exits_marks_both(self):
        exits = [exit_(HOUGANG, "Exit A"), exit_(HOUGANG, "Exit B"), exit_(HOUGANG, "Exit C")]
        markers = build_exit_markers(exits, [{"status": "maintenance", "description": "Exit A/B Street level"}])
        self.assertEqual([m.exit_name for m in markers if m.lift_status == "maintenance"], ["Exit A", "Exit B"])

    def test_numbered_exits_sort_naturally(self):
        exits = [exit_(HOUGANG, code) for code in ("Exit 10", "Exit 2", "Exit 1")]
        self.assertEqual([m.exit_name for m in build_exit_markers(exits, [])], ["Exit 1", "Exit 2", "Exit 10"])


class TestExitRoutingCandidateExits(unittest.IsolatedAsyncioTestCase):
    async def test_loop_journey_keeps_alighting_selection_after_dedupe(self):
        """Boarding and alighting at Hougang: only the alighting copy of the exit is selected."""
        client = FakeLtaClient(
            exits=[exit_(HOUGANG, "Exit A"), exit_(HOUGANG, "Exit B"), exit_("PUNGGOL MRT STATION", "Exit A", lat=1.40, lon=103.90)],
            maintenance=[{"StationName": "Hougang", "LiftID": "B1 L01", "LiftDesc": "Exit A Street level - Concourse"}],
        )
        routing = MagicMock()
        routing.get_walking_route = AsyncMock(return_value={"route_summary": {"total_time": 120, "total_distance": 100}, "route_geometry": ""})
        service = ExitRoutingService(routing_client=routing, station_exits=StationExitService(client), lta_client=client)
        route = Route(total_duration_min=30.0, distance_m=9000.0, legs=[
            RouteLeg(mode="mrt", duration_min=10.0, distance_m=4000.0, from_location=HOUGANG, to_location="PUNGGOL MRT STATION", line_name="NE"),
            RouteLeg(mode="mrt", duration_min=10.0, distance_m=4000.0, from_location="PUNGGOL MRT STATION", to_location=HOUGANG, line_name="NE"),
            RouteLeg(mode="walk", duration_min=5.0, distance_m=300.0, from_location=HOUGANG, to_location="Destination"),
        ])

        result = await service.apply(route, Coordinates(lat=1.37, lon=103.89), Coordinates(lat=1.371, lon=103.891), RoutePreferences(step_free=True))

        candidates = result.exit_routing.candidate_exits
        self.assertEqual(sorted(c.id for c in candidates), [f"{HOUGANG}-EXIT-Exit A", f"{HOUGANG}-EXIT-Exit B"])
        by_name = {c.exit_name: c for c in candidates}
        self.assertTrue(by_name["Exit B"].is_selected)
        self.assertFalse(by_name["Exit A"].is_selected)
        self.assertEqual(by_name["Exit A"].lift_status, "maintenance")


if __name__ == "__main__":
    unittest.main()
