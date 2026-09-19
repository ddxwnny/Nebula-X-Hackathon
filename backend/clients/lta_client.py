import logging
from typing import Any
import httpx

from config import Settings, get_settings
from models.disruptions import TrainDisruption, TrainServiceStatus

logger = logging.getLogger(__name__)


class LTAClient:
    """Dedicated adapter for LTA DataMall TrainServiceAlerts."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._last_known_status: TrainServiceStatus | None = None

    async def get_train_service_alerts(self) -> TrainServiceStatus:
        if not self.settings.lta_datamall_account_key:
            # Without an account key, we cannot query LTA DataMall
            return self._fallback_status("unavailable", "Missing LTA DataMall AccountKey")

        headers = {
            "AccountKey": self.settings.lta_datamall_account_key,
            "accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
                response = await client.get(
                    self.settings.lta_train_service_alerts_url,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as err:
            logger.warning("Failed to fetch TrainServiceAlerts: %s", err)
            return self._fallback_status("stale" if self._last_known_status else "unavailable", str(err))

        status = self._parse_payload(data)
        self._last_known_status = status
        return status

    def _parse_payload(self, data: dict[str, Any]) -> TrainServiceStatus:
        # LTA DataMall TrainServiceAlerts wraps the structure in 'value'
        val = data.get("value", data)
        if isinstance(val, list) and val:
            val = val[0]
        elif not isinstance(val, dict):
            val = {}

        raw_status = val.get("Status", 1)
        try:
            status_code = int(raw_status)
        except (ValueError, TypeError):
            status_code = 1

        raw_segments = val.get("AffectedSegments", [])
        if isinstance(raw_segments, dict):
            raw_segments = [raw_segments]

        segments: list[TrainDisruption] = []
        for seg in raw_segments:
            if not isinstance(seg, dict):
                continue
            line = str(seg.get("Line") or "").strip().upper()
            direction = str(seg.get("Direction") or "").strip()

            raw_stations = seg.get("Stations", [])
            stations = self._normalize_list(raw_stations)

            free_bus = self._normalize_list(seg.get("FreePublicBus", []))
            free_shuttle = self._normalize_list(seg.get("FreeMRTShuttle", []))
            shuttle_direction = seg.get("MRTShuttleDirection")
            if shuttle_direction:
                shuttle_direction = str(shuttle_direction).strip()

            if line or stations:
                segments.append(
                    TrainDisruption(
                        line=line,
                        direction=direction,
                        stations=stations,
                        free_public_bus=free_bus,
                        free_mrt_shuttle=free_shuttle,
                        mrt_shuttle_direction=shuttle_direction,
                    )
                )

        raw_messages = val.get("Message", [])
        messages: list[str] = []
        if isinstance(raw_messages, list):
            for msg in raw_messages:
                if isinstance(msg, dict):
                    content = msg.get("Content") or msg.get("text") or str(msg)
                    messages.append(str(content).strip())
                elif isinstance(msg, str) and msg.strip():
                    messages.append(msg.strip())
        elif isinstance(raw_messages, str) and raw_messages.strip():
            messages.append(raw_messages.strip())

        return TrainServiceStatus(
            status=status_code,
            affected_segments=segments,
            messages=messages,
            data_status="ok",
        )

    @staticmethod
    def _normalize_list(val: Any) -> list[str]:
        if isinstance(val, str):
            parts = [p.strip().upper() for p in val.replace(";", ",").split(",") if p.strip()]
            return parts
        if isinstance(val, list):
            res = []
            for item in val:
                if isinstance(item, str):
                    for sub in item.replace(";", ",").split(","):
                        if sub.strip():
                            res.append(sub.strip().upper())
                elif item is not None:
                    res.append(str(item).strip().upper())
            return res
        return []

    def _fallback_status(self, data_status: str, error_msg: str) -> TrainServiceStatus:
        if self._last_known_status:
            return TrainServiceStatus(
                status=self._last_known_status.status,
                affected_segments=self._last_known_status.affected_segments,
                messages=self._last_known_status.messages + [f"Data is stale: {error_msg}"],
                data_status="stale",
            )
        return TrainServiceStatus(
            status=1,
            affected_segments=[],
            messages=[f"Service alerts unavailable: {error_msg}"],
            data_status=data_status,
        )

