"""Deterministic arithmetic explanations derived from risk components."""

from __future__ import annotations

from typing import Any

FACTOR_LABELS = {"sea_ice": "Sea-ice concentration", "iceberg": "Iceberg proximity", "wind": "Wind", "current": "Current"}


def explain_route_change(
    base_eval: dict[str, Any], forecast_eval: dict[str, Any], hazard: dict[str, Any],
    recommended_route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    indices = hazard.get("blocked_waypoints") or [hazard.get("first_conflict_waypoint_index")]
    indices = [index for index in indices if index is not None and index < len(base_eval["waypoints"])]
    if not indices:
        indices = list(range(min(len(base_eval["waypoints"]), len(forecast_eval["waypoints"]))))
    contributors = []
    for factor, label in FACTOR_LABELS.items():
        before_values = [base_eval["waypoints"][index]["components"][factor]["weighted"] for index in indices]
        after_values = [forecast_eval["waypoints"][index]["components"][factor]["weighted"] for index in indices]
        before = sum(before_values) / len(before_values)
        after = sum(after_values) / len(after_values)
        entity = None
        if factor == "iceberg":
            ids = [forecast_eval["waypoints"][index]["components"][factor].get("nearest_iceberg_id") for index in indices]
            entity = next((item for item in ids if item), None)
        contributors.append({"factor": f"Iceberg {entity}" if factor == "iceberg" and entity else label, "key": factor, "impact": round(after - before, 3), "detail": f"weighted contribution {before:.2f} -> {after:.2f}"})
    contributors.sort(key=lambda item: abs(item["impact"]), reverse=True)
    primary = contributors[0]
    primary_entity = primary["factor"].split(" ", 1)[1] if primary["key"] == "iceberg" and " " in primary["factor"] else None
    total_delta = round(sum(item["impact"] for item in contributors), 3)
    recommended_metrics = recommended_route.get("metrics", {}) if recommended_route else {}
    return {
        "route_change": {
            "primary_reason": FACTOR_LABELS[primary["key"]], "primary_entity": primary_entity,
            "summary": f"{primary['factor']} is the largest measured contributor to the forecast risk change.",
            "contributors": contributors, "total_risk_delta": total_delta,
            "original_safety": hazard["original_safety"], "forecast_safety": hazard["forecast_safety"],
            "recommended_safety": recommended_metrics.get("safety_score"),
            "additional_distance_km": None, "additional_time_hours": None, "additional_fuel_index": None,
        }
    }
