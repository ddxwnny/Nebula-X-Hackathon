# Door-to-Door Multi-Modal Route Planner

An MVP FastAPI service for public-transit journeys with a walking leg at each end.

## Run locally

In one terminal, start the API:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ONEMAP_ACCESS_TOKEN="your-onemap-access-token"
uvicorn main:app --reload
```

In another terminal, start the UI:

```bash
cd frontend
npm install
npm run dev
```

`POST /api/v1/routes/plan` accepts an `address` or a `lat`/`lon` pair for origin and destination. Configure `ONEMAP_ACCESS_TOKEN` in `.env` before running it. Without OneMap authentication, it returns `503` instead of manufacturing transit legs.

```json
{
  "origin": { "address": "NUS Kent Ridge Campus" },
  "destination": { "address": "Raffles Place" }
}
```

Open the URL shown in the terminal (normally `http://localhost:5173`). The frontend calls `http://localhost:8000` by default.
