from functools import lru_cache
import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "covered_linkways.geojson"


class CoveredLinkwayService:
    def __init__(self):
        self._data = self._load()

    @staticmethod
    @lru_cache(maxsize=1)
    def _load():
        if not DATA_FILE.exists():
            return []
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            features = payload.get("features", [])
            for feat in features:
                geom = feat.get("geometry", {})
                coords = geom.get("coordinates", [])
                t = geom.get("type", "")
                if t == "LineString" and coords:
                    lons = [pt[0] for pt in coords]
                    lats = [pt[1] for pt in coords]
                    feat["_bbox"] = (min(lats), max(lats), min(lons), max(lons))
                elif t == "MultiLineString" and coords:
                    lons = [pt[0] for line in coords for pt in line]
                    lats = [pt[1] for line in coords for pt in line]
                    feat["_bbox"] = (min(lats), max(lats), min(lons), max(lons))
                else:
                    feat["_bbox"] = None
            return features
        except Exception:
            return []

    def find_linkways_near_route(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        buffer: float = 0.005,
        limit: int | None = None,
    ) -> list[dict]:
        """Filter linkway features within a bounding box buffer. If limit is None, returns all matches."""
        b_min_lat, b_max_lat = min_lat - buffer, max_lat + buffer
        b_min_lon, b_max_lon = min_lon - buffer, max_lon + buffer

        matches = []
        for feature in self._data:
            bbox = feature.get("_bbox")
            if not bbox:
                continue
            f_min_lat, f_max_lat, f_min_lon, f_max_lon = bbox
            if not (f_max_lat < b_min_lat or f_min_lat > b_max_lat or f_max_lon < b_min_lon or f_min_lon > b_max_lon):
                clean_feat = {k: v for k, v in feature.items() if k != "_bbox"}
                matches.append(clean_feat)
                if limit and len(matches) >= limit:
                    break

        return matches