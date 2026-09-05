"""Generic committed-route evaluation and forecast hazard detection."""

from __future__ import annotations

from typing import Any

from .grid import GridConfig, latlon_to_cell


def _grid_config(document: dict[str, Any]) -> GridConfig:
    meta = document["meta"]
    return GridConfig(**meta["bounds"], rows=meta["grid"]["rows"], cols=meta["grid"]["cols"])


def evaluate_route(
    route: list[dict[str, Any]],
    forecast_scenario: dict[str, Any],
    risk_grid: dict[str, Any],
    cfg: dict[str, Any],
    departure_hour: float = 0.0,
    forecast_data: dict[int, tuple[dict[str, Any], dict[str, Any]]] | None = None,
    time_offset_hours: float = 0.0,
) -> dict[str, Any]:
    """Score every supplied waypoint against one forecast snapshot."""
    grid = _grid_config(risk_grid)
    lookup = {(cell["row"], cell["col"]): cell for cell in risk_grid["cells"]}
    forecast_lookups = {
        hour: {(cell["row"], cell["col"]): cell for cell in data[1]["cells"]}
        for hour, data in (forecast_data or {}).items()
    }
    waypoints = []
    for index, point in enumerate(route):
        row, col = (point.get("row"), point.get("col"))
        if row is None or col is None:
            row, col = latlon_to_cell(float(point["lat"]), float(point["lon"]), grid)
        arrival_hour = float(point.get("arrival_hour") if point.get("arrival_hour") is not None else departure_hour + index)
        selected_hour = None
        if forecast_lookups:
            target_hour = arrival_hour + time_offset_hours
            selected_hour = min(forecast_lookups, key=lambda hour: (abs(hour - target_hour), hour))
            cell = forecast_lookups[selected_hour][(int(row), int(col))]
        else:
            cell = lookup[(int(row), int(col))]
        waypoints.append({
            "index": index,
            "lat": float(point["lat"]),
            "lon": float(point["lon"]),
            "row": int(row),
            "col": int(col),
            "arrival_hour": round(arrival_hour, 2),
            "forecast_hour_used": selected_hour if selected_hour is not None else forecast_scenario["meta"].get("forecast_hour", 0),
            "total_risk": float(cell["total_risk"]),
            "is_navigable": bool(cell["is_navigable"]),
            "block_reason": cell["block_reason"],
            "components": cell["components"],
        })
    risks = [point["total_risk"] for point in waypoints]
    mean_risk = sum(risks) / len(risks) if risks else 100.0
    max_risk = max(risks, default=100.0)
    weights = cfg["route_metrics"]
    risk_score = float(weights["mean_weight"]) * mean_risk + float(weights["max_weight"]) * max_risk
    return {
        "safety_score": round(100.0 - risk_score, 3),
        "risk_score": round(risk_score, 3),
        "mean_cell_risk": round(mean_risk, 3),
        "max_cell_risk": round(max_risk, 3),
        "blocked_waypoints": [point["index"] for point in waypoints if not point["is_navigable"]],
        "waypoints": waypoints,
    }


def detect_hazard(
    route: list[dict[str, Any]], base_eval: dict[str, Any], forecast_eval: dict[str, Any], cfg: dict[str, Any]
) -> dict[str, Any]:
    hazard_cfg = cfg["hazard"]
    drop = float(base_eval["safety_score"]) - float(forecast_eval["safety_score"])
    blocked = list(forecast_eval["blocked_waypoints"])
    triggers = []
    if blocked and bool(hazard_cfg["block_triggers_alert"]):
        triggers.append("cell_blocked")
    if forecast_eval["safety_score"] < float(hazard_cfg["min_safety_score"]):
        triggers.append("safety_floor")
    if drop > float(hazard_cfg["max_safety_drop"]):
        triggers.append("safety_drop")
    severity = "none"
    for label in ("advisory", "warning", "critical"):
        if drop >= float(hazard_cfg["severity_bands"][label]):
            severity = label
    if blocked:
        severity = "critical"
    elif triggers and severity == "none":
        severity = "advisory"
    first = blocked[0] if blocked else (max(range(len(forecast_eval["waypoints"])), key=lambda i: forecast_eval["waypoints"][i]["total_risk"]) if forecast_eval["waypoints"] else None)
    responsible = sorted({point["components"]["iceberg"].get("nearest_iceberg_id") for point in forecast_eval["waypoints"] if point["index"] in blocked and point["components"]["iceberg"].get("nearest_iceberg_id")})
    reason = "Committed route remains within configured safety limits."
    if triggers:
        reason = "Predicted conditions reduce committed-route safety."
    if blocked:
        reason = f"Predicted {forecast_eval['waypoints'][blocked[0]]['block_reason']} intersects committed route near waypoint {blocked[0]}."
    return {
        "alert": bool(triggers), "severity": severity, "reason": reason, "triggers": triggers,
        "original_safety": round(float(base_eval["safety_score"]), 1),
        "forecast_safety": round(float(forecast_eval["safety_score"]), 1),
        "safety_delta": round(-drop, 1),
        "first_conflict_waypoint_index": first,
        "first_conflict_hour": forecast_eval["waypoints"][first]["arrival_hour"] if first is not None else None,
        "blocked_waypoints": blocked,
        "responsible_icebergs": responsible,
    }
