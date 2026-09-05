"""Generate the deterministic Milestone 1 Antarctic engineering scenario."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine.geo import haversine_km  # noqa: E402
from engine.grid import GridConfig, cell_to_latlon  # noqa: E402

BOUNDS = {
    "lat_min": -69.5,
    "lat_max": -66.5,
    "lon_min": 71.0,
    "lon_max": 79.0,
}
GRID = GridConfig(**BOUNDS, rows=30, cols=30)
OUTPUT_PATH = Path(__file__).with_name("demo_scenario.json")


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _is_land(row: int, col: int) -> bool:
    """Return the synthetic hand-authored shelf/coast mask for the demo."""
    south_shelf_edge = 2 + round(1.2 * math.sin(col / 4.2))
    western_headland = col <= 3 and row <= 8 - col
    eastern_outcrop = col >= 26 and row <= 5 + (col - 26)
    return row <= south_shelf_edge or western_headland or eastern_outcrop


def _ice_concentration(row: int, col: int, is_land: bool) -> float:
    if is_land:
        return 0.0

    normalized_row = row / (GRID.rows - 1)
    heavy_band = 0.64 * math.exp(-((row - 15.0) / 4.8) ** 2)
    southern_pack = 0.24 * (1.0 - normalized_row)
    texture = 0.06 * math.sin(col / 3.1) + 0.035 * math.cos((row + col) / 4.7)

    lead_center_col = 4.0 + row * 0.72
    lead = 0.50 * math.exp(-((col - lead_center_col) / 2.0) ** 2)
    open_northeast = 0.18 * math.exp(-(((row - 25) / 5.5) ** 2 + ((col - 25) / 6.0) ** 2))

    concentration = 0.08 + southern_pack + heavy_band + texture - lead - open_northeast
    return round(_clamp(concentration, 0.0, 0.96), 3)


def _environment_cell(row: int, col: int) -> dict[str, Any]:
    lat, lon = cell_to_latlon(row, col, GRID)
    land = _is_land(row, col)
    return {
        "row": row,
        "col": col,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "ice_concentration": _ice_concentration(row, col, land),
        "wind_speed_ms": round(7.2 + 2.1 * math.sin(row / 5.5) + 1.3 * math.cos(col / 6.0), 2),
        "wind_direction_deg": round((62.0 + row * 2.7 + col * 1.9) % 360.0, 1),
        "current_speed_ms": round(0.24 + 0.08 * math.sin(col / 4.5) + 0.04 * math.cos(row / 5.0), 3),
        "current_direction_deg": round((18.0 + row * 1.4 - col * 1.1) % 360.0, 1),
        "is_land": land,
        "is_navigable": not land,
    }


def build_scenario() -> dict[str, Any]:
    """Build the complete deterministic scenario in memory."""
    midpoint_lat = (GRID.lat_min + GRID.lat_max) / 2.0
    midpoint_lon = (GRID.lon_min + GRID.lon_max) / 2.0
    cell_height_km = haversine_km(
        midpoint_lat - GRID.cell_height_deg / 2.0,
        midpoint_lon,
        midpoint_lat + GRID.cell_height_deg / 2.0,
        midpoint_lon,
    )
    cell_width_km = haversine_km(
        midpoint_lat,
        midpoint_lon - GRID.cell_width_deg / 2.0,
        midpoint_lat,
        midpoint_lon + GRID.cell_width_deg / 2.0,
    )

    icebergs = [
        ("IB-04", -68.78, 72.82, 0.62, 31.0, 1.2, 2.8),
        ("IB-02", -67.86, 75.36, 0.44, 82.0, 1.8, 3.4),
        ("IB-03", -67.92, 73.25, 0.71, 18.0, 1.0, 2.5),
        ("IB-01", -68.32, 74.32, 0.83, 58.0, 2.0, 4.0),
        ("IB-05", -67.42, 76.18, 0.35, 112.0, 1.4, 3.0),
        ("IB-06", -68.52, 77.22, 0.56, 335.0, 1.6, 3.2),
        ("IB-07", -67.16, 77.48, 0.48, 74.0, 0.9, 2.3),
        ("IB-08", -68.08, 78.12, 0.67, 296.0, 1.3, 2.9),
    ]

    return {
        "meta": {
            "scenario_id": "prydz-bay-demo-v1",
            "generated_at": "2026-01-01T00:00:00Z",
            "forecast_hour": 0,
            "bounds": BOUNDS,
            "grid": {
                "rows": GRID.rows,
                "cols": GRID.cols,
                "cell_height_km": round(cell_height_km, 4),
                "cell_width_km": round(cell_width_km, 4),
            },
            "data_source": "synthetic",
        },
        "vessel": {
            "id": "RV-01",
            "name": "Research Vessel",
            "lat": -69.02,
            "lon": 72.10,
            "speed_knots_open_water": 12.0,
        },
        "destination": {
            "name": "Bharati approach",
            "lat": -66.92,
            "lon": 78.18,
        },
        "icebergs": [
            {
                "id": iceberg_id,
                "lat": lat,
                "lon": lon,
                "velocity_kmh": velocity_kmh,
                "heading_deg": heading_deg,
                "radius_km": radius_km,
                "safety_buffer_km": safety_buffer_km,
            }
            for iceberg_id, lat, lon, velocity_kmh, heading_deg, radius_km, safety_buffer_km in icebergs
        ],
        "cells": [
            _environment_cell(row, col)
            for row in range(GRID.rows)
            for col in range(GRID.cols)
        ],
    }


def write_scenario(output_path: Path = OUTPUT_PATH) -> Path:
    """Write stable, human-readable JSON and return its path."""
    output_path.write_text(
        json.dumps(build_scenario(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


if __name__ == "__main__":
    generated_path = write_scenario()
    print(f"Generated deterministic scenario: {generated_path}")
