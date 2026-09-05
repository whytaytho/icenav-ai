# ICE-NAV AI — Architecture

**SIH26059 — Ministry of Earth Sciences**

---

## The one-sentence version

A **time-varying cost surface** over a bounded Antarctic sea region, a
deterministic shortest-path search across it, and a diff engine that explains
why the path changed when the surface changed.

## Layer separation

The single most important structural decision in this project is that
forecasting, risk scoring and route selection are three separate layers with
one-way data flow.

| Layer | Nature | Modules |
|---|---|---|
| **Forecast** | statistical / physical, **uncertain** | `iceberg.py`, `seaice.py`, `api/forecast.py`, `ml.py` |
| **Risk** | deterministic, **configurable** | `risk.py`, `config/weights.yaml` |
| **Decision** | deterministic, **auditable** | `routing.py`, `hazard.py`, `explain.py`, `comparison.py`, `fuel.py` |

Uncertainty is confined to the forecast layer. Once a forecast exists, every
downstream step is reproducible arithmetic. That is why a route can be
explained cell by cell, and why the same request always returns the same
answer.

## Data flow

```text
                sea ice · icebergs · wind · ocean current
                                |
                    backend/data/generate_scenario.py
              deterministic, fixed seed, committed to git
                                |
                       demo_scenario.json
                    30 x 30 cells, 8 icebergs
                                |
         +----------------------+----------------------+
         |                                             |
   engine/iceberg.py                            engine/seaice.py
   persistence | free drift | ML                semi-Lagrangian advection
   (free drift = current + 2% wind)             backtrace + bilinear interp
         |                                             |
         +----------------------+----------------------+
                                |
                       api/forecast.py
        builds and caches T+0 / +3 / +6 / +12 / +24 at startup
                                |
                          engine/risk.py
             TIER 1  hard constraints -> cell removed
                     land, ice >= 0.80, berg radius+buffer
             TIER 2  soft risk 0-100, weighted sum
                     0.50 ice + 0.25 berg + 0.15 wind + 0.10 current
                                |
                        engine/routing.py
        A* over navigable cells only, 8-connected, no corner cutting
        node = (row, col, arrival_time_bucket)   <- time-expanded
        cost = segment_km x (1 + alpha x risk_norm)
        heuristic = straight-line haversine  (admissible: multiplier >= 1)
                                |
        +-----------+-----------+-----------+-----------+
        |           |           |           |           |
    fuel.py   comparison.py  hazard.py  explain.py  validation.py
    ice-adj   3 modes +      committed  factor      historical
    distance  recommendation route eval attribution backtesting
                                |
                          backend/main.py
              FastAPI - config validated once at startup
                                |
                      frontend/src/services/api.js
                                |
                     frontend/src/pages/Dashboard.jsx
                                |
        map · comparison · forecast slider · alert · explainability
```

## Why the cost function is multiplicative

```text
step_cost = segment_km x (1 + alpha x risk_norm)
```

An additive formulation — `w_dist x km + w_risk x risk` — fails in two ways
that are easy to miss and hard to debug.

**Unit mixing.** A step is about 11 km; risk runs 0–100. Under additive weights
of 0.2/0.8 a step costs `0.2 x 11 + 0.8 x 80 = 66.2`, of which geometry
contributes 2.2. Distance is effectively ignored and routes wander.

**Inadmissible heuristic.** If the distance weight is 0.2 but the heuristic
returns raw straight-line kilometres, the heuristic *overestimates* remaining
cost. A\* then no longer returns an optimal path — and it still returns *a*
path, so the bug hides until someone checks.

The multiplicative form fixes both. The multiplier can never fall below 1.0, so
straight-line distance is always a lower bound on remaining cost and the
heuristic stays admissible. The output is in kilometre-equivalent units, the
same quantity the fuel index uses, so routing cost and fuel cost are one
coherent concept.

`tests/test_routing.py` verifies admissibility empirically by running A\* and
Dijkstra over the same cost function and asserting equal total cost.

## Why routing is time-expanded

A voyage across this corridor takes about 16 hours. Scoring the whole grid
against a single forecast snapshot would mean pricing the last leg of the
voyage with conditions from the moment of departure.

Node identity is therefore `(row, col, arrival_time_bucket)`. On expanding a
node the search computes segment travel time from the local ice concentration,
adds it to accumulated time, and prices the neighbour against the forecast
snapshot nearest that arrival hour. Bucketing keeps the state space finite —
without it, floating-point arrival times make every node unique.

The heuristic remains admissible: the minimum edge multiplier is 1.0 at any
time, so straight-line distance is still a lower bound.

`tests/test_forecast.py` asserts that with a **static** forecast (all horizons
identical), time-expanded search returns exactly the snapshot result. That is
the regression guard for the whole upgrade.

## Why risk has two tiers

Iceberg proximity as a soft weighted term at 0.25 would mean a cell containing
an iceberg, in calm open water, scores total risk 25 — and the router would
sail straight through it. A collision is not a 25%-bad outcome.

So cells within `radius_km + safety_buffer_km` of any berg, cells with ice at
or above 0.80, and land cells are **absent from the graph**. They are not
expensive; they are unreachable. No weight tuning can produce a route through
an iceberg.

The weighted 0–100 score then shapes preference only among cells that are
already passable.

## Why the route score uses both mean and maximum

```text
risk_score = 0.5 x mean_cell_risk + 0.5 x max_cell_risk
```

A route averaging risk 20 with one cell at 95 is not a safe route. Mean alone
hides the single lethal cell, so worst-case exposure carries equal weight.

## Why the explanation is not a language model

`explain.py` diffs the per-component risk contributions that `risk.py` already
stored on every cell, between the T+0 evaluation and the forecast evaluation,
then sorts by magnitude. The components **sum to the reported total**, and a
test fails if they ever stop summing.

The risk engine already knows exactly what changed. Asking a language model to
describe it would be less accurate, unverifiable, and impossible to defend to a
judge who checks the arithmetic.

## Purity, and why it matters

`geo.py`, `grid.py`, `risk.py`, `routing.py`, `fuel.py`, `iceberg.py`,
`seaice.py`, `hazard.py` and `explain.py` perform no I/O, make no HTTP calls,
and hold no global state. They take data and return data.

That is what makes the forecast layer cheap: a forecast scenario has exactly
the same shape as `demo_scenario.json`, so `compute_risk_grid` and the entire
routing stack operate on it with no modification. There is no parallel
"forecast-mode" implementation to keep in sync.

Configuration is loaded and validated **once** at application startup —
weights summing to 1.0, all required blocks present, non-negative alphas, fuel
resistance factors at or above 1.0. Failures are loud and immediate rather than
subtle and per-request.

## Offline guarantee

Nothing in the request path touches the network. The scenario is committed, all
five forecast horizons are precomputed at startup, and the map renders from a
local `CRS.Simple` projection with no external tile server. External data
acquisition is a separate, ahead-of-time, manual step under
`backend/ingestion/`.

This is a design requirement, not a fallback. Venue internet fails.

## Coordinate handling

At 68 degrees south, one degree of longitude spans about 41.7 km against
111.2 km for one degree of latitude. Any code treating a degree as a degree is
wrong here.

- Distances go through `geo.haversine_km`; nothing computes distance from
  degree differences.
- The corridor bounds (3 degrees of latitude by 8 of longitude over a 30 × 30
  grid) are chosen so cells come out approximately square in kilometres —
  11.12 km by 11.11 km, computed geodesically and reported in scenario
  metadata.
- The frontend projects longitude by cos(mean latitude) under Leaflet's
  `CRS.Simple`, avoiding the severe Web Mercator distortion at this latitude.

This is a local equirectangular approximation, valid for a bounded box only.
Continental scaling requires EPSG:3031 — the polar stereographic projection the
NSIDC sea-ice products already use.

## Test strategy

89 tests, organised around invariants rather than magic numbers, so the
scenario can be retuned without rewriting the suite.

| Area | What is guarded |
|---|---|
| `test_geo` | haversine against hand-computed distances at 68°S, bearing normalisation, destination round-trip |
| `test_grid` | cell ↔ lat/lon round-trip for every cell, neighbour validity, bounds |
| `test_risk` | hard constraints, component ranges, monotonicity, determinism |
| `test_routing` | **A\* equals Dijkstra**, no blocked cells on path, no corner cutting, detour around obstacles |
| `test_modes_fuel` | safety ordering across modes, `fuel_index >= distance_km` always |
| `test_forecast` | vector conventions, drift plausibility, **static forecast equals snapshot routing** |
| `test_hazard_explain` | **components sum to total**, demo figures within bands, reroute improves safety |
| `test_ml` | no berg spans train/test, feature-order match, safe fallback |
| `test_ingestion` | **no network call in any request path**, schema conformance |
| `test_validation` | no observation after T0 leaks into a backtest |

`scripts/demo_check.py` sits alongside the suite and measures the figures the
presentation quotes, failing if any regress.
