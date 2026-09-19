# sMaRT Move 🚇♿

**Accessible, Disruption-Resilient Multimodal Transit Journey Planner for Singapore**

sMaRT Move is a multimodal Singapore transit routing web application that combines door-to-door transit planning, verified step-free accessibility guidance, station exit-level routing, and real-time LTA train service disruption monitoring.

---

## 1. Prerequisites

Before running the application, ensure the following software is installed on your machine:

| Requirement | Minimum Version | Notes |
| :--- | :--- | :--- |
| **Python** | `3.11+` | Tested on Python 3.11, 3.12, and 3.13 |
| **Node.js** | `20.19+` or `22.12+` | Includes `npm` package manager |
| **pip** | `23.0+` | Standard Python package installer |
| **Git** | `2.30+` | Version control |
| **(Optional) Docker** | `24.0+` | Docker Engine with Docker Compose v2 for containerized execution |

---

## 2. Configuration & API Keys

The application requires a `.env` file at the project root for API credentials:

```bash
cp .env.example .env
```

Open `.env` and configure the following variables:

| Variable | Required? | Purpose & Where to Obtain |
| :--- | :--- | :--- |
| `ONEMAP_ACCESS_TOKEN` | **Yes (for routing)** | **OneMap API Access Token**: Powers geocoding and public transit routing. Register a free account and generate an API key from the [OneMap API Portal](https://www.onemap.gov.sg/apidocs/). |
| `ONEMAP_EMAIL` & `ONEMAP_PASSWORD` | Optional | Alternative to `ONEMAP_ACCESS_TOKEN`: The backend can automatically fetch and refresh OneMap tokens using your OneMap account credentials. |
| `LTA_DATAMALL_ACCOUNT_KEY` | Recommended | **LTA DataMall API Key**: Powers live train service disruption alerts and real-time bus arrivals. Request a free API key at [LTA DataMall](https://datamall.lta.gov.sg/content/datamall/en/request-for-api.html). *(If omitted, the app runs normally with fallback alert messaging).* |
| `LTA_STATION_EXITS_GEOJSON_URL` | Optional | URL for official LTA station exits. Pre-configured by default to the official [data.gov.sg dataset](https://api-open.data.gov.sg/v1/public/api/datasets/d_b39d3a0871985372d7e1637193335da5/poll-download). |

---

## 3. Install and Run

Choose either **Option A (Docker Compose - Recommended)** or **Option B (Manual Local Setup)**.

### Option A: Quickstart with Docker Compose (Single Command)

1. Clone and prepare configuration:
   ```bash
   cp .env.example .env
   # Open .env and add your ONEMAP_ACCESS_TOKEN
   ```

2. Build and start containers:
   ```bash
   docker compose up --build
   ```

3. Open your browser at **`http://localhost:5173`** (or `http://localhost:80`).
   - The FastAPI backend will be available at `http://localhost:8000` (interactive Swagger API docs at `http://localhost:8000/docs`).

---

### Option B: Manual Local Setup (Two Terminals)

#### Terminal 1: Backend API (FastAPI)

```bash
# 1. From the repository root, copy the environment template
cp .env.example .env
# Edit .env to supply your ONEMAP_ACCESS_TOKEN

# 2. Enter the backend directory and set up the Python virtual environment
cd backend
python3 -m venv .venv
source .venv/bin/activate

# 3. Install backend dependencies
pip install -r requirements.txt

# 4. Start the backend server
uvicorn main:app --reload --port 8000
```
*The backend will be running at `http://localhost:8000`.*

#### Terminal 2: Frontend Web Application (React + Vite)

```bash
# 1. Enter the frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Start Vite development server
npm run dev
```
*The web UI will be live at `http://localhost:5173`.*

---

## 4. What to Click: The Recommended Journey to Try First

Open **`http://localhost:5173`** in your web browser.

### The First Journey:
1. **Origin**: Type or select `Ang Mo Kio MRT Station` (or `NUS Kent Ridge Campus`).
2. **Destination**: Type or select `Singapore General Hospital` (or `Raffles Place`).
3. **Preferences**: Check the **"Step-free route"** toggle (*Avoid stairs. Prefer lifts and ramps*).
4. **Schedule**: Leave default date/time (Singapore local time) or pick a scheduled departure.
5. Click **"Find route"**.

### What to Observe & Verify:
- **Interactive Route Map**: Leaflet map immediately mounts and frames the route with color-coded transit legs (walking paths, official MRT line colors such as NSL red and EWL green, bus connections, origin green pin, destination red pin, and station entrance/exit pins).
- **Step-Free Accessibility Assessment**: A clear status card explains the step-free verification result (e.g. lift/ramp availability, verified barrier-free walking connections, or warnings if step-free access is unverified).
- **Station Entrance & Exit Guide**: Expand the **"Station entrances & exits"** accordion to see the specific station exits selected based on walking network time (e.g., *Exit A* vs *Exit B*).
- **Responsive Bottom Sheet**:
  - Drag the bottom sheet handle up or down to reveal more map or more itinerary details.
  - Alternatively, click/tap the sheet handle (or use keyboard arrow keys) to snap across **25%**, **60%**, and **85%** view heights.
- **Service Disruption Alerts**:
  - Click **"Alerts"** in the bottom navigation bar.
  - Review live LTA train service disruption alerts, affected stations, and bridging bus/shuttle mitigations.
  - Filter alerts between **"All lines"** and **"My journey"** to see disruptions that intersect your active itinerary.

---

## 5. Running Automated Tests

### Frontend End-to-End Tests (Playwright)
The frontend includes 18 automated Playwright tests verifying the mobile-first UX, bottom-sheet drag interactions, keyboard navigation, alert cards, disruption banners, and route alternatives on desktop and mobile viewports:

```bash
cd frontend
npm run test:e2e
```

### Frontend Production Build Verification
```bash
cd frontend
npm run build
```

### Backend Unit & Integration Tests
Run the test suite verifying routing calculations, duration ranges, LTA caching, exit selection, and disruption monitoring:

```bash
cd backend
source .venv/bin/activate
PYTHONPATH=. python3 -m unittest discover -s tests
```

---

## 6. Architecture & Implementation Highlights

- **Frontend**: Mobile-first responsive web application built with React 19, TypeScript, and Vite. Designed around a clean thumb-zone bottom-sheet layout suited for one-handed commuter use and wheelchair navigation. Leaflet with OpenStreetMap tiles provides high-contrast geospatial route visualization.
- **Backend**: High-performance FastAPI service interfacing with OneMap Routing APIs, LTA DataMall v2/v3, and official Singapore Government Open Data GeoJSON datasets.
- **Accessibility Engine**: Real-time evaluation of barrier-free connectivity, including lift maintenance status, ramps, and stair avoidance.
- **Disruption Resilience**: Live polling and caching of LTA train service alerts with automatic journey status matching and alternative route comparison.
