# ICE-NAV AI

**SIH26059 — Ministry of Earth Sciences**  
AI-Enabled Antarctic Sea-Ice, Iceberg Trajectory, and Navigation Decision Support System

## Current milestone

Milestone 1 establishes one complete offline data flow from a committed deterministic synthetic Antarctic scenario through FastAPI and REST to an interactive React-Leaflet map.

Current Milestone 1 uses a deterministic synthetic Antarctic environment. Routing, risk scoring, forecasting and machine learning are not implemented yet.

## What the demo shows

- A bounded prototype corridor from 69.5°S to 66.5°S and 71°E to 79°E
- A research vessel and the Bharati-approach destination
- Eight iceberg markers with schematic safety-buffer rings
- A 30 × 30 grid of normalized sea-ice concentration
- Synthetic, hand-authored land / non-navigable areas
- Backend health, scenario, data source, forecast hour, and grid status

No external map tiles, environmental APIs, databases, or internet connection are required at runtime. Internet access is only needed once to install Python and npm dependencies.

## Architecture

```text
backend/data/demo_scenario.json
        ↓
FastAPI  GET /environment/current
        ↓
frontend/src/services/api.js
        ↓
Dashboard.jsx (network/loading/error state)
        ↓
AntarcticMap.jsx + StatusBar.jsx (presentation)
```

The map uses React-Leaflet with a tile-free `CRS.Simple` canvas and a local longitude scale based on the corridor midpoint latitude. This avoids presenting Web Mercator tiles as a reliable Antarctic navigation chart. It is still only a local visualization approximation; a production Antarctic implementation should use a validated polar projection such as `EPSG:3031`.

## Directory structure

```text
icenav-ai/
├── backend/
│   ├── config/weights.yaml
│   ├── data/generate_scenario.py
│   ├── data/demo_scenario.json
│   ├── engine/geo.py
│   ├── engine/grid.py
│   ├── main.py
│   └── requirements.txt
├── docs/data-contract.md
├── frontend/
│   ├── src/components/AntarcticMap.jsx
│   ├── src/components/StatusBar.jsx
│   ├── src/pages/Dashboard.jsx
│   ├── src/services/api.js
│   ├── src/App.jsx
│   ├── src/main.jsx
│   ├── package.json
│   └── vite.config.js
├── tests/
├── .gitignore
├── LICENSE
└── README.md
```

## Requirements

- Python 3.9 or later
- Node.js 18 or later and npm
- PowerShell on Windows or a POSIX shell on macOS

## macOS setup

Run from the cloned project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

Regenerate the committed scenario and run tests:

```bash
python backend/data/generate_scenario.py
python -m pytest
```

Start FastAPI:

```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, install and start the frontend:

```bash
cd frontend
npm install
npm run dev
```

## Backend setup (Windows PowerShell)

Run from `C:\Users\prath\Documents\icenav-ai`:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\backend\requirements.txt
```

Regenerate the committed scenario:

```powershell
python .\backend\data\generate_scenario.py
```

Start FastAPI:

```powershell
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Run tests from the repository root:

```powershell
python -m pytest
```

## Frontend setup (Windows PowerShell)

Open a second PowerShell window and run:

```powershell
cd C:\Users\prath\Documents\icenav-ai\frontend
npm install
npm run dev
```

The frontend defaults to `http://localhost:8000`. To use another backend URL, create `frontend\.env.local` with:

```dotenv
VITE_API_BASE=http://localhost:8000
```

## URLs

- Frontend: <http://localhost:5173>
- Backend health: <http://localhost:8000/health>
- Current environment: <http://localhost:8000/environment/current>
- Interactive API docs: <http://localhost:8000/docs>

## Data contract

The frozen Milestone 1 schema and conventions are documented in [`docs/data-contract.md`](docs/data-contract.md). Coordinates use named `lat` and `lon` fields. Physical fields include units, vector directions are clockwise from true north and point toward motion, and ice concentration is normalized from `0.0` to `1.0`.

Scenario generation contains no live clock or unseeded randomness, so repeated runs produce the same JSON bytes. The committed `demo_scenario.json` is intentionally tracked for offline reproducibility.

## Current limitations

- All environmental and land/ice-shelf data are synthetic and not survey-grade.
- The corridor is an engineering demonstration, not an operational navigation product.
- The local map projection is suitable only for this bounded visualization.
- Safety-buffer rings are schematic screen-space indicators and are not map-scale circles.
- Non-land cells remain navigable in Milestone 1; concentration is visualization only.
- There is no routing, risk scoring, route mode, fuel model, forecast, prediction, machine learning, data ingestion, playback, auto-rerouting, authentication, database, or deployment configuration.
