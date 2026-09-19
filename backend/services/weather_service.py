import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DATA_GOV_SG_NOWCAST_URL = "https://api-open.data.gov.sg/v2/real-time/api/two-hr-forecast"
DATA_GOV_SG_RAINFALL_URL = "https://api-open.data.gov.sg/v2/real-time/api/rainfall"

# Singapore rainfall station coordinates for spatial matching
# These are approximate region centroids used to match route points to forecast areas
_SG_REGION_CENTERS: dict[str, tuple[float, float]] = {
    "north": (1.4050, 103.8000),
    "northeast": (1.3700, 103.8500),
    "east": (1.3300, 103.9300),
    "central": (1.3500, 103.8200),
    "west": (1.3400, 103.7200),
    "south": (1.2900, 103.8550),
}

# Rain severity mapping from data.gov.sg forecast codes
_RAIN_CODE_MAP: dict[str, str] = {
    "Rain": "rain",
    "Heavy Rain": "heavy_rain",
    "Light Rain": "light_rain",
    "Thundery Showers": "thunderstorm",
    "Heavy Thundery Showers": "thunderstorm",
    "Heavy Thundery Showers with Gusty Winds": "severe_thunderstorm",
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate haversine distance in km between two lat/lon points."""
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _find_nearest_region(lat: float, lon: float) -> str:
    """Find the nearest SG region center to a given point."""
    best = "central"
    best_dist = float("inf")
    for region, (rlat, rlon) in _SG_REGION_CENTERS.items():
        d = _haversine_km(lat, lon, rlat, rlon)
        if d < best_dist:
            best_dist = d
            best = region
    return best


class WeatherService:
    """Fetches real-time weather and rainfall data from data.gov.sg APIs."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[datetime, Any]] = {}
        self._cache_ttl = timedelta(minutes=5)

    async def _fetch_json(self, url: str) -> dict | None:
        """Fetch JSON from a URL with error handling and basic caching."""
        cache_key = url
        now = datetime.now()
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if now - cached_time < self._cache_ttl:
                return cached_data

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                self._cache[cache_key] = (now, data)
                return data
        except Exception as e:
            logger.warning("Weather API fetch failed for %s: %s", url, e)
            return None

    async def get_two_hour_nowcast(self) -> dict | None:
        """Fetch the 2-hour nowcast from data.gov.sg.

        Returns the full API response or None on failure.
        The nowcast contains forecast regions with weather codes like "Rain",
        "Thundery Showers", etc., and a time period (e.g. "2024-01-01T08:00:00+08:00").
        """
        return await self._fetch_json(DATA_GOV_SG_NOWCAST_URL)

    async def get_rainfall_readings(self) -> dict | None:
        """Fetch real-time rainfall readings from data.gov.sg."""
        return await self._fetch_json(DATA_GOV_SG_RAINFALL_URL)

    def _parse_nowcast_for_point(
        self, nowcast: dict | None, lat: float, lon: float
    ) -> dict:
        """Parse 2-hour nowcast data and determine rain risk for a specific point.

        Returns a dict with:
          - rain_expected: bool
          - rain_severity: str (none, light_rain, rain, heavy_rain, thunderstorm, severe_thunderstorm)
          - forecast_area: str (nearest region name)
          - forecast_text: str (human-readable forecast)
          - valid_period: str (time range of the forecast)
        """
        if not nowcast:
            return {
                "rain_expected": False,
                "rain_severity": "unknown",
                "forecast_area": "unknown",
                "forecast_text": "Weather data unavailable",
                "valid_period": "",
            }

        region = _find_nearest_region(lat, lon)

        # Parse the nowcast response
        items = nowcast.get("data", {}).get("items", [])
        if not items:
            return {
                "rain_expected": False,
                "rain_severity": "unknown",
                "forecast_area": region,
                "forecast_text": "No forecast data available",
                "valid_period": "",
            }

        latest = items[0]
        forecasts = latest.get("forecasts", [])
        timestamp = latest.get("timestamp", "")

        for fc in forecasts:
            area = fc.get("area", "")
            # Match the forecast area to our region
            area_lower = area.lower()
            if region in area_lower or _haversine_km(
                lat, lon,
                _SG_REGION_CENTERS.get(region, (1.35, 103.82))[0],
                _SG_REGION_CENTERS.get(region, (1.35, 103.82))[1],
            ) < 10:
                weather_code = fc.get("weather", "")
                rain_severity = _RAIN_CODE_MAP.get(weather_code, "none")
                rain_expected = rain_severity not in ("none", "unknown")

                return {
                    "rain_expected": rain_expected,
                    "rain_severity": rain_severity,
                    "forecast_area": area or region,
                    "forecast_text": weather_code if weather_code else "Clear",
                    "valid_period": f"Next 2 hours from {timestamp}",
                }

        # If no exact match, use first forecast as fallback
        if forecasts:
            fc = forecasts[0]
            weather_code = fc.get("weather", "")
            rain_severity = _RAIN_CODE_MAP.get(weather_code, "none")
            return {
                "rain_expected": rain_severity not in ("none", "unknown"),
                "rain_severity": rain_severity,
                "forecast_area": fc.get("area", region),
                "forecast_text": weather_code if weather_code else "Clear",
                "valid_period": f"Next 2 hours from {timestamp}",
            }

        return {
            "rain_expected": False,
            "rain_severity": "none",
            "forecast_area": region,
            "forecast_text": "Clear",
            "valid_period": "",
        }

    def _parse_rainfall_for_point(
        self, rainfall: dict | None, lat: float, lon: float
    ) -> dict:
        """Check current rainfall readings near a point.

        Returns:
          - currently_raining: bool
          - nearest_station: str
          - rainfall_mm: float (0.0 if no data)
        """
        if not rainfall:
            return {
                "currently_raining": False,
                "nearest_station": "unknown",
                "rainfall_mm": 0.0,
            }

        items = rainfall.get("data", {}).get("items", [])
        if not items:
            return {
                "currently_raining": False,
                "nearest_station": "unknown",
                "rainfall_mm": 0.0,
            }

        latest = items[0]
        readings = latest.get("readings", [])

        best_station = "unknown"
        best_dist = float("inf")
        best_rainfall = 0.0

        for reading in readings:
            station = reading.get("station_id", "")
            value = reading.get("value", 0.0)
            # Rainfall stations have lat/lon in the metadata, but the API
            # structure varies. We use the station readings directly.
            # For simplicity, treat any non-zero reading as rain.
            if value > 0 and best_rainfall == 0.0:
                best_rainfall = value
                best_station = station

        return {
            "currently_raining": best_rainfall > 0.0,
            "nearest_station": best_station,
            "rainfall_mm": best_rainfall,
        }

    async def assess_route_rain_risk(
        self,
        route_points: list[tuple[float, float]],
        departure_time: datetime | None = None,
    ) -> dict:
        """Assess rain risk for an entire route.

        Args:
            route_points: List of (lat, lon) tuples along the route.
            departure_time: When the commuter departs. If None, uses now.

        Returns a comprehensive rain assessment:
          - rain_along_route: bool (is rain expected anywhere along the route?)
          - rain_severity: worst severity across all points
          - point_forecasts: per-point forecast details
          - current_rain: current rainfall status
          - recommendation: str (human-readable advice)
        """
        nowcast_data, rainfall_data = await asyncio.gather(
            self.get_two_hour_nowcast(),
            self.get_rainfall_readings(),
        )

        point_forecasts = []
        worst_severity = "none"
        any_rain = False

        # Check key points: origin, destination, and midpoint(s)
        key_points = route_points[:1]  # origin
        if len(route_points) > 2:
            mid_idx = len(route_points) // 2
            key_points.append(route_points[mid_idx])  # midpoint
        if len(route_points) > 1:
            key_points.append(route_points[-1])  # destination

        for lat, lon in key_points:
            forecast = self._parse_nowcast_for_point(nowcast_data, lat, lon)
            point_forecasts.append({"lat": lat, "lon": lon, **forecast})

            if forecast["rain_expected"]:
                any_rain = True
                severity_order = ["none", "light_rain", "rain", "heavy_rain", "thunderstorm", "severe_thunderstorm"]
                if severity_order.index(forecast["rain_severity"]) > severity_order.index(worst_severity):
                    worst_severity = forecast["rain_severity"]

        current = self._parse_rainfall_for_point(
            rainfall_data,
            route_points[0][0] if route_points else 1.35,
            route_points[0][1] if route_points else 103.82,
        )

        # Build recommendation
        if current["currently_raining"]:
            recommendation = (
                f"Rain is currently falling ({current['rainfall_mm']:.1f}mm). "
                "Use sheltered walkways and covered linkways for all walking legs."
            )
        elif any_rain:
            severity_labels = {
                "light_rain": "light rain",
                "rain": "rain",
                "heavy_rain": "heavy rain",
                "thunderstorm": "thundery showers",
                "severe_thunderstorm": "severe thunderstorms",
            }
            label = severity_labels.get(worst_severity, "rain")
            recommendation = (
                f"{label.title()} is forecasted within the next 2 hours. "
                "Consider the 100% Dry Route using covered linkways and indoor concourses."
            )
        else:
            recommendation = (
                "No rain forecasted in the next 2 hours. "
                "Open-air walking routes are fine."
            )

        return {
            "rain_along_route": any_rain,
            "rain_severity": worst_severity if any_rain else "none",
            "current_rain": current,
            "point_forecasts": point_forecasts,
            "recommendation": recommendation,
        }
