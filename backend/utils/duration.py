import math
from pydantic import BaseModel, ConfigDict
from config import DISPLAY_INTERVAL_MINUTES


class DurationRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    min: int
    max: int


def duration_to_range(duration_minutes: float) -> DurationRange:
    """Convert a raw estimated duration into a user-facing DurationRange.

    For journeys below DISPLAY_INTERVAL_MINUTES (default 5 min), returns a
    single rounded whole-minute range (min == max) to avoid misleading ranges
    such as '0–5 min'.
    For standard journeys, returns 5-minute intervals.
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
        rounded = max(0, round(duration_minutes))
        return DurationRange(min=rounded, max=rounded)

    lower = math.floor(duration_minutes / DISPLAY_INTERVAL_MINUTES) * DISPLAY_INTERVAL_MINUTES
    upper = math.ceil(duration_minutes / DISPLAY_INTERVAL_MINUTES) * DISPLAY_INTERVAL_MINUTES
    if lower == upper:
        upper += DISPLAY_INTERVAL_MINUTES

    return DurationRange(min=lower, max=upper)


def format_duration_unit(minutes: int) -> str:
    """Format an integer number of minutes into human-readable hours and minutes."""
    if minutes < 60:
        return f"{minutes} min"

    hours = minutes // 60
    rem = minutes % 60

    if rem == 0:
        return "1 hour" if hours == 1 else f"{hours} hours"
    if hours == 1:
        return f"1 hour {rem} min"
    return f"{hours} hours {rem} min"


def format_duration_range(range_or_duration: DurationRange | dict | float | int) -> str:
    """Format a DurationRange or numeric duration into a human-readable range string."""
    if isinstance(range_or_duration, dict):
        range_ = DurationRange(**range_or_duration)
    elif isinstance(range_or_duration, (int, float)) and not isinstance(range_or_duration, bool):
        range_ = duration_to_range(float(range_or_duration))
    elif isinstance(range_or_duration, DurationRange):
        range_ = range_or_duration
    else:
        raise ValueError("Expected DurationRange or numeric duration")


    lower = range_.min
    upper = range_.max

    if lower == upper:
        return format_duration_unit(lower)

    if lower < 60 and upper < 60:
        return f"{lower}–{upper} min"

    return f"{format_duration_unit(lower)}–{format_duration_unit(upper)}"
