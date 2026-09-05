# ICE-NAV AI — Milestones 1–7 + Milestone 8 Validation

**SIH26059 — Ministry of Earth Sciences**  
AI-Enabled Antarctic Sea-Ice, Iceberg Trajectory, and Navigation Decision Support System

Public repository: <https://github.com/whytaytho/icenav-ai>

## Current milestone

Milestones 5–7 and the completed historical-validation portion of Milestone 8 add cached environmental forecasts, time-expanded routing,
forecast hazard detection, automatic rerouting, deterministic explanations, an
optional Random Forest iceberg predictor, offline scenario discovery, and a
historical trajectory-validation screen. Runtime remains fully offline.

Milestone 8 environmental ingestion remains deliberately human-gated: no real
sea-ice product has yet been approved with an exact product/version, citation,
licence, projection, resolution, format, and access method. The adapter and
scenario registry are implemented, but no observed sea-ice scenario is claimed.

## Demo capabilities

- A bounded 30 × 30 synthetic Antarctic environment and navigation risk surface
- Navigable-only A* routing with deterministic tie-breaking
- No diagonal passage between two blocked orthogonal cells
- Supercover line-of-sight path smoothing without crossing forbidden cells
- Fastest, Balanced, and Safest routes controlled by configurable risk aversion
- Distance, ice-adjusted ETA, route risk, safety score, and cells traversed
- Estimated Fuel Index (ice-adjusted km) for every route
- Rule-based recommendation with the actual comparison numbers in its reason
- One-click three-route overlay with distinct arcade-console colours
- Optional raw grid path for demonstrating the underlying A* search
- Discrete NOW/+3h/+6h/+12h/+24h forecast snapshots with sea-ice advection
- Persistence, free-drift, and optional ML iceberg predictors
- Committed-route hazard detection, alternate route, and arithmetic explanation
- BYU/NIC +24-hour historical iceberg backtesting

ML metrics apply only to +24-hour giant-tabular-iceberg tracks. Shorter demo
horizons are not independently validated, and no sea-ice forecast accuracy is
claimed.

## Measured M7 results

BYU/NIC v8.0 subset: 95 icebergs, 45,345 observations, median sampling interval
24 hours. Group holdout uses iceberg-disjoint IDs; temporal holdout trains on
earlier predictions and tests on later predictions.

| Split | Predictor | Mean km | Median km | P90 km | RMSE km | N |
|---|---|---:|---:|---:|---:|---:|
| Group | Random Forest | 2.35 | 0.22 | 7.05 | 5.59 | 7,342 |
| Group | Persistence | 2.93 | 0.00 | 9.64 | 6.80 | 7,342 |
| Group | Stationary | 2.36 | 0.00 | 7.66 | 6.32 | 7,342 |
| Temporal | Random Forest | 0.67 | 0.12 | 1.35 | 1.70 | 8,942 |
| Temporal | Persistence | 0.58 | 0.00 | 0.87 | 2.25 | 8,942 |
| Temporal | Stationary | 0.77 | 0.00 | 1.86 | 2.66 | 8,942 |

The Random Forest beats persistence on group-holdout mean error but loses on
temporal-holdout mean error. It is therefore experimental, not an operationally
validated replacement for persistence. Free-drift accuracy is unavailable
without collocated historical wind/current observations.

## Architecture

```text
demo_scenario.json
        ↓
risk.py + weights.yaml → one navigation risk surface
        ↓
routing.py → deterministic A* + smoothing + ETA
fuel.py    → Estimated Fuel Index
comparison.py → three modes + recommendation
        ↓
FastAPI
  GET  /environment/current
  GET  /environment/risk
  GET  /forecast
  GET  /forecast/horizons
  GET  /scenarios
  GET  /validation/options
  GET  /validation/times
  GET  /validation/backtest
  POST /route
  POST /route/reroute
  POST /routes/compare
        ↓
api.js → Dashboard.jsx
        ↓
NavigationPanel + RouteComparison + AntarcticMap
```

The calculation modules are independent of HTTP and file loading. FastAPI loads
and validates the complete YAML configuration once at startup, computes the risk
surface once per comparison request, and passes data into the pure engines.

## Routing model

Every A* edge uses kilometre-equivalent cost:

```text
risk_norm = mean(risk_from, risk_to) / 100
step_cost = segment_km × (1 + alpha × risk_norm)
```

The heuristic is raw straight-line haversine distance. It is admissible because
the edge multiplier can never be below `1.0`; true remaining cost must therefore
be at least the direct distance.

Current mode values:

| Mode | Alpha | Intent |
|---|---:|---|
| Fastest | 0.5 | Prefer shorter distance |
| Balanced | 2.0 | Trade distance against risk |
| Safest | 6.0 | Prefer lower-risk water |

All active risk, routing, speed, fuel, and recommendation values live in
`backend/config/weights.yaml`. They are configurable engineering-demo values,
not scientifically calibrated operating limits.

## Estimated Fuel Index

For each segment:

```text
fuel contribution = segment_km × resistance_factor(mean_segment_ice)
```

The **Estimated Fuel Index (ice-adjusted km)** is a dimensionless ice-adjusted
distance proxy. It is not litres, tonnes, measured fuel consumption, or a
validated vessel fuel model. Every resistance factor is at least `1.0`, so the
index can never be lower than route distance.

## Requirements

- Git
- Python 3.9 or later
- Node.js 18 or later and npm
- Internet access once to install dependencies

Runtime uses no external map tiles, data APIs, or internet connection.

## Clone

```text
git clone https://github.com/whytaytho/icenav-ai.git
cd icenav-ai
```

## macOS / Linux

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
python backend/data/generate_scenario.py
python -m pytest
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Optional one-time M7 historical-data setup (required for case-level validation):

```bash
python -m backend.ingestion.iceberg_tracks --download
python -m backend.ingestion.train_iceberg_model
```

## Windows PowerShell

From the cloned repository directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\backend\requirements.txt
python .\backend\data\generate_scenario.py
python -m pytest
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

In a second PowerShell window:

```powershell
cd .\frontend
npm install
npm run dev
```

Optional one-time M7 historical-data setup in PowerShell:

```powershell
python -m backend.ingestion.iceberg_tracks --download
python -m backend.ingestion.train_iceberg_model
```

To use another backend URL, create `frontend/.env.local`:

```dotenv
VITE_API_BASE=http://localhost:8000
```

## URLs

- Frontend: <http://localhost:5173>
- Health: <http://localhost:8000/health>
- Environment: <http://localhost:8000/environment/current>
- Risk surface: <http://localhost:8000/environment/risk>
- Risk configuration: <http://localhost:8000/config/risk>
- Interactive API documentation: <http://localhost:8000/docs>
- Forecast horizons: <http://localhost:8000/forecast/horizons>
- Forecast example: <http://localhost:8000/forecast?hour=6>
- Scenario list: <http://localhost:8000/scenarios>

`POST /route` requires `fastest`, `balanced`, or `safest`. `POST
/routes/compare` computes all three against one risk surface. Example requests
are documented in `docs/data-contract.md` and available interactively through
FastAPI’s `/docs` page.

## Directory structure

```text
icenav-ai/
├── backend/
│   ├── config/weights.yaml
│   ├── data/demo_scenario.json
│   ├── data/generate_scenario.py
│   ├── engine/comparison.py
│   ├── engine/fuel.py
│   ├── engine/geo.py
│   ├── engine/grid.py
│   ├── engine/risk.py
│   ├── engine/routing.py
│   └── main.py
├── docs/data-contract.md
├── frontend/src/
│   ├── components/AntarcticMap.jsx
│   ├── components/LayerToggle.jsx
│   ├── components/Legend.jsx
│   ├── components/NavigationPanel.jsx
│   ├── components/RouteComparison.jsx
│   ├── components/StatusBar.jsx
│   ├── pages/Dashboard.jsx
│   ├── services/api.js
│   └── styles.css
└── tests/
    ├── test_api.py
    ├── test_geo.py
    ├── test_grid.py
    ├── test_modes_fuel.py
    ├── test_risk.py
    ├── test_routing.py
    └── test_scenario.py
```

## Current limitations

- Live environment, coastline, weather, current, and sea ice remain synthetic.
- Real environmental sea-ice ingestion is source-gated and intentionally not bound to an unconfirmed product.
- A fresh clone must run the documented BYU/NIC acquisition command before case-level historical validation because explicit redistribution permission for the derived CSV has not been located.
- Iceberg ML is validated at +24h only on giant tabular bergs; short horizons and small demo bergs are not independently validated.
- Group holdout mean error is 2.35 km for ML versus 2.93 km for persistence (7,342 samples); temporal holdout mean is 0.67 km for ML versus 0.58 km for persistence (8,942 samples), so ML does not consistently beat persistence.
- Free-drift historical accuracy is not reported without collocated wind/current observations.
- The corridor is an engineering demo, not an operational navigation product.
- Risk weights, mode alphas, speed factors, and resistance factors are not calibrated.
- ETA factors are illustrative and are not measured performance for a real hull or ice class.
- Estimated Fuel Index is a proxy and is not calibrated against any vessel.
- The local `CRS.Simple` map is not an operational Antarctic projection.
- Endpoint selection is currently the committed vessel and destination; map dragging is not implemented.
- The 30 × 30 grid limits route and exclusion-zone resolution.
- Forecast snapshots are discrete at T+0h, +3h, +6h, +12h, and +24h; environmental forcing is held constant across the horizon.
- There is no live ingestion, authentication, database, deployment orchestration, or operational polar projection.
