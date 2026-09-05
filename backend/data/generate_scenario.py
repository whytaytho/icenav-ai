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


# --------------------------------------------------------------------------
# Scenario geometry
#
# The corridor is deliberately shaped so the demonstration has something to
# decide about. A thick, largely impassable ice band lies across the middle of
# the corridor, pierced by TWO navigable leads:
#
#   * the PRIMARY lead follows the direct vessel-to-destination line, and is
#     the passage a distance-biased route naturally takes;
#   * the SECONDARY lead bows east of it through the same band, rejoining at
#     both ends, and is longer but stays open.
#
# IB-04 sits west of the primary lead and drifts east into it, so within a few
# forecast hours the short passage closes while the eastern one remains
# navigable. That is what gives the reroute somewhere genuinely better to go.
#
# Nothing here special-cases the demo: the alert, the reroute, and the
# explanation are all produced by the same generic risk and routing engine
# used for any scenario. This module only places geography.
# --------------------------------------------------------------------------

# Vessel enters near (row 4, col 4) and exits near (row 25, col 26); the
# primary lead is drawn along that line.
LEAD_START_ROW = 4.0
LEAD_START_COL = 4.0
LEAD_COLS_PER_ROW = 1.05

# How far east the secondary lead bows away from the primary one, and over
# what span of rows the two are separated.
SECONDARY_LEAD_OFFSET_COLS = 4.0
SECONDARY_LEAD_CENTER_ROW = 15.5
SECONDARY_LEAD_SPREAD_ROWS = 4.5

# The ice band. Amplitude exceeds the 0.80 hard-block threshold so its core is
# genuinely impassable rather than merely expensive.
BAND_CENTER_ROW = 15.0
BAND_AMPLITUDE = 0.95
BAND_SPREAD_ROWS = 3.1

# Lead depth slightly exceeds band amplitude so lead centres are near open
# water. The primary lead is deliberately the NARROWER of the two: holding it
# costs more worst-cell exposure, which is what gives a risk-averse route a
# reason to prefer the longer eastern passage. Without that asymmetry all
# three modes collapse onto the same path.
PRIMARY_LEAD_DEPTH = 0.88
PRIMARY_LEAD_WIDTH_COLS = 2.4
SECONDARY_LEAD_DEPTH = 1.02
SECONDARY_LEAD_WIDTH_COLS = 3.4


def _is_land(row: int, col: int) -> bool:
    """Return the synthetic hand-authored shelf/coast mask for the demo."""
    south_shelf_edge = 2 + round(1.2 * math.sin(col / 4.2))
    western_headland = col <= 3 and row <= 8 - col
    eastern_outcrop = col >= 26 and row <= 5 + (col - 26)
    return row <= south_shelf_edge or western_headland or eastern_outcrop


def _primary_lead_col(row: float) -> float:
    """Column centre of the direct passage at a given row."""
    return LEAD_START_COL + (row - LEAD_START_ROW) * LEAD_COLS_PER_ROW


def _secondary_lead_col(row: float) -> float:
    """Column centre of the eastern bypass, which rejoins at both ends."""
    divergence = math.exp(
        -(((row - SECONDARY_LEAD_CENTER_ROW) / SECONDARY_LEAD_SPREAD_ROWS) ** 2)
    )
    return _primary_lead_col(row) + SECONDARY_LEAD_OFFSET_COLS * divergence


def _lead_relief(row: int, col: int) -> float:
    """Combined ice reduction from both leads at a cell."""
    primary = PRIMARY_LEAD_DEPTH * math.exp(
        -(((col - _primary_lead_col(row)) / PRIMARY_LEAD_WIDTH_COLS) ** 2)
    )
    secondary = SECONDARY_LEAD_DEPTH * math.exp(
        -(((col - _secondary_lead_col(row)) / SECONDARY_LEAD_WIDTH_COLS) ** 2)
    )
    return max(primary, secondary)


def _ice_concentration(row: int, col: int, is_land: bool) -> float:
    if is_land:
        return 0.0

    normalized_row = row / (GRID.rows - 1)
    heavy_band = BAND_AMPLITUDE * math.exp(
        -(((row - BAND_CENTER_ROW) / BAND_SPREAD_ROWS) ** 2)
    )
    southern_pack = 0.08 * (1.0 - normalized_row)
    texture = 0.022 * math.sin(col / 3.1) + 0.018 * math.cos((row + col) / 4.7)
    open_northeast = 0.05 * math.exp(
        -(((row - 25) / 5.5) ** 2 + ((col - 25) / 6.0) ** 2)
    )

    concentration = (
        0.035
        + southern_pack
        + heavy_band
        + texture
        - _lead_relief(row, col)
        - open_northeast
    )
    return round(_clamp(concentration, 0.0, 0.96), 3)


def _current_vector(row: int, col: int) -> tuple[float, float]:
    """Return (east, north) current components in m/s.

    Ambient flow is weak and broadly eastward. A localised eastward jet sits
    over the western approach to the primary lead; it is what carries IB-04
    into the channel over the forecast horizons. Coastal jets of this order
    are physically unremarkable, but the placement here is chosen for the
    demonstration and is not an observed current field.
    """
    ambient_east = 0.11 + 0.03 * math.sin(col / 4.5)
    ambient_north = 0.03 * math.cos(row / 5.0)

    jet = 0.46 * math.exp(
        -((((row - 14.0) / 5.0) ** 2) + (((col - 12.0) / 4.0) ** 2))
    )
    return ambient_east + jet, ambient_north


def _environment_cell(row: int, col: int) -> dict[str, Any]:
    lat, lon = cell_to_latlon(row, col, GRID)
    land = _is_land(row, col)
    east, north = _current_vector(row, col)
    current_speed = math.hypot(east, north)
    current_direction = math.degrees(math.atan2(east, north)) % 360.0
    return {
        "row": row,
        "col": col,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "ice_concentration": _ice_concentration(row, col, land),
        "wind_speed_ms": round(4.1 + 1.1 * math.sin(row / 5.5) + 0.7 * math.cos(col / 6.0), 2),
        "wind_direction_deg": round((78.0 + row * 1.6 + col * 1.1) % 360.0, 1),
        "current_speed_ms": round(current_speed, 3),
        "current_direction_deg": round(current_direction, 1),
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

    # (id, lat, lon, velocity_kmh, heading_deg, radius_km, safety_buffer_km)
    #
    # IB-04 is the demonstration hazard. It sits west of the primary lead at
    # roughly the midpoint of the voyage, inside the eastward current jet, so
    # over the forecast horizons it drifts across the channel the direct route
    # depends on. Its exclusion radius is large because it is a substantial
    # tabular berg; every other berg is placed clear of both leads so the
    # planned route starts genuinely low-risk.
    icebergs = [
        ("IB-04", -67.98, 74.55, 0.58, 92.0, 5.0, 11.0),
        ("IB-01", -68.94, 76.90, 0.41, 145.0, 1.9, 4.0),
        ("IB-02", -67.20, 72.30, 0.44, 82.0, 1.8, 3.4),
        ("IB-03", -66.75, 74.05, 0.52, 18.0, 1.4, 3.0),
        ("IB-05", -69.10, 74.60, 0.35, 112.0, 1.4, 3.0),
        ("IB-06", -68.60, 78.55, 0.56, 335.0, 1.6, 3.2),
        ("IB-07", -66.70, 76.60, 0.48, 74.0, 0.9, 2.3),
        ("IB-08", -69.22, 77.90, 0.67, 296.0, 1.3, 2.9),
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
