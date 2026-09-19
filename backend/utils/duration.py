import math
from pydantic import BaseModel, ConfigDict
from config import DISPLAY_INTERVAL_MINUTES


class DurationRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    min: int
    max: int


def duration_to_range(duration_minutes: float) -> DurationRange:
    """Convert a raw estimated duration into a user-facing DurationRange.

    Invariant:
        min >= 1
        max > min
        min <= duration_minutes <= max (for normal journeys)
        max - min == DISPLAY_INTERVAL_MINUTES (for standard journeys)
    """
    if duration_minutes is None:
        raise ValueError("duration_minutes cannot be None")

    if not isinstance(duration_minutes, (int, float)) or isinstance(duration_minutes, bool):
        raise ValueError("duration_minutes must be a valid number")

    if not math.isfinite(duration_minutes):
        raise ValueError("duration_minutes must be finite")

    if duration_minutes < 0:
        raise ValueError("duration_minutes cannot be negative")

    if duration_minutes < DISPLAY_INTERVAL_MINUTES:
        lower = max(1, math.floor(duration_minutes))
        upper = DISPLAY_INTERVAL_MINUTES
        return DurationRange(min=lower, max=upper)

    lower = math.floor(duration_minutes / DISPLAY_INTERVAL_MINUTES) * DISPLAY_INTERVAL_MINUTES
    upper = math.ceil(duration_minutes / DISPLAY_INTERVAL_MINUTES) * DISPLAY_INTERVAL_MINUTES
    if lower == upper:
        upper += DISPLAY_INTERVAL_MINUTES

    return DurationRange(min=lower, max=upper)

