"""Pure navigation-risk calculations for the deterministic Antarctic demo.

The module performs no file or network I/O and stores no mutable global state.
All prototype thresholds and weights arrive through ``cfg``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .geo import haversine_km


def _clamp_risk(value: float) -> float:
    return max(0.0, min(100.0, value))


def sea_ice_risk(ice_concentration: float, cfg: dict[str, Any]) -> float:
    """Return ``100 * concentration / block_threshold``, clamped to 0-100.

    This is a linear prototype mapping. Real ice-navigation risk additionally
    depends on ice type, thickness, floe size, ridging, and vessel ice class,
    none of which this prototype models.
    """
    threshold = float(cfg["normalisation"]["sea_ice_block_threshold"])
    return _clamp_risk(100.0 * float(ice_concentration) / threshold)


def iceberg_risk(
    cell_lat: float,
    cell_lon: float,
    icebergs: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> tuple[float, str | None]:
    """Return linearly interpolated proximity risk and the nearest iceberg ID.

    Distance is measured from the cell centre to the iceberg edge:
    ``haversine_km(cell, iceberg) - radius_km``. Risk is interpolated between
    the configured ``(edge_distance_km, risk)`` breakpoints, remains at the
    first risk below the first distance, and is zero beyond the last distance.
    """
    if not icebergs:
        return 0.0, None

    nearest_iceberg = min(
        icebergs,
        key=lambda iceberg: haversine_km(
            cell_lat,
            cell_lon,
            float(iceberg["lat"]),
            float(iceberg["lon"]),
        )
        - float(iceberg["radius_km"]),
    )
    edge_distance_km = haversine_km(
        cell_lat,
        cell_lon,
        float(nearest_iceberg["lat"]),
        float(nearest_iceberg["lon"]),
    ) - float(nearest_iceberg["radius_km"])
    breakpoints = [
        (float(distance), float(risk))
        for distance, risk in cfg["iceberg_proximity_km"]
    ]

    if edge_distance_km <= breakpoints[0][0]:
        risk_value = breakpoints[0][1]
    else:
        risk_value = 0.0
        for (near_distance, near_risk), (far_distance, far_risk) in zip(
            breakpoints, breakpoints[1:]
        ):
            if edge_distance_km <= far_distance:
                fraction = (edge_distance_km - near_distance) / (
                    far_distance - near_distance
                )
                risk_value = near_risk + fraction * (far_risk - near_risk)
                break

    return _clamp_risk(risk_value), str(nearest_iceberg["id"])


def wind_risk(wind_speed_ms: float, cfg: dict[str, Any]) -> float:
    """Return wind speed divided by its configured 100-risk ceiling, times 100.

    The ceiling is a configurable prototype value, not a calibrated operating
    limit.
    """
    ceiling = float(cfg["normalisation"]["wind_speed_ms_at_100"])
    return _clamp_risk(100.0 * float(wind_speed_ms) / ceiling)


def current_risk(current_speed_ms: float, cfg: dict[str, Any]) -> float:
    """Return current speed divided by its configured 100-risk ceiling, times 100.

    The ceiling is a configurable prototype value, not a calibrated operating
    limit.
    """
    ceiling = float(cfg["normalisation"]["current_speed_ms_at_100"])
    return _clamp_risk(100.0 * float(current_speed_ms) / ceiling)


def is_navigable(
    cell: dict[str, Any],
    icebergs: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> tuple[bool, str | None]:
    """Apply land, heavy-ice, then iceberg-exclusion hard constraints."""
    constraints = cfg["hard_constraints"]
    if constraints["block_land"] and bool(cell["is_land"]):
        return False, "land"

    if float(cell["ice_concentration"]) >= float(
        constraints["max_ice_concentration"]
    ):
        return False, "heavy_ice"

    include_buffer = bool(constraints["iceberg_exclusion_uses_safety_buffer"])
    for iceberg in icebergs:
        exclusion_radius_km = float(iceberg["radius_km"])
        if include_buffer:
            exclusion_radius_km += float(iceberg["safety_buffer_km"])
        centre_distance_km = haversine_km(
            float(cell["lat"]),
            float(cell["lon"]),
            float(iceberg["lat"]),
            float(iceberg["lon"]),
        )
        if centre_distance_km <= exclusion_radius_km:
            return False, "iceberg_exclusion"

    return True, None


def cell_risk(
    cell: dict[str, Any],
    icebergs: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """Return hard navigability and a complete weighted soft-risk audit trail."""
    sea_ice_raw = sea_ice_risk(float(cell["ice_concentration"]), cfg)
    iceberg_raw, nearest_iceberg_id = iceberg_risk(
        float(cell["lat"]), float(cell["lon"]), icebergs, cfg
    )
    wind_raw = wind_risk(float(cell["wind_speed_ms"]), cfg)
    current_raw = current_risk(float(cell["current_speed_ms"]), cfg)

    weights = cfg["weights"]
    component_values = {
        "sea_ice": (sea_ice_raw, float(weights["sea_ice"])),
        "iceberg": (iceberg_raw, float(weights["iceberg"])),
        "wind": (wind_raw, float(weights["wind"])),
        "current": (current_raw, float(weights["current"])),
    }
    components: dict[str, dict[str, Any]] = {}
    soft_scale = float(cfg.get("soft_risk_scale", 1.0))
    for name, (raw_value, weight) in component_values.items():
        components[name] = {
            "raw": round(_clamp_risk(raw_value), 3),
            "weighted": round(_clamp_risk(raw_value) * weight * soft_scale, 3),
        }
    components["iceberg"]["nearest_iceberg_id"] = nearest_iceberg_id

    navigable, block_reason = is_navigable(cell, icebergs, cfg)
    weighted_total = sum(
        component["weighted"] for component in components.values()
    )
    if not navigable:
        responsible_factor = "iceberg" if block_reason == "iceberg_exclusion" else "sea_ice"
        components[responsible_factor]["weighted"] = round(
            components[responsible_factor]["weighted"] + (100.0 - weighted_total), 3
        )
        components[responsible_factor]["hard_constraint_penalty"] = round(100.0 - weighted_total, 3)
        weighted_total = 100.0
    return {
        "row": int(cell["row"]),
        "col": int(cell["col"]),
        "total_risk": 100.0 if not navigable else round(_clamp_risk(weighted_total), 3),
        "is_navigable": navigable,
        "block_reason": block_reason,
        "components": components,
    }


def compute_risk_grid(
    scenario: dict[str, Any], cfg: dict[str, Any]
) -> dict[str, Any]:
    """Compute all cell risks plus deterministic grid-level summary statistics."""
    risk_cells = [cell_risk(cell, scenario["icebergs"], cfg) for cell in scenario["cells"]]
    navigable_risks = [
        cell["total_risk"] for cell in risk_cells if cell["is_navigable"]
    ]
    blocked_by = {"land": 0, "heavy_ice": 0, "iceberg_exclusion": 0}
    for cell in risk_cells:
        if cell["block_reason"] is not None:
            blocked_by[cell["block_reason"]] += 1

    meta = deepcopy(scenario["meta"])
    meta["risk_model_version"] = str(cfg["version"])
    return {
        "meta": meta,
        "cells": risk_cells,
        "summary": {
            "navigable_cells": len(navigable_risks),
            "blocked_cells": len(risk_cells) - len(navigable_risks),
            "blocked_by": blocked_by,
            "mean_risk_navigable": round(
                sum(navigable_risks) / len(navigable_risks), 3
            )
            if navigable_risks
            else 0.0,
            "max_risk_navigable": round(max(navigable_risks), 3)
            if navigable_risks
            else 0.0,
        },
    }
