import asyncio
from contextlib import suppress
import logging
from clients.lta_client import LTAClient
from config import Settings, get_settings
from models.disruptions import TrainServiceStatus
from services.journey_service import JourneyService

logger = logging.getLogger(__name__)


class DisruptionMonitor:
    """Monitors LTA TrainServiceAlerts, detects meaningful status changes, and notifies journeys."""

    def __init__(
        self,
        lta_client: LTAClient | None = None,
        journey_service: JourneyService | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()
        self._lta_client = lta_client or LTAClient(self.settings)
        self._journey_service = journey_service
        self.previous_status: TrainServiceStatus | None = None
        self.current_status: TrainServiceStatus | None = None
        self._poll_task: asyncio.Task | None = None
        self._running = False

    def set_journey_service(self, journey_service: JourneyService) -> None:
        if hasattr(journey_service, "_journeys"):
            self._journey_service = journey_service

    async def check_for_updates(self) -> TrainServiceStatus:
        curr = await self._lta_client.get_train_service_alerts()
        self.current_status = curr

        if self.is_meaningful_change(self.previous_status, curr):
            logger.info(
                "Meaningful disruption status change detected: prev_status=%s -> curr_status=%s",
                self.previous_status.status if self.previous_status else None,
                curr.status,
            )
            await self.process_update(self.previous_status, curr)
            self.previous_status = curr

        return curr

    @staticmethod
    def is_meaningful_change(prev: TrainServiceStatus | None, curr: TrainServiceStatus) -> bool:
        if prev is None:
            return True

        # Status 1 -> Status 2 or Status 2 -> Status 1
        if prev.status != curr.status:
            return True

        # Check fingerprint (affected segments lines, directions, stations)
        return prev.fingerprint != curr.fingerprint

    async def process_update(
        self,
        previous_status: TrainServiceStatus | None,
        current_status: TrainServiceStatus,
    ) -> None:
        if not self._journey_service or not hasattr(self._journey_service, "_journeys"):
            return

        for journey in list(self._journey_service._journeys.values()):
            self._journey_service.evaluate_journey_disruption(journey, current_status)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await self.check_for_updates()
            except Exception as err:
                logger.error("Error during disruption monitor poll: %s", err)
            await asyncio.sleep(self.settings.disruption_poll_interval_seconds)

