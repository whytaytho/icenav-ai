# ICE-NAV AI Data Contract

## Forecast and route-time semantics

- `forecast_hour` selects one supported world snapshot: `0, 3, 6, 12, 24`.
- `departure_hour` states when the vessel leaves and drives time-expanded A*.
- Route `timing` reports departure, arrival, forecast exhaustion, and
  `snapshots_used`.
- Forecast scenarios preserve the base environment shape and add
  `meta.drift_model_used`; predictions are not observations.
- Real-data cells may add `data_quality: observed | interpolated | missing`.
  Missing data is never encoded as zero concentration and is non-navigable by
  default.

Reroute explanations derive contributor impacts from the existing weighted risk
components. Their arithmetic sum is `total_risk_delta` over the same conflict
waypoints.

This document freezes the JSON contract used by the deterministic Milestone 1 environment endpoint. Later components should remain compatible with this schema or introduce an explicitly versioned replacement.

## Coordinate and unit conventions

- Coordinates are objects or named fields. Ambiguous coordinate arrays such as `[-68.2, 74.1]` are not part of the API contract.
- `lat` and `lon` are decimal degrees in WGS 84 (`EPSG:4326`). Latitude is negative in the Southern Hemisphere.
- Every physical quantity includes its unit in the field name, for example `wind_speed_ms`, `velocity_kmh`, and `radius_km`.
- `heading_deg` and all `*_direction_deg` values are degrees clockwise from true north, normalized to `[0, 360)`.
- `wind_direction_deg` is the direction **toward which** the wind vector acts. This intentionally differs from the traditional meteorological "wind from" convention.
- `current_direction_deg` is likewise the direction toward which the current acts.
- `ice_concentration` is a normalized fraction in `[0.0, 1.0]`, not a percentage from 0 to 100.
- Timestamps use ISO 8601. The committed demo uses a fixed timestamp so regeneration is byte-for-byte deterministic.

## Geographic assumptions

Milestone 1 covers a bounded synthetic corridor from latitude `-69.5` to `-66.5` and longitude `71.0` to `79.0`. It is inspired by a Prydz Bay / Bharati-approach setting for engineering demonstrations; it is not an operationally validated navigation corridor.

Grid rows run south to north and columns run west to east. Each cell's `lat` and `lon` identify its centre. Angular cell dimensions are derived independently from latitude and longitude bounds. Reported physical cell height and width are calculated geodesically near the corridor midpoint, so longitude is not treated as physically equivalent to latitude.

Local or equirectangular reasoning is acceptable inside this small prototype area. A production Antarctic system should use a suitable polar projection such as Antarctic Polar Stereographic `EPSG:3031`; this local approximation must not be extrapolated across Antarctica.

The demo land/ice-shelf mask is synthetic and hand-authored. It is not survey-grade and must not be used for real navigation.

## `GET /environment/current`

The endpoint returns one JSON object with the following shape:

```json
{
  "meta": {
    "scenario_id": "prydz-bay-demo-v1",
    "generated_at": "2026-01-01T00:00:00Z",
    "forecast_hour": 0,
    "bounds": {
      "lat_min": -69.5,
      "lat_max": -66.5,
      "lon_min": 71.0,
      "lon_max": 79.0
    },
    "grid": {
      "rows": 30,
      "cols": 30,
      "cell_height_km": 11.1195,
      "cell_width_km": 11.1078
    },
    "data_source": "synthetic"
  },
  "vessel": {
    "id": "RV-01",
    "name": "Research Vessel",
    "lat": -68.95,
    "lon": 72.0,
    "speed_knots_open_water": 12.0
  },
  "destination": {
    "name": "Bharati approach",
    "lat": -67.05,
    "lon": 78.1
  },
  "icebergs": [
    {
      "id": "IB-01",
      "lat": -68.4,
      "lon": 73.2,
      "velocity_kmh": 0.7,
      "heading_deg": 35.0,
      "radius_km": 1.4,
      "safety_buffer_km": 3.0
    }
  ],
  "cells": [
    {
      "row": 0,
      "col": 0,
      "lat": -69.45,
      "lon": 71.133333,
      "ice_concentration": 0.0,
      "wind_speed_ms": 8.0,
      "wind_direction_deg": 70.0,
      "current_speed_ms": 0.3,
      "current_direction_deg": 20.0,
      "is_land": true,
      "is_navigable": false
    }
  ]
}
```

### Invariants

- `meta.grid.rows * meta.grid.cols` equals the number of objects in `cells`.
- Every `(row, col)` pair is unique and within the declared grid dimensions.
- Every coordinate lies inside `meta.bounds`.
- `is_land: true` always implies `is_navigable: false`.
- In Milestone 1, non-land cells are navigable; sea-ice concentration is visualized but is not a risk score or routing constraint.
- `forecast_hour` is exactly `0`; no forecast series exists in Milestone 1.
- `data_source` is exactly `synthetic`.

## Health contract

`GET /health` returns HTTP 200 with:

```json
{
  "status": "ok"
}
```

## Milestone 2 navigation risk contract

Milestone 2 adds a navigation risk surface without changing the Milestone 1
environment schema. Risk has two deliberately separate tiers:

1. **Hard constraints** decide whether a cell is forbidden. Land, sea-ice
   concentration at or above the configured threshold, and iceberg exclusion
   zones are non-navigable regardless of their weighted score.
2. **Soft risk** compares cells that remain navigable. Sea ice, iceberg
   proximity, wind, and current each produce a raw risk from `0` to `100`, then
   contribute to `total_risk` using the configured weights.

This distinction prevents a weighted average from making a collision or land
crossing appear acceptable. Hard constraints are not high-cost choices; they
are removed from the navigable world.

**Scale warning: `ice_concentration` is a fraction from `0.0` to `1.0`, while
all risk values, including `total_risk`, are scores from `0.0` to `100.0`.**

### `GET /environment/risk`

The endpoint accepts `forecast_hour`, which defaults to `0`. Milestone 2 only
supports `forecast_hour=0`; any other value returns HTTP 400 rather than
silently serving the wrong time step.

```json
{
  "meta": {
    "scenario_id": "prydz-bay-demo-v1",
    "generated_at": "2026-01-01T00:00:00Z",
    "forecast_hour": 0,
    "bounds": {
      "lat_min": -69.5,
      "lat_max": -66.5,
      "lon_min": 71.0,
      "lon_max": 79.0
    },
    "grid": {
      "rows": 30,
      "cols": 30,
      "cell_height_km": 11.1195,
      "cell_width_km": 11.1078
    },
    "data_source": "synthetic",
    "risk_model_version": "v1"
  },
  "cells": [
    {
      "row": 12,
      "col": 14,
      "total_risk": 42.7,
      "is_navigable": true,
      "block_reason": null,
      "components": {
        "sea_ice": {"raw": 51.2, "weighted": 25.6},
        "iceberg": {
          "raw": 50.0,
          "weighted": 12.5,
          "nearest_iceberg_id": "IB-04"
        },
        "wind": {"raw": 28.0, "weighted": 4.2},
        "current": {"raw": 4.0, "weighted": 0.4}
      }
    }
  ],
  "summary": {
    "navigable_cells": 0,
    "blocked_cells": 0,
    "blocked_by": {
      "land": 0,
      "heavy_ice": 0,
      "iceberg_exclusion": 0
    },
    "mean_risk_navigable": 0.0,
    "max_risk_navigable": 0.0
  }
}
```

`block_reason` is exactly one of `"land"`, `"heavy_ice"`,
`"iceberg_exclusion"`, or `null`. If multiple constraints apply, the service
uses the stable precedence shown in that list. Blocked cells have
`total_risk: 100.0`, while their component audit trail remains populated where
computable.

`risk_model_version` identifies the formulas used to produce the response. It
must be incremented whenever a formula, hard-constraint rule, normalization, or
weighting interpretation changes.

### `GET /config/risk`

The endpoint returns the active `risk_model` configuration loaded once at API
startup:

```json
{
  "version": "v1",
  "weights": {
    "sea_ice": 0.5,
    "iceberg": 0.25,
    "wind": 0.15,
    "current": 0.1
  },
  "hard_constraints": {
    "max_ice_concentration": 0.8,
    "block_land": true,
    "iceberg_exclusion_uses_safety_buffer": true
  },
  "normalisation": {
    "sea_ice_block_threshold": 0.8,
    "wind_speed_ms_at_100": 25.0,
    "current_speed_ms_at_100": 1.5
  },
  "iceberg_proximity_km": [
    [3.0, 100.0],
    [5.0, 80.0],
    [10.0, 50.0],
    [20.0, 20.0],
    [30.0, 0.0]
  ]
}
```

These values are configurable prototype settings, not scientifically
calibrated operating limits.

## Milestones 3 and 4 routing contract

Routing uses the same named WGS 84 coordinate convention as the environment
contract. Bare coordinate arrays are never accepted. Routes are computed only
for `forecast_hour: 0`; other hours return HTTP 400 until forecasting exists.

### `POST /route`

Request:

```json
{
  "start": {"lat": -69.02, "lon": 72.10},
  "destination": {"lat": -66.92, "lon": 78.18},
  "mode": "balanced",
  "forecast_hour": 0
}
```

`mode` is required and must be exactly `"fastest"`, `"balanced"`, or
`"safest"`.

Successful response:

```json
{
  "success": true,
  "mode": "balanced",
  "alpha": 2.0,
  "forecast_hour": 0,
  "straight_line_km": 320.0,
  "route": [
    {"lat": -69.05, "lon": 72.2, "row": 4, "col": 4}
  ],
  "route_raw": [
    {"lat": -69.05, "lon": 72.2, "row": 4, "col": 4}
  ],
  "metrics": {
    "distance_km": 330.0,
    "eta_hours": 20.0,
    "risk_score": 25.0,
    "safety_score": 75.0,
    "mean_cell_risk": 20.0,
    "max_cell_risk": 32.5,
    "cells_traversed": 34,
    "fuel_index": 365.0,
    "fuel_vs_direct": 1.1
  },
  "search_stats": {
    "nodes_expanded": 250,
    "navigable_cells": 706,
    "blocked_cells": 194
  }
}
```

`route` is the line-of-sight-smoothed path and `route_raw` is the original
8-connected grid path. Every point uses named `lat`, `lon`, `row`, and `col`
fields. If a requested endpoint falls on a blocked cell and can be moved to a
navigable cell within the configured three-cell search radius, the response
adds `start_snapped_from` / `start_snapped_to` or
`destination_snapped_from` / `destination_snapped_to` objects. Snapping is
always reported and never silent.

No-route response remains HTTP 200 because it is a valid navigation result:

```json
{
  "success": false,
  "reason": "no_route_found",
  "message": "No navigable path exists between start and destination under the current risk surface.",
  "diagnostics": {
    "start_cell_navigable": true,
    "goal_cell_navigable": false,
    "goal_block_reason": "iceberg_exclusion",
    "nodes_expanded": 706
  }
}
```

Coordinates outside the scenario bounds, unsupported modes, and non-zero
forecast hours are request errors and return HTTP 400 with a clear message.

### Cost, heuristic, and safety metrics

For a segment of length `segment_km`, routing uses:

```text
risk_norm = mean(risk_from, risk_to) / 100
step_cost = segment_km * (1 + alpha * risk_norm)
heuristic = straight-line haversine distance to the goal
```

The heuristic is admissible because every edge multiplier is at least `1.0`,
so remaining route cost can never be less than straight-line distance.

Route risk combines both typical and peak exposure:

```text
risk_score = mean_weight * mean_cell_risk + max_weight * max_cell_risk
safety_score = 100 - risk_score
```

The two scores are exact complements. Reported route metrics are rounded to one
decimal place.

### Estimated Fuel Index

The API field `fuel_index` must be presented to users as **Estimated Fuel Index
(ice-adjusted km)**. It is calculated as:

```text
fuel_index = sum(segment_km * resistance_factor(mean_segment_ice))
fuel_vs_direct = fuel_index / straight_line_km
```

Every configured resistance factor is at least `1.0`; therefore
`fuel_index >= distance_km`. The index is a dimensionless ice-adjusted distance
proxy, **not litres, tonnes, fuel consumption, or measured fuel cost**.

### `POST /routes/compare`

Request uses the same fields as `POST /route` except `mode`:

```json
{
  "start": {"lat": -69.02, "lon": 72.10},
  "destination": {"lat": -66.92, "lon": 78.18},
  "forecast_hour": 0
}
```

Response:

```json
{
  "success": true,
  "forecast_hour": 0,
  "straight_line_km": 320.0,
  "routes": {
    "fastest": {"success": true, "mode": "fastest"},
    "balanced": {"success": true, "mode": "balanced"},
    "safest": {"success": true, "mode": "safest"}
  },
  "recommendation": {
    "mode": "balanced",
    "reason": "Balanced improves safety by 12.0 points over Fastest for 8.5% additional distance.",
    "rule_applied": "safety_gain_per_extra_km"
  },
  "comparison_table": [
    {
      "mode": "fastest",
      "distance_km": 325.0,
      "eta_hours": 18.0,
      "safety_score": 70.0,
      "fuel_index": 350.0,
      "fuel_vs_direct": 1.1
    }
  ]
}
```

The risk surface is computed once and reused for all three searches. A failed
mode retains its structured `success: false` result while other modes remain
available. Recommendations use only the configured deterministic rule; no LLM
or opaque selection is involved.
