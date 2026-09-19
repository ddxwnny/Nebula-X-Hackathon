"""Live bus arrivals (LTA BusArrival) and the journey's arrival time.

The arrival estimate is computed here, server-side, by walking the legs in
order: walking legs add their duration, transit legs wait for their boarding
time. A bus leg boards on a live LTA ETA when the rider reaches the stop within
LTA's live horizon (the next 3 buses); every other transit leg boards on
OneMap's timetable. `basis` says which was used, and becomes "uncertain" when
the estimate relies on something the rider may not be able to do.
"""

from datetime import date, datetime, time, timedelta
from typing import Callable

from clients.lta_datamall_client import LtaDataMallClient
from models.responses import ArrivalEstimate, BusEta, BusServiceArrivals, BusStopArrivals, LiveBusInfo, Route, RouteLeg
from services.routing_service import SGT

# Live ETAs describe only the next 3 buses (~30 min), so they are used only for
# journeys starting within this window of now (and not ones that already started).
LIVE_WINDOW = timedelta(minutes=15)
LIVE_PAST_TOLERANCE = timedelta(minutes=2)
# A transit leg reached more than this after its timetabled departure is a missed connection.
MISSED_CONNECTION_GRACE = timedelta(minutes=1)

_LOAD = {"SEA": "seats_available", "SDA": "standing_available", "LSD": "limited_standing"}
_TYPE = {"SD": "single_deck", "DD": "double_deck", "BD": "bendy"}


def parse_bus(raw: object, now: datetime) -> BusEta | None:
    """One NextBus/NextBus2/NextBus3 entry; LTA leaves EstimatedArrival blank when no bus is scheduled."""
    if not isinstance(raw, dict) or not raw.get("EstimatedArrival"):
        return None
    try:
        eta = datetime.fromisoformat(str(raw["EstimatedArrival"]))
    except ValueError:
        return None
    if eta.tzinfo is None:
        eta = eta.replace(tzinfo=SGT)
    return BusEta(
        estimated_arrival=eta,
        minutes_away=max(0, int((eta - now).total_seconds() // 60)),
        wheelchair_accessible=raw.get("Feature") == "WAB",
        load=_LOAD.get(str(raw.get("Load")), "unknown"),
        bus_type=_TYPE.get(str(raw.get("Type")), "unknown"),
        monitored=str(raw.get("Monitored")) == "1",
    )


def parse_service(raw: dict, now: datetime) -> BusServiceArrivals:
    buses = [bus for key in ("NextBus", "NextBus2", "NextBus3") if (bus := parse_bus(raw.get(key), now))]
    operator = raw.get("Operator")
    return BusServiceArrivals(service_no=str(raw.get("ServiceNo", "")), operator=str(operator) if operator is not None else None, next_buses=sorted(buses, key=lambda bus: bus.estimated_arrival))


def _services(raw: list | None) -> list[dict]:
    return [service for service in raw or [] if isinstance(service, dict)]


def _same_service(a: object, b: str) -> bool:
    return str(a).strip().upper() == b.strip().upper()


def _hhmm(moment: datetime) -> str:
    return moment.astimezone(SGT).strftime("%H:%M")


class LiveTransitService:
    def __init__(self, lta_client: LtaDataMallClient | None = None, clock: Callable[[], datetime] | None = None):
        self._lta = lta_client or LtaDataMallClient()
        self._now = clock or (lambda: datetime.now(SGT))

    def now(self) -> datetime:
        """Current Singapore time; the pipeline uses it to resolve "leave now" journeys."""
        return self._now()

    async def stop_arrivals(self, stop_code: str, service_no: str | None = None) -> BusStopArrivals:
        now = self._now()
        raw = await self._lta.bus_arrivals(stop_code)
        if raw is None:
            return BusStopArrivals(stop_code=stop_code, status="unavailable", fetched_at=now)
        services = [parse_service(service, now) for service in _services(raw) if not service_no or _same_service(service.get("ServiceNo", ""), service_no)]
        # Distinguish "that service does not call here / has no data" from live data.
        status = "no_service" if service_no and not services else "live"
        return BusStopArrivals(stop_code=stop_code, status=status, fetched_at=now, services=services)

    async def apply(self, route: Route, departure_date: date | None, departure_time: time | None, *, step_free: bool) -> Route:
        now = self._now()
        start = datetime.combine(departure_date or now.date(), departure_time or now.time().replace(microsecond=0), SGT)
        in_live_window = -LIVE_PAST_TOLERANCE <= start - now <= LIVE_WINDOW
        clock, used_live, cautions = start, False, []
        for leg in route.legs:
            if leg.mode == "bus" and leg.stop_code and leg.service_no:
                leg.live_bus = await self._live_bus(leg, clock if in_live_window else None, step_free, now)
            live = leg.live_bus
            if live and live.boarding_eta:
                clock, used_live = max(clock, live.boarding_eta), True
            elif live and live.status == "no_suitable_bus" and live.next_buses:
                # None of the listed buses can be boarded, so the earliest possible
                # boarding is after the last one LTA reports: the arrival is a lower bound.
                clock = max(clock, live.next_buses[-1].estimated_arrival)
                cautions.append(f"No wheelchair-accessible bus {leg.service_no} among the next {live.skipped_inaccessible} you can reach; you will arrive later than this.")
            elif leg.mode != "walk" and leg.scheduled_departure:
                if clock > leg.scheduled_departure + MISSED_CONNECTION_GRACE:
                    cautions.append(f"Tight connection: you may miss the {_hhmm(leg.scheduled_departure)} {leg.mode.upper()} departure from {leg.from_location}.")
                clock = max(clock, leg.scheduled_departure)
            elif leg.mode != "walk":
                cautions.append(f"No timetable for the {leg.mode.upper()} leg from {leg.from_location}; waiting time is not included.")
            clock += timedelta(minutes=leg.duration_min)
        if cautions:
            basis, note = "uncertain", " ".join(cautions)
        elif used_live:
            basis, note = "live", "Uses live LTA bus arrival times for bus boarding."
        else:
            basis, note = "scheduled", "Based on OneMap timetables; no live bus arrival was used."
        route.estimated_arrival = ArrivalEstimate(departure=start, arrival=clock, basis=basis, note=note)
        return route

    async def _live_bus(self, leg: RouteLeg, reach_stop_at: datetime | None, step_free: bool, now: datetime) -> LiveBusInfo:
        base = {"stop_code": leg.stop_code, "service_no": leg.service_no}
        if reach_stop_at is None:
            return LiveBusInfo(**base, status="outside_live_window", message=f"Live arrivals only apply to journeys starting within {int(LIVE_WINDOW.total_seconds() // 60)} minutes of now.")
        raw = await self._lta.bus_arrivals(leg.stop_code)
        service = next((parse_service(item, now) for item in _services(raw) if _same_service(item.get("ServiceNo", ""), leg.service_no)), None)
        if service is None or not service.next_buses:
            return LiveBusInfo(**base, status="unavailable", message=f"No live arrival data for bus {leg.service_no} at stop {leg.stop_code}.")
        reachable = [bus for bus in service.next_buses if bus.estimated_arrival >= reach_stop_at]
        if not reachable:
            # Every listed bus leaves before the rider gets there: beyond LTA's live horizon, not "no bus".
            return LiveBusInfo(**base, status="beyond_live_horizon", next_buses=service.next_buses, message=f"You reach this stop after the buses LTA currently reports; using the timetable for bus {leg.service_no}.")
        boardable = [bus for bus in reachable if bus.wheelchair_accessible or not step_free]
        if not boardable:
            return LiveBusInfo(**base, status="no_suitable_bus", next_buses=service.next_buses, skipped_inaccessible=len(reachable), message=f"No wheelchair-accessible bus {leg.service_no} among the next {len(reachable)} you can reach.")
        board = boardable[0]
        skipped = sum(1 for bus in reachable if bus.estimated_arrival < board.estimated_arrival and not bus.wheelchair_accessible)
        # Bus lateness: the GPS-tracked bus closest to the timetabled departure (the trip the
        # timetable means, even if it ran early and has gone) vs that departure. Waiting for an
        # accessible bus is reported separately (skipped_inaccessible), and lateness is only
        # reported when the rider is at the stop in time for the timetable.
        delay = None
        tracked = [bus for bus in service.next_buses if bus.monitored]
        if leg.scheduled_departure and reach_stop_at <= leg.scheduled_departure and tracked:
            trip = min(tracked, key=lambda bus: abs(bus.estimated_arrival - leg.scheduled_departure))
            delay = round((trip.estimated_arrival - leg.scheduled_departure).total_seconds() / 60, 1)
        return LiveBusInfo(
            **base,
            status="live",
            next_buses=service.next_buses,
            boarding_eta=board.estimated_arrival,
            boarding_bus_wheelchair_accessible=board.wheelchair_accessible,
            delay_vs_schedule_min=delay,
            skipped_inaccessible=skipped,
            message=f"Bus {leg.service_no} at {_hhmm(board.estimated_arrival)} (" + ("arriving now" if board.minutes_away == 0 else f"in {board.minutes_away} min") + ")" + ("" if board.monitored else ", timetable estimate, not GPS-tracked") + ".",
        )
