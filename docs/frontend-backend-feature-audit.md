# Frontend/backend feature audit

Scope: repository implementation, not a live-provider availability test. Backend support depends on credentials and upstream data. The frontend branch contains no backend changes.

## Visible features without corresponding backend data

| Feature | Current behaviour | Missing support |
| --- | --- | --- |
| Weather updates | Planner and Alerts show unavailable | Weather feed, location/time forecasts, route exposure or shelter data, weather-aware ranking |
| General bus operating conditions | Alerts shows unavailable | General bus incident/delay and live-arrival endpoints. Bus route legs and LTA bus mitigations for train incidents are supported separately. |
| Arrival time | Browser adds returned duration to selected departure time; labelled estimated | No live vehicle ETA or predicted arrival timestamp in route response |
| Alternative accessibility and exits | Explicitly labelled unverified | Reroute response does not include a fresh step-free assessment or exit-routing metadata |

## Removed unsupported feature

Start journey, Complete step, Finish journey, and End guidance were local UI state. They have been removed. The existing journey APIs register routes, monitor train disruptions, and reroute; they do not expose position/progress updates or turn-by-turn navigation. Route details now show the returned itinerary without pretending to track progress.

The app still uses journey registration internally to check the planned route. Replanning starts from its registered origin; it does not automatically know where a commuter has travelled. Use Edit trip and Use my location to explicitly replan from a new location.

## Browser features that do not require backend endpoints

| Feature | Implementation |
| --- | --- |
| Use my location | Browser geolocation permission and coordinates, then coordinates are sent to the route API |
| Map display | Leaflet with OpenStreetMap tiles; route geometry comes from the backend |
| Draggable bottom sheet, tabs, swap, filters, announcement rotation | Local interface behaviour |
| Walking total, transfer count, line badges | Derived from returned route legs; transfer count is transit-leg count minus one |
| Edit trip / return to route / compare original | In-memory browser state; not saved to an account or persisted across reloads |
| Offline notice | Browser connectivity state; current in-memory itinerary remains visible, but no offline map cache or persistent offline journey storage |
| My journey alert filtering | Network cards match lines locally; the journey status API checks the affected route segments |

## Backend-backed features

- Address search: `GET /api/v1/locations/search`.
- Public-transit planning, departure date/time, duration, walking/bus/MRT legs and geometry: `POST /api/v1/routes/plan`.
- Route-specific step-free verification, lift/ramp status when available, and station-exit selection: included in the planning response. There is no separate network-wide accessibility alerts endpoint exposed to this UI.
- Train disruptions, messages, timestamps, data freshness and bus/shuttle mitigations: `GET /api/v1/disruptions/status`.
- Planned-route registration and disruption matching: `POST /api/v1/journeys` and `GET /api/v1/journeys/{id}/status`.
- Alternative route and duration comparison: `POST /api/v1/journeys/{id}/reroute`. Since that endpoint mutates a journey, the frontend uses a separate preview registration and displays it only after Use alternative.

## Not currently offered

Live bus/train countdowns, platform/headsign details, intermediate-stop lists, fares, saved trips/accounts, push notifications, automatic GPS navigation, and verified sheltered-route comparisons are not implemented in the frontend. Route-leg responses do not expose structured fields for several of these details.

Sources inspected: `backend/api/routes.py`, `backend/models/requests.py`, `backend/models/responses.py`, `backend/models/journeys.py`, `backend/models/disruptions.py`, `backend/services/routing_service.py`, `backend/services/journey_service.py`, and `backend/services/accessibility_service.py`.
