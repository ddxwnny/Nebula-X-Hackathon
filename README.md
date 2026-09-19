# Door-to-Door Multi-Modal Route Planner

An MVP FastAPI service for public-transit journeys with a walking leg at each end.

## Run locally

In one terminal, start the API:

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

In another terminal, start the UI:

```bash
cd frontend
npm install
npm run dev
```

POST `/api/v1/routes/plan` accepts an address or a lat/lon pair for origin and destination. Configure `ONEMAP_ACCESS_TOKEN` in `.env` before running it. Without OneMap authentication, it returns 503 instead of manufacturing transit legs.

Set `preferences.step_free` to request a step-free route. The response includes an accessibility decision and will only label a route step-free when all walking connections are verified. Add `LTA_DATAMALL_ACCOUNT_KEY` to enable cached LTA lift-maintenance data when mapped lift identifiers are available.

Exit-level routing loads the official LTA MRT-exit GeoJSON dataset from data.gov.sg by default. Set `LTA_STATION_EXITS_GEOJSON_URL` only to override that source. It evaluates walking-network time from each candidate exit, and replaces the origin/destination walking leg with the best exit route. If LTA exit data is unavailable, `recommended_route.exit_routing` reports a station-level fallback instead of claiming an exit-specific route.

```json
{
  "origin": { "address": "NUS Kent Ridge Campus" },
  "destination": { "address": "Raffles Place" }
}
```

Open the URL shown in the terminal (normally http://localhost:5173). The frontend calls http://localhost:8000 by default.

---

## 2. Geospatial / OSM Layer (satisfies 3.2.2 — mandatory)

| Feature | Priority | Notes |
|---|---|---|
| **OSM base map with attribution** | **Must** | "© OpenStreetMap contributors" visible on every map view |
| **Covered walkway overlay** | **Must** | CoveredLinkWay layer, shown on the walking legs |
| **Step-free path layer** | **Must** | Footpaths/ramps vs stairs distinguished, using OSM footway tags + GRND_LEVEL from provided geojson |
| **Station exit markers** | **Must** | TrainStationExit points plotted, not just station polygons |
| **Self-hosted/cached tile strategy** | **Must** | Static extract or free-tier tile provider — never hit 	ile.openstreetmap.org in a loop |
