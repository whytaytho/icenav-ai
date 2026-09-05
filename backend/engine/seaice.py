"""First-order deterministic sea-ice concentration advection.

Sea ice is backtraced with current plus a configurable fraction of wind, then
bilinearly sampled and mildly diffused. Wind/current remain constant over every
horizon. This omits internal stress, ice-ocean drag detail, and Coriolis effects;
it is a visual engineering forecast, not operational sea-ice physics.
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from .geo import MPS_TO_KMH
from .iceberg import to_components


def _sample(values: list[list[float]], row: float, col: float) -> float:
    rows, cols = len(values), len(values[0])
    row = min(max(row, 0.0), rows - 1.0)
    col = min(max(col, 0.0), cols - 1.0)
    r0, c0 = int(math.floor(row)), int(math.floor(col))
    r1, c1 = min(r0 + 1, rows - 1), min(c0 + 1, cols - 1)
    fr, fc = row - r0, col - c0
    return (
        values[r0][c0] * (1 - fr) * (1 - fc)
        + values[r1][c0] * fr * (1 - fc)
        + values[r0][c1] * (1 - fr) * fc
        + values[r1][c1] * fr * fc
    )


def advect_seaice(scenario: dict[str, Any], hours: float, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    forecast_cfg = cfg["forecast"]
    cells = deepcopy(scenario["cells"])
    if hours <= 0 or not bool(forecast_cfg.get("advection_enabled", True)):
        return cells
    rows, cols = scenario["meta"]["grid"]["rows"], scenario["meta"]["grid"]["cols"]
    height_km = float(scenario["meta"]["grid"]["cell_height_km"])
    width_km = float(scenario["meta"]["grid"]["cell_width_km"])
    values = [[0.0 for _ in range(cols)] for _ in range(rows)]
    for cell in scenario["cells"]:
        values[cell["row"]][cell["col"]] = float(cell["ice_concentration"])
    advected = [[0.0 for _ in range(cols)] for _ in range(rows)]
    wind_factor = float(forecast_cfg["seaice_wind_factor"])
    for cell in cells:
        row, col = cell["row"], cell["col"]
        if cell["is_land"]:
            advected[row][col] = values[row][col]
            continue
        wind_e, wind_n = to_components(cell["wind_speed_ms"], cell["wind_direction_deg"])
        current_e, current_n = to_components(cell["current_speed_ms"], cell["current_direction_deg"])
        east_km = (current_e + wind_factor * wind_e) * MPS_TO_KMH * hours
        north_km = (current_n + wind_factor * wind_n) * MPS_TO_KMH * hours
        advected[row][col] = _sample(values, row - north_km / height_km, col - east_km / width_km)
    diffusion = float(forecast_cfg.get("seaice_diffusion", 0.0))
    for cell in cells:
        row, col = cell["row"], cell["col"]
        if cell["is_land"]:
            continue
        neighbours = [advected[r][c] for r in range(max(0, row - 1), min(rows, row + 2)) for c in range(max(0, col - 1), min(cols, col + 2)) if not cells[r * cols + c]["is_land"]]
        smooth = sum(neighbours) / len(neighbours)
        value = (1 - diffusion) * advected[row][col] + diffusion * smooth
        cell["ice_concentration"] = round(min(1.0, max(0.0, value)), 3)
        cell["is_navigable"] = cell["ice_concentration"] < float(cfg["risk_model"]["hard_constraints"]["max_ice_concentration"])
    return cells
