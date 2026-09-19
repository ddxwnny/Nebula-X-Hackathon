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
    "Showers": "rain",
    "Moderate Rain": "rain",
    "Heavy Showers": "heavy_rain",
    "Light Showers": "light_rain",
    "Partly Cloudy": "none",
    "Cloudy": "none",
    "Fair": "none",
    "Fair (Day)": "none",
    "Fair (Night)": "none",
}

_SEVERITY_ORDER = ["none", "light_rain", "rain", "heavy_rain", "thunderstorm", "severe_thunderstorm"]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate haversine distance in km between two lat/lon points."""
    import math
    if lat1 == lat2 and lon1 == lon2:
        return 0.0
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
        except httpx.HTTPStatusError as e:
            logger.warning("Weather API HTTP error for %s: %s", url, e)
            return None
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError) as e:
            logger.warning("Weather API request failed for %s: %s", url, e)
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

    def _map_rain_severity(self, text: str) -> tuple[bool, str]:
        """Map a forecast text string to (is_rain, severity_code)."""
        if not text:
            return False, "none"
        mapped = _RAIN_CODE_MAP.get(text)
        if mapped:
            return mapped not in ("none", "unknown"), mapped
        
        low = text.lower()
        if "thunder" in low:
            return True, "thunderstorm"
        if "heavy" in low and ("rain" in low or "shower" in low):
            return True, "heavy_rain"
        if "light" in low or "passing" in low:
            return True, "light_rain"
        if "rain" in low or "shower" in low:
            return True, "rain"
        return False, "none"

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

        data = nowcast.get("data", {})
        area_metadata = data.get("area_metadata", [])
        items = data.get("items", [])
        if not items:
            region = _find_nearest_region(lat, lon)
            return {
                "rain_expected": False,
                "rain_severity": "unknown",
                "forecast_area": region,
                "forecast_text": "No forecast data available",
                "valid_period": "",
            }

        latest = items[0]
        forecasts_list = latest.get("forecasts", [])
        valid_period_obj = latest.get("valid_period", {})
        valid_period_str = valid_period_obj.get("text", "") if isinstance(valid_period_obj, dict) else ""
        if not valid_period_str:
            timestamp = latest.get("timestamp", "")
            valid_period_str = f"Next 2 hours from {timestamp}" if timestamp else "Next 2 hours"

        # Build dictionary of area name -> forecast text
        # v2 API uses "forecast", older API used "weather"
        forecast_by_area: dict[str, str] = {}
        for fc in forecasts_list:
            area_name = fc.get("area", "")
            fc_text = fc.get("forecast") or fc.get("weather", "")
            if area_name:
                forecast_by_area[area_name] = fc_text

        best_area = ""
        best_weather = ""

        # Use area_metadata if available for accurate spatial matching
        if area_metadata:
            min_dist = float("inf")
            for entry in area_metadata:
                name = entry.get("name", "")
                loc = entry.get("label_location", {})
                alat = loc.get("latitude")
                alon = loc.get("longitude")
                if alat is not None and alon is not None:
                    d = _haversine_km(lat, lon, alat, alon)
                    if d < min_dist:
                        min_dist = d
                        best_area = name
                        best_weather = forecast_by_area.get(name, "")

        # Fallback to region matching if area_metadata not present
        if not best_weather:
            region = _find_nearest_region(lat, lon)
            best_area = region
            for area_name, fc_text in forecast_by_area.items():
                if region in area_name.lower():
                    best_area = area_name
                    best_weather = fc_text
                    break
            if not best_weather and forecasts_list:
                first_fc = forecasts_list[0]
                best_area = first_fc.get("area", region)
                best_weather = first_fc.get("forecast") or first_fc.get("weather", "")

        rain_expected, rain_severity = self._map_rain_severity(best_weather)

        return {
            "rain_expected": rain_expected,
            "rain_severity": rain_severity,
            "forecast_area": best_area or "Singapore",
            "forecast_text": best_weather if best_weather else "Fair",
            "valid_period": valid_period_str,
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

        data = rainfall.get("data", {})
        stations = data.get("stations", [])
        readings_containers = data.get("readings", [])

        # Map station_id -> rainfall_mm
        station_readings: dict[str, float] = {}

        # Format 1: data.gov.sg v2: readings is [{"timestamp": ..., "data": [{"stationId": ..., "value": ...}]}]
        if readings_containers and isinstance(readings_containers, list):
            first_entry = readings_containers[0]
            readings_list = first_entry.get("data", []) if isinstance(first_entry, dict) else []
            for item in readings_list:
                stn_id = item.get("stationId") or item.get("station_id", "")
                val = float(item.get("value", 0.0))
                if stn_id:
                    station_readings[stn_id] = val

        # Format 2 fallback: older schema where data.items[0].readings exists
        if not station_readings and "items" in data:
            items = data.get("items", [])
            if items:
                for item in items[0].get("readings", []):
                    stn_id = item.get("stationId") or item.get("station_id", "")
                    val = float(item.get("value", 0.0))
                    if stn_id:
                        station_readings[stn_id] = val

        if not stations:
            # If no station metadata, check if any reading > 0
            has_rain = any(v > 0 for v in station_readings.values())
            return {
                "currently_raining": has_rain,
                "nearest_station": "generic",
                "rainfall_mm": max(station_readings.values()) if station_readings else 0.0,
            }

        # Find nearest station to (lat, lon)
        nearest_stn_name = "unknown"
        nearest_stn_id = ""
        min_dist = float("inf")
        nearby_rain_mm = 0.0

        for stn in stations:
            s_id = stn.get("id") or stn.get("deviceId", "")
            s_name = stn.get("name", s_id)
            loc = stn.get("location", {})
            slat = loc.get("latitude")
            slon = loc.get("longitude")
            if slat is not None and slon is not None:
                dist = _haversine_km(lat, lon, slat, slon)
                if dist < min_dist:
                    min_dist = dist
                    nearest_stn_name = s_name
                    nearest_stn_id = s_id
                
                # Check for active rain within 5km radius
                if dist <= 5.0:
                    val = station_readings.get(s_id, 0.0)
                    if val > nearby_rain_mm:
                        nearby_rain_mm = val

        stn_val = station_readings.get(nearest_stn_id, 0.0)
        final_rainfall = max(stn_val, nearby_rain_mm)

        return {
            "currently_raining": final_rainfall > 0.0,
            "nearest_station": nearest_stn_name,
            "rainfall_mm": final_rainfall,
        }

    async def assess_route_rain_risk(
        self,
        route_points: list[tuple[float, float]],
        departure_time: datetime | None = None,
        simulate_rain: bool = False,
        dry_route: bool = False,
    ) -> dict:
        """Assess rain risk for an entire route.

        Args:
            route_points: List of (lat, lon) tuples along the route.
            departure_time: When the commuter departs. If None, uses now.
            simulate_rain: Demo flag to simulate active rain along the route.
            dry_route: User preference requesting 100% weather-protected route.

        Returns a comprehensive rain assessment:
          - rain_along_route: bool (is rain expected anywhere along the route?)
          - rain_severity: worst severity across all points
          - point_forecasts: per-point forecast details
          - current_rain: current rainfall status
          - recommendation: str (human-readable advice)
        """
        if simulate_rain:
            simulated_points = [
                {
                    "lat": pt[0],
                    "lon": pt[1],
                    "rain_expected": True,
                    "rain_severity": "thunderstorm",
                    "forecast_area": "Simulated Storm Zone",
                    "forecast_text": "Thundery Showers (Simulated)",
                    "valid_period": "Next 2 hours",
                }
                for pt in (route_points[:3] if route_points else [(1.35, 103.82)])
            ]
            current_rain = {
                "currently_raining": True,
                "nearest_station": "Demo Weather Station (Simulated)",
                "rainfall_mm": 5.4,
            }
            if dry_route:
                recommendation = (
                    "✓ 100% Dry Route Activated: Heavy rain intercepted! Route strictly routes "
                    "through covered linkways, underpasses, and indoor concourses. Zero open-air exposure."
                )
            else:
                recommendation = (
                    "Thundery showers detected along the route. "
                    "Enable 'Dry Route Mode' to navigate exclusively through covered linkways and concourses."
                )
            return {
                "rain_along_route": True,
                "rain_severity": "thunderstorm",
                "current_rain": current_rain,
                "point_forecasts": simulated_points,
                "recommendation": recommendation,
            }

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
                sev = forecast["rain_severity"]
                sev_idx = _SEVERITY_ORDER.index(sev) if sev in _SEVERITY_ORDER else 0
                worst_idx = _SEVERITY_ORDER.index(worst_severity) if worst_severity in _SEVERITY_ORDER else 0
                if sev_idx > worst_idx:
                    worst_severity = forecast["rain_severity"]

        current = self._parse_rainfall_for_point(
            rainfall_data,
            route_points[0][0] if route_points else 1.35,
            route_points[0][1] if route_points else 103.82,
        )

        # If current rainfall is detected, ensure any_rain is true
        if current["currently_raining"]:
            any_rain = True
            if worst_severity == "none":
                worst_severity = "rain"

        # Build recommendation
        if dry_route:
            if any_rain or current["currently_raining"]:
                recommendation = (
                    f"✓ 100% Dry Route Activated: Rain detected ({current['rainfall_mm']:.1f}mm). "
                    "Navigating strictly via covered linkways, MRT concourses, and sheltered paths."
                )
            else:
                recommendation = (
                    "✓ 100% Dry Route Mode Active: Sheltered linkways and covered station concourses "
                    "are prioritized for continuous weather protection."
                )
        elif current["currently_raining"]:
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
                "Consider activating 100% Dry Route to utilize covered linkways and indoor concourses."
            )
        else:
            recommendation = (
                "No rain forecasted in the next 2 hours. "
                "Open-air walking routes are fine."
            )

        return {
            "rain_along_route": any_rain or (dry_route and (any_rain or current["currently_raining"])),
            "rain_severity": worst_severity if any_rain else "none",
            "current_rain": current,
            "point_forecasts": point_forecasts,
            "recommendation": recommendation,
        }
