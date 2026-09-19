# Door-to-Door Multi-Modal Route Planner

An MVP FastAPI service for public-transit journeys with a walking leg at each end.

## Run locally

In one terminal, start the API:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

In another terminal, start the UI:

```bash
cd frontend
npm install
npm run dev
```

## Run with Docker

Run the entire application (FastAPI backend + Vite/React frontend) with Docker Compose:

1. Ensure `.env` is configured with your credentials:
   ```bash
   cp .env.example .env
   # Add your ONEMAP_ACCESS_TOKEN and optional LTA_DATAMALL_ACCOUNT_KEY
   ```

2. Build and start the containers:
   ```bash
   docker compose up --build
   ```

3. Open `http://localhost:5173` in your browser. The backend API is available at `http://localhost:8000` (docs at `http://localhost:8000/docs`).

`POST /api/v1/routes/plan` accepts an `address` or a `lat`/`lon` pair for origin and destination. Configure `ONEMAP_ACCESS_TOKEN` in `.env` before running it. Without OneMap authentication, it returns `503` instead of manufacturing transit legs.

Set `preferences.step_free` to request a step-free route. The response includes
an accessibility decision and will only label a route step-free when all walking
connections are verified. Add `LTA_DATAMALL_ACCOUNT_KEY` to enable cached LTA
lift-maintenance data when mapped lift identifiers are available.

Exit-level routing loads the official LTA MRT-exit GeoJSON dataset from data.gov.sg
by default. Set `LTA_STATION_EXITS_GEOJSON_URL` only to override that source. It evaluates walking-network time from each candidate
exit, and replaces the origin/destination walking leg with the best exit route.
If LTA exit data is unavailable, `recommended_route.exit_routing` reports a
station-level fallback instead of claiming an exit-specific route.

```json
{
  "origin": { "address": "NUS Kent Ridge Campus" },
  "destination": { "address": "Raffles Place" }
}
```

Open the URL shown in the terminal (normally `http://localhost:5173`). The frontend calls `http://localhost:8000` by default.

## Live Disruption-Aware Re-Routing

Active journeys can monitor LTA train service alerts (`TrainServiceAlerts`), detect disruptions affecting their remaining transit segments, and recalculate alternative routes from the commuter's current position:

* `POST /api/v1/journeys`: Convert a planned route into an active journey with initial remaining legs and current position.
* `GET /api/v1/journeys/{journey_id}/status`: Check if the active journey is affected by disruptions (`active`, `unaffected`, `reroute_required`, `rerouted`, `completed`).
* `POST /api/v1/journeys/{journey_id}/reroute`: Recalculate the remaining journey from `current_position`, incorporating LTA shuttle/bus mitigations and returning a duration comparison against the original route.
