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

## Frontend experience

The website uses a phone layout at every screen size: full-width on phones and
centred at a maximum width of 430px on desktop. The initial planner fits one
viewport; the map is loaded only after Find route succeeds. Edit trip returns to
the saved form, while long itineraries scroll inside the results panel. It includes Plan and Alerts, address suggestions, optional
device location, scheduled departure in Singapore time, step-free preferences,
MRT-coloured map segments, and a readable route itinerary. Drag the bottom sheet
to see more map or details; it snaps to 25%, 60%, and 85% of the available area.
Tap its handle to cycle positions, or focus it and use arrow keys, Home, or End.
Navigation guidance and journey-progress controls are not offered.
Train service and planned-route alerts refresh every 30
seconds while the page is open. Alternatives are previewed before the commuter
chooses **Use alternative**; their accessibility and station exits remain unverified.

Weather and general bus operational feeds are not yet connected. The interface
labels them unavailable, and does not claim live arrivals or verified shelter.
Routing still requires the backend and provider configuration described above.

Frontend checks (from `frontend`):

```bash
npm run build
npm run test:e2e
```

Browser tests use installed Google Chrome and mocked API responses, with desktop
and mobile viewports. If Chrome is absent, install it or run
`npx playwright install chrome`. The test runner starts Vite automatically when
needed. See [the approved UX proposal](docs/frontend-ux-proposal.md) for design
decisions and remaining data integrations.

## Live Disruption-Aware Re-Routing

Active journeys can monitor LTA train service alerts (`TrainServiceAlerts`), detect disruptions affecting their remaining transit segments, and recalculate alternative routes from the commuter's current position:

* `POST /api/v1/journeys`: Convert a planned route into an active journey with initial remaining legs and current position.
* `GET /api/v1/journeys/{journey_id}/status`: Check if the active journey is affected by disruptions (`active`, `unaffected`, `reroute_required`, `rerouted`, `completed`).
* `POST /api/v1/journeys/{journey_id}/reroute`: Recalculate the remaining journey from `current_position`, incorporating LTA shuttle/bus mitigations and returning a duration comparison against the original route.

See [the frontend/backend feature audit](docs/frontend-backend-feature-audit.md)
for supported integrations, browser-only behaviour, and missing data feeds.
