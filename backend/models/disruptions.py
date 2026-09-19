from datetime import datetime, timezone
import hashlib
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class TrainDisruption(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    line: str
    direction: str = ""
    stations: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("stations", "affected_stations", "affectedStations"),
    )
    free_public_bus: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("free_public_bus", "freePublicBus"),
    )
    free_mrt_shuttle: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("free_mrt_shuttle", "freeMrtShuttle"),
    )
    mrt_shuttle_direction: str | None = Field(
        default=None,
        validation_alias=AliasChoices("mrt_shuttle_direction", "mrtShuttleDirection"),
    )

    @property
    def affected_stations(self) -> list[str]:
        return self.stations

    def segment_hash(self) -> str:
        stations_tuple = tuple(sorted(s.strip().upper() for s in self.stations if s.strip()))
        return f"{self.line.upper()}:{self.direction.upper()}:{stations_tuple}"


class TrainServiceStatus(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: int
    affected_segments: list[TrainDisruption] = Field(
        default_factory=list,
        validation_alias=AliasChoices("affected_segments", "affectedSegments"),
    )
    messages: list[str] = Field(default_factory=list)
    data_status: str = Field(
        default="ok",
        validation_alias=AliasChoices("data_status", "dataStatus"),
    )  # "ok", "stale", "unavailable"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def fingerprint(self) -> str:
        if self.status == 1 or not self.affected_segments:
            return f"status:1:data:{self.data_status}"
        segment_hashes = sorted(seg.segment_hash() for seg in self.affected_segments)
        raw = f"status:{self.status}:data:{self.data_status}:segments:{','.join(segment_hashes)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

