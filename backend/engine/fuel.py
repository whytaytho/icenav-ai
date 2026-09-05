"""Estimated Fuel Index calculations for ICE-NAV route comparisons.

The index is an ice-adjusted distance proxy. It is not a marine engine model
and must never be presented as litres, tonnes, or measured fuel consumption.
"""

from __future__ import annotations

from typing import Any

from .geo import haversine_km
from .grid import GridConfig, cell_to_latlon


def resistance_factor(ice_concentration: float, cfg: dict[str, Any]) -> float:
    """Linearly interpolate the configured ice-resistance multiplier.

    Values below the first concentration use the first factor and values above
    the final breakpoint use the final factor. Configuration validation ensures
    every factor is at least 1.0.
    """
    breakpoints = [
        (float(concentration), float(factor))
        for concentration, factor in cfg["fuel_model"]["resistance_by_ice"]
    ]
    concentration = float(ice_concentration)
    if concentration <= breakpoints[0][0]:
        return breakpoints[0][1]

    for (low_ice, low_factor), (high_ice, high_factor) in zip(
        breakpoints, breakpoints[1:]
    ):
        if concentration <= high_ice:
            fraction = (concentration - low_ice) / (high_ice - low_ice)
            return low_factor + fraction * (high_factor - low_factor)
    return breakpoints[-1][1]


def fuel_index(
    path: list[tuple[int, int]],
    risk_grid: dict[str, Any],
    cfg: dict[str, Any],
    start_latlon: tuple[float, float] | None = None,
    goal_latlon: tuple[float, float] | None = None,
) -> float:
    """Return the sum of segment km times mean-segment ice resistance."""
    if len(path) < 2:
        return 0.0

    meta = risk_grid["meta"]
    grid_cfg = GridConfig(
        **meta["bounds"],
        rows=int(meta["grid"]["rows"]),
        cols=int(meta["grid"]["cols"]),
    )
    cells = {(cell["row"], cell["col"]): cell for cell in risk_grid["cells"]}
    total = 0.0
    for segment_index, (start, end) in enumerate(zip(path, path[1:])):
        start_lat, start_lon = cell_to_latlon(*start, grid_cfg)
        end_lat, end_lon = cell_to_latlon(*end, grid_cfg)
        if segment_index == 0 and start_latlon is not None:
            start_lat, start_lon = start_latlon
        if segment_index == len(path) - 2 and goal_latlon is not None:
            end_lat, end_lon = goal_latlon
        segment_km = haversine_km(start_lat, start_lon, end_lat, end_lon)
        mean_ice = (
            float(cells[start]["ice_concentration"])
            + float(cells[end]["ice_concentration"])
        ) / 2.0
        total += segment_km * resistance_factor(mean_ice, cfg)
    return total


def fuel_metrics(
    path: list[tuple[int, int]],
    risk_grid: dict[str, Any],
    straight_line_km: float,
    cfg: dict[str, Any],
    start_latlon: tuple[float, float] | None = None,
    goal_latlon: tuple[float, float] | None = None,
) -> dict[str, float]:
    """Return fuel index and its ratio to direct geodesic distance."""
    index = fuel_index(
        path,
        risk_grid,
        cfg,
        start_latlon=start_latlon,
        goal_latlon=goal_latlon,
    )
    return {
        "fuel_index": index,
        "fuel_vs_direct": index / straight_line_km if straight_line_km > 0.0 else 0.0,
    }
