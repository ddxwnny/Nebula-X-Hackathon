"""Station ground-level service utilizing AmendmenttoMP2014RailStation.geojson.

Provides spatial querying of the 208 official station footprint polygons and
concourse transition level analysis (UNDERGROUND vs ABOVEGROUND).
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any


class StationGroundLevelService:
    _instance: StationGroundLevelService | None = None
    _features: list[dict[str, Any]] = []

    def __init__(self, geojson_path: Path | str | None = None):
        if not self._features:
            self._load_data(geojson_path)

    def _load_data(self, geojson_path: Path | str | None = None) -> None:
        candidates = [
            Path(geojson_path) if geojson_path else None,
            Path(__file__).resolve().parent.parent / "data" / "AmendmenttoMP2014RailStation.geojson",
            Path(__file__).resolve().parent.parent / "PS2" / "data" / "AmendmenttoMP2014RailStation.geojson",
            Path(__file__).resolve().parent.parent.parent / "PS2" / "data" / "AmendmenttoMP2014RailStation.geojson",
        ]
        target_path = next((p for p in candidates if p and p.exists()), None)
        if not target_path:
            return

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                features = data.get("features", [])
                for feat in features:
                    geom = feat.get("geometry", {})
                    props = feat.get("properties", {})
                    # Calculate approximate centroid and bounding box for fast indexing
                    if geom.get("type") == "Polygon":
                        coords = geom.get("coordinates", [[]])[0]
                        if coords:
                            lons = [c[0] for c in coords]
                            lats = [c[1] for c in coords]
                            props["_bbox"] = (min(lats), max(lats), min(lons), max(lons))
                            props["_centroid"] = (sum(lats) / len(lats), sum(lons) / len(lons))
                    feat["properties"] = props
                StationGroundLevelService._features = features
        except Exception:
            StationGroundLevelService._features = []

    @property
    def features(self) -> list[dict[str, Any]]:
        return self._features

    def get_station_by_name(self, station_name: str) -> dict[str, Any] | None:
        """Find station footprint by station name with normalisation."""
        if not station_name:
            return None
        norm_target = self._normalise_name(station_name)
        for feat in self._features:
            name = feat.get("properties", {}).get("NAME", "")
            norm_name = self._normalise_name(name)
            if norm_target == norm_name or norm_target in norm_name or norm_name in norm_target:
                return feat
        return None

    def get_station_level(self, station_name: str) -> str:
        """Return 'UNDERGROUND', 'ABOVEGROUND', or 'UNKNOWN'."""
        feat = self.get_station_by_name(station_name)
        if feat:
            return feat.get("properties", {}).get("GRND_LEVEL", "UNKNOWN")
        return "UNKNOWN"

    def concourse_transition_info(self, station_name: str) -> dict[str, Any]:
        """Provides concourse vertical transition guidance for wheelchair commuters."""
        level = self.get_station_level(station_name)
        feat = self.get_station_by_name(station_name)
        stn_type = feat.get("properties", {}).get("TYPE", "MRT") if feat else "MRT"
        canonical_name = feat.get("properties", {}).get("NAME", station_name) if feat else station_name

        if level == "UNDERGROUND":
            return {
                "station_name": canonical_name,
                "ground_level": "UNDERGROUND",
                "station_type": stn_type,
                "requires_elevator": True,
                "transition_type": "subsurface_concourse",
                "summary": "Underground concourse and platform",
                "guidance": "Street ⬇️ Concourse ⬇️ Platform transition requires dual lift/elevator hops. Avoid stairs/escalators.",
            }
        elif level == "ABOVEGROUND":
            return {
                "station_name": canonical_name,
                "ground_level": "ABOVEGROUND",
                "station_type": stn_type,
                "requires_elevator": True,
                "transition_type": "elevated_concourse",
                "summary": "Elevated / ground-level concourse and platform",
                "guidance": "Street ⬆️ Concourse ⬆️ Platform transition via station lift or accessibility ramp.",
            }
        return {
            "station_name": canonical_name,
            "ground_level": "UNKNOWN",
            "station_type": stn_type,
            "requires_elevator": False,
            "transition_type": "standard",
            "summary": "Standard station concourse",
            "guidance": "Follow station barrier-free signs for lift and ramp access.",
        }

    def find_station_for_point(self, lat: float, lon: float, buffer_degrees: float = 0.003) -> dict[str, Any] | None:
        """Find station whose polygon or buffer contains the specified coordinate."""
        for feat in self._features:
            props = feat.get("properties", {})
            bbox = props.get("_bbox")
            if not bbox:
                continue
            min_lat, max_lat, min_lon, max_lon = bbox
            if (min_lat - buffer_degrees) <= lat <= (max_lat + buffer_degrees) and (min_lon - buffer_degrees) <= lon <= (max_lon + buffer_degrees):
                return feat
        return None

    def get_polygons_in_bounds(self, min_lat: float, max_lat: float, min_lon: float, max_lon: float, limit: int | None = None) -> list[dict[str, Any]]:
        """Return station polygons intersecting the given bounding box."""
        matched = []
        for feat in self._features:
            bbox = feat.get("properties", {}).get("_bbox")
            if not bbox:
                continue
            f_min_lat, f_max_lat, f_min_lon, f_max_lon = bbox
            # Check bounding box overlap
            if not (f_max_lat < min_lat or f_min_lat > max_lat or f_max_lon < min_lon or f_min_lon > max_lon):
                matched.append(feat)
                if limit and len(matched) >= limit:
                    break
        return matched

    @staticmethod
    def _normalise_name(name: str | None) -> str:
        if not name:
            return ""
        return (
            str(name).upper()
            .replace(" MRT STATION", "")
            .replace(" LRT STATION", "")
            .replace(" STATION", "")
            .replace(" STN", "")
            .replace(" MRT", "")
            .replace(" LRT", "")
            .strip()
        )
