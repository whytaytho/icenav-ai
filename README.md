# ICE-NAV AI

**AI-Enabled Antarctic Sea-Ice, Iceberg Trajectory, and Navigation Decision Support System**

**SIH26059 — Ministry of Earth Sciences**

Repository: <https://github.com/whytaytho/icenav-ai>

---

## Problem statement

Antarctic navigation is not a shortest-path problem. Sea ice evolves, icebergs
drift, and a route that is safe at departure can be dangerous several hours
later. A road network is static and only its traffic changes; here the
navigable surface itself changes, so cells that were passable become forbidden
and the set of feasible routes at T+6h differs from the set at T+0.

## Our solution

ICE-NAV AI combines sea-ice, iceberg and environmental data into a
**time-dependent risk surface**, plans routes across it with a deterministic
A\* search, detects when a committed route is predicted to become unsafe, and
explains the change factor by factor.

The division of responsibility is deliberate, and is the answer to
"where is the AI?":

| Layer | Nature | What it does |
|---|---|---|
| Forecast | statistical / physical, uncertain | predicts iceberg drift and sea-ice advection |
| Risk | deterministic, configurable | turns the environment into a 0–100 risk surface |
| Decision | deterministic, auditable | A\* routing, hazard detection, explanation |

**AI forecasts the environment. It never chooses the route.** Route selection
stays inspectable, reproducible and explainable.

---

## Demo sequence

The timed three-minute script is in [`docs/demo-script.md`](docs/demo-script.md).
Every figure below is produced by the committed scenario and reproduced by
`python scripts/demo_check.py`.

1. **Compare all modes** at T+0 — three strategies over one risk surface.
2. **Commit the balanced route** — planned safety **89.8 / 100**.
3. **Move the forecast slider to +6h** — IB-04 drifts into the direct lead.
4. **PREDICTED ROUTE CONFLICT** fires — safety falls **89.8 → 43.4**, first
   conflict at waypoint 10 of 23, about 10 hours into the voyage.
5. **AUTO REROUTE** — an alternate route scoring **87.5**, costing
   **+12.0 km**, **+0.5 h**, **+12.0 ice-adjusted km**.
6. **Explainability panel** — the risk change attributed by factor, summing
   arithmetically to the reported total.

### Measured demo figures

| Quantity | Value |
|---|---:|
| Planned balanced route safety at T+0 | 89.8 |
| Same route re-scored against the +6h forecast | 43.4 |
| Alternate route safety at +6h | 87.5 |
| Additional distance / time / fuel index | +12.0 km / +0.5 h / +12.0 |
| First conflict | waypoint 10 of 23, hour 10.0 |
| Responsible iceberg | IB-04 |

### T+0 route comparison

Straight-line reference: **344.4 km**.

| Mode | Alpha | Distance | ETA | Safety | Est. Fuel Index |
|---|---:|---:|---:|---:|---:|
| Fastest | 0.0 | 350.9 km | 15.8 h | 82.5 | 350.9 |
| Balanced | 0.6 | 350.9 km | 15.8 h | 82.5 | 350.9 |
| Safest | 4.0 | 368.4 km | 16.6 h | 90.6 | 368.4 |

Fastest and Balanced resolve to the same path on this scenario; Safest buys
**8.1 safety points for 17.5 km** by taking the wider eastern lead.

Because no candidate route crosses ice above the 0.20 concentration at which
the resistance factor rises above 1.0, the Estimated Fuel Index equals route
distance here. That is the correct output of the model, not a defect — the
index exceeds distance only where a route is forced through heavier ice. The
scenario was not reshaped to manufacture a fuel difference.

---

## System architecture

```text
        sea ice · icebergs · wind · ocean current
                          |
                  generate_scenario.py
              (deterministic committed scenario)
                          |
        +-----------------+------------------+
        |                                    |
  iceberg.py (persistence | free drift | ML) |
  seaice.py  (semi-Lagrangian advection)     |
        |                                    |
        +----------> api/forecast.py <-------+
                 (T+0/3/6/12/24 cached)
                          |
                       risk.py
              two-tier risk surface, 0-100
                          |
                     routing.py
          time-expanded A*, admissible heuristic
                          |
        +-----------+-----+------+------------+
        |           |            |            |
    fuel.py   comparison.py  hazard.py   explain.py
                          |
                       FastAPI
                          |
                       api.js
                          |
                    Dashboard.jsx
      map · comparison · alert · explainability
```

A fuller walkthrough is in [`docs/architecture.md`](docs/architecture.md).

The calculation modules are pure: no HTTP, no file loading, no global state.
FastAPI validates the whole YAML configuration once at startup, builds the
forecast cache once, and passes plain data into the engines. That purity is
what lets the forecast layer reuse the risk and routing code unchanged.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | per-component readiness (scenario, forecast cache, model, risk config) |
| GET | `/environment/current` | committed scenario |
| GET | `/environment/risk` | risk surface for a horizon |
| GET | `/config/risk` | the active, configurable risk weights |
| GET | `/scenarios` | available scenarios |
| GET | `/forecast`, `/forecast/horizons` | forecast environment and horizon list |
| GET | `/icebergs/trajectory` | predicted positions of one berg |
| POST | `/route` | one route in one mode |
| POST | `/routes/compare` | all three modes against one risk surface |
| POST | `/route/reroute` | evaluate committed route, detect hazard, propose alternate, explain |
| GET | `/validation/backtest`, `/validation/options`, `/validation/times` | historical iceberg backtesting |

Interactive documentation at <http://localhost:8000/docs>. Request and response
shapes are frozen in [`docs/data-contract.md`](docs/data-contract.md).

## Risk model

Two tiers, and the distinction matters.

**Hard constraints** remove a cell from the navigable world entirely — land,
ice concentration at or above 0.80, and anything within an iceberg's
`radius_km + safety_buffer_km`. These cells are absent from the search graph,
so no weighting can ever route a vessel through an iceberg.

**Soft risk** scores the remaining cells 0–100:

```text
risk = 0.50 x sea_ice + 0.25 x iceberg + 0.15 x wind + 0.10 x current
```

Route-level scores combine average and worst-case exposure, so a route that is
mostly clear but touches one severe cell cannot hide behind its mean:

```text
risk_score   = 0.5 x mean_cell_risk + 0.5 x max_cell_risk
safety_score = 100 - risk_score
```

Every active constant lives in `backend/config/weights.yaml` and is served live
at `/config/risk`. They are configurable engineering-demo values, **not**
scientifically calibrated operating limits.

## Navigation algorithm

A\* over navigable cells, 8-connected, with no diagonal passage between two
blocked orthogonal cells, and deterministic tie-breaking so the same request
always returns the same route.

```text
risk_norm = mean(risk_from, risk_to) / 100
step_cost = segment_km x (1 + alpha x risk_norm)
```

The cost is **multiplicative and in kilometre-equivalent units**, which matters
for two reasons. It keeps distance and risk dimensionally coherent instead of
adding kilometres to risk points; and because the edge multiplier can never
fall below 1.0, the straight-line haversine heuristic can never overestimate
the remaining cost. The heuristic is therefore admissible and A\* returns a
genuinely optimal path — a property the test suite verifies by comparing A\*
against Dijkstra over the same cost function.

`alpha` is the single risk-aversion knob: **Fastest 0.0, Balanced 0.6,
Safest 4.0**.

Routing is **time-expanded**: node identity is `(row, col, arrival_time_bucket)`
and each cell is costed against the forecast snapshot nearest the hour the
vessel actually reaches it. A voyage of roughly 16 hours is therefore scored
against several different states of the world rather than one frozen snapshot.

## Estimated Fuel Index

```text
fuel contribution = segment_km x resistance_factor(mean_segment_ice)
```

The **Estimated Fuel Index (ice-adjusted km)** is a dimensionless proxy. It is
not litres, tonnes, measured consumption, or a validated vessel fuel model.
Every resistance factor is at least 1.0, so the index can never fall below
route distance.

## AI/ML methodology and evaluation

The optional Random Forest predicts iceberg displacement in a local metric
frame (`delta_north_km`, `delta_east_km`) rather than in degrees, which avoids
forcing the model to learn the latitude-dependent physical size of a degree of
longitude.

Data: **BYU/NIC Consolidated Antarctic Iceberg Tracking Database v8.0** —
95 icebergs, 45,345 observations, median sampling interval 24 hours. Splits are
iceberg-disjoint (group holdout) and additionally reported on a temporal
holdout; no berg appears on both sides of a split.

Required citation: J.S. Budge and D.G. Long, "A comprehensive database for
Antarctic iceberg tracking using scatterometer data," *IEEE Journal of Selected
Topics in Applied Earth Observations*, Vol. 11, No. 2,
doi:10.1109/JSTARS.2017.2784186, 2017.

| Split | Predictor | Mean km | Median km | P90 km | RMSE km | N |
|---|---|---:|---:|---:|---:|---:|
| Group | Random Forest | 2.35 | 0.22 | 7.05 | 5.59 | 7,342 |
| Group | Persistence | 2.93 | 0.00 | 9.64 | 6.80 | 7,342 |
| Group | Stationary | 2.36 | 0.00 | 7.66 | 6.32 | 7,342 |
| Temporal | Random Forest | 0.67 | 0.12 | 1.35 | 1.70 | 8,942 |
| Temporal | Persistence | 0.58 | 0.00 | 0.87 | 2.25 | 8,942 |
| Temporal | Stationary | 0.77 | 0.00 | 1.86 | 2.66 | 8,942 |

**The Random Forest beats persistence on group-holdout mean error and loses to
it on temporal-holdout mean error.** It is therefore presented as experimental,
not as an operationally validated replacement for persistence. Free-drift
accuracy is not reported because no collocated historical wind and current
observations were confirmed for these tracks.

Two scope limits apply to every figure above, and are repeated wherever the
model is quoted in the interface:

- Validation is at **+24h only**, because the source data is daily. The demo's
  +3h/+6h/+12h horizons are interpolated from a model validated at daily
  resolution and are **not independently validated**.
- The database tracks **giant tabular icebergs**, a different size class from
  the 1–4 km bergs in the demo scenario. The model demonstrates data-driven
  drift prediction for the size class the data covers; it is not a validated
  claim about small-berg behaviour.

The demo never depends on the model. If `iceberg_model.pkl` is deleted, startup
logs a warning, `/health` reports `degraded`, and forecasting continues on the
free-drift baseline.

## Requirements

- Python 3.12 (the pinned `scikit-learn` wheel targets it)
- Node.js 18 or later, and npm
- Internet access once, to install dependencies

**Runtime uses no external map tiles, data APIs, or internet connection.**

## Installation

### Windows PowerShell

```powershell
git clone https://github.com/whytaytho/icenav-ai.git
cd icenav-ai
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\backend\requirements.txt
python .\backend\data\generate_scenario.py
python -m pytest
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

In a second window:

```powershell
cd .\frontend
npm install
npm run dev
```

### macOS / Linux

```bash
git clone https://github.com/whytaytho/icenav-ai.git
cd icenav-ai
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
python backend/data/generate_scenario.py
python -m pytest
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

The frontend dev server **must** run on port 5173; the backend CORS allowlist
names that origin explicitly rather than using a wildcard. To point the
frontend at a different backend, create `frontend/.env.local`:

```dotenv
VITE_API_BASE=http://localhost:8000
```

### Verifying the demo

```bash
python scripts/demo_check.py
```

This measures every figure the presentation quotes and exits non-zero if any of
them regress. Run it before presenting.

### Optional: historical iceberg data

Case-level historical validation needs the BYU/NIC tracks, which are not
redistributed in this repository because explicit redistribution permission was
not located. One-time setup:

```bash
python -m backend.ingestion.iceberg_tracks --download
python -m backend.ingestion.train_iceberg_model
```

Everything else — the map, routing, forecasting, hazard detection, rerouting
and explanation — works without this step.

## URLs

| | |
|---|---|
| Frontend | <http://localhost:5173> |
| Health | <http://localhost:8000/health> |
| API docs | <http://localhost:8000/docs> |
| Risk configuration | <http://localhost:8000/config/risk> |
| Risk surface | <http://localhost:8000/environment/risk> |

## Performance

Measured on the committed 30 × 30 scenario, in-process:

| Operation | Time |
|---|---:|
| Startup (config + forecast cache + model load) | ~1.3 s |
| `GET /environment/current` | ~5 ms |
| `GET /environment/risk` | ~10 ms |
| `POST /route` | ~17 ms |
| `POST /routes/compare` (three routes) | ~29 ms |

All five forecast horizons are precomputed at startup, so the forecast slider
does no routing work and responds immediately.

## Deployment

The demonstration is run from **localhost**, deliberately. Free hosting tiers
sleep after inactivity and take tens of seconds to wake, which is not
acceptable in front of a judging panel. Deployment is proof of deployability,
not the demo path. See [`docs/deployment.md`](docs/deployment.md).

## Testing

```bash
python -m pytest              # 89 tests
python scripts/demo_check.py  # demo figures
cd frontend && npm run build  # frontend compiles
```

The suite covers geodesy round-trips at 68 degrees south, grid cell
round-trips, risk invariants and hard constraints, A\* optimality against
Dijkstra, refusal of diagonal corner-cutting, route mode ordering, fuel
invariants, forecast determinism, static-forecast equivalence between snapshot
and time-expanded routing, hazard and explanation arithmetic, ML split leakage,
offline operation, and the end-to-end demo figures.

## Repository layout

```text
icenav-ai/
├── backend/
│   ├── main.py                     FastAPI application
│   ├── config/weights.yaml         every active tunable constant
│   ├── data/
│   │   ├── generate_scenario.py    deterministic scenario generator
│   │   └── demo_scenario.json      committed, byte-reproducible
│   ├── engine/
│   │   ├── geo.py, grid.py         geodesy and grid discretisation
│   │   ├── risk.py                 two-tier risk surface
│   │   ├── routing.py              A*, smoothing, metrics
│   │   ├── fuel.py, comparison.py  fuel index, three-mode comparison
│   │   ├── iceberg.py, seaice.py   drift baselines, ice advection
│   │   ├── hazard.py, explain.py   hazard detection, factor attribution
│   │   ├── ml.py, iceberg_features.py
│   │   ├── validation.py           historical backtesting
│   │   └── scenarios.py, schema.py
│   ├── api/forecast.py             horizon cache
│   ├── ingestion/                  offline, ahead-of-time data acquisition
│   └── models/                     trained model + provenance metadata
├── frontend/src/
│   ├── components/                 map, panels, alerts, explainability
│   ├── pages/                      Dashboard, Validation
│   └── services/api.js
├── docs/
│   ├── data-contract.md            frozen API contract
│   ├── methodology.md              data provenance and method notes
│   ├── architecture.md             system diagram and data flow
│   ├── demo-script.md              timed presentation script
│   ├── judge-qa.md                 prepared answers
│   └── deployment.md
├── notebooks/iceberg_prediction.ipynb
├── scripts/demo_check.py           demo regression guard
└── tests/                          89 tests
```

---

## Limitations

Stated plainly, because a limitation a team names itself is evidence of
understanding, and one a judge finds first is not.

**Scenario and environment**

- The demonstration environment is **synthetic**. Coastline, sea ice, wind and
  currents are hand-authored, not observed.
- The corridor is inspired by a Prydz Bay / Bharati-approach setting, but the
  exact coordinates are **illustrative, not charted**, and have not been
  verified against a nautical chart.
- The hazard scenario is **deliberately engineered** so the demonstration is
  reproducible. It is placed geographically; no code special-cases it, and the
  alert, reroute and explanation are produced by the same generic engine that
  would run on any scenario.
- The land and ice-shelf mask is hand-authored, not survey-grade hydrography.

**Model and scoring**

- Risk weights, mode alphas, speed factors and resistance factors are
  **configurable prototype values, not calibrated** against any vessel or
  historical voyage.
- The Estimated Fuel Index is a dimensionless proxy, **not** measured fuel
  consumption.
- ETA speed factors are illustrative, and are not measured performance for any
  hull or ice class.
- Iceberg ML is validated at **+24h only**, on **giant tabular bergs**. Shorter
  horizons and small bergs are not independently validated.
- Free-drift historical accuracy is not reported; no collocated wind/current
  observations were confirmed.
- **No sea-ice forecast accuracy is claimed at all.** Ice advection is a
  first-order semi-Lagrangian scheme, not a physical sea-ice model.
- Wind and current fields are held constant across forecast horizons.
- **Small growlers and bergy bits — in practice a dominant collision hazard for
  ships — are not resolvable in satellite iceberg databases and are entirely
  out of scope.**

**Engineering**

- Milestone 8 environmental ingestion is deliberately **source-gated**: no real
  sea-ice product has been approved with an exact product, version, citation,
  licence, projection, resolution and access method, so no observed sea-ice
  scenario is claimed. The adapter and scenario registry exist and are tested.
- A fresh clone must run the documented BYU/NIC acquisition command before
  case-level historical validation, because redistribution permission for the
  derived CSV was not located.
- Path smoothing is disabled: a navigability-only shortcut can invalidate the
  Fastest/Balanced/Safest ordering, so routes follow the grid until smoothing
  evaluates the same objective as A\*.
- The 30 × 30 grid limits route and exclusion-zone resolution to roughly 11 km.
- The map uses a local `CRS.Simple` projection with a cos(latitude) correction,
  valid for this bounded corridor only. Continental scaling requires a polar
  projection such as EPSG:3031.
- Route endpoints are the committed vessel and destination; the map does not
  support dragging endpoints.
- There is no authentication, database, or live ingestion at runtime.

## Future scope

- Approve a specific sea-ice product and complete observed-data ingestion.
- Reproject to EPSG:3031 and tile the corridor to scale beyond one region.
- Calibrate risk weights and resistance factors against vessel ice class and
  historical voyages.
- Obtain sub-daily iceberg observations, to validate the horizons the demo
  actually shows.
- Smoothing that optimises the same objective as the search, so it can be
  re-enabled without disturbing mode ordering.
- Ensemble or probabilistic forecasting, to carry uncertainty into the risk
  surface rather than treating each horizon as deterministic.

---

## Scientific integrity

Every quantitative claim in this repository traces to a measurement:

- Demo figures are reproduced by `python scripts/demo_check.py` and asserted by
  the test suite.
- ML metrics come from `backend/models/iceberg_model_meta.json`, written at
  training time, and are reported for the model **and** its baselines —
  including the split where the baseline wins.
- Risk weights and routing constants are served live at `/config/risk`.

Where a number is a prototype value, it is labelled as one. Where a model is
experimental, it is labelled as such. Nothing in this repository claims
scientific validation that was not performed.
