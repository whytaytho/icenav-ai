# ICE-NAV AI Milestone 1 Data Contract

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
