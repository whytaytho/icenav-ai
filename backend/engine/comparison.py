"""Pure three-mode route comparison and deterministic recommendation rules."""

from __future__ import annotations

from typing import Any

from .geo import haversine_km
from .routing import plan_route

MODE_ORDER = ("fastest", "balanced", "safest")


def recommendation_for_routes(
    routes: dict[str, dict[str, Any]], cfg: dict[str, Any]
) -> dict[str, Any] | None:
    """Recommend a successful route using the configured inspectable rule."""
    successful = {
        mode: routes[mode]
        for mode in MODE_ORDER
        if mode in routes and routes[mode].get("success")
    }
    if not successful:
        return None

    recommendation_cfg = cfg["recommendation"]
    safety_floor = float(recommendation_cfg["min_safety_score"])
    minimum_gain = float(recommendation_cfg["min_safety_gain"])
    maximum_extra_pct = float(recommendation_cfg["max_extra_distance_pct"])
    qualifying = [
        mode
        for mode in MODE_ORDER
        if mode in successful
        and float(successful[mode]["metrics"]["safety_score"]) >= safety_floor
    ]

    if not qualifying:
        selected_mode = max(
            successful,
            key=lambda mode: (
                float(successful[mode]["metrics"]["safety_score"]),
                -MODE_ORDER.index(mode),
            ),
        )
        selected_safety = float(
            successful[selected_mode]["metrics"]["safety_score"]
        )
        return {
            "mode": selected_mode,
            "reason": (
                f"{selected_mode.title()} has the highest available safety score "
                f"at {selected_safety:.1f}, but no route meets the "
                f"{safety_floor:.1f} safety floor."
            ),
            "rule_applied": str(recommendation_cfg["rule"]),
            "warning": "No available route meets the configured safety floor.",
        }

    fastest_baseline = successful.get("fastest", successful[qualifying[0]])
    fastest_distance = float(fastest_baseline["metrics"]["distance_km"])
    incumbent = qualifying[0]
    decisions: list[tuple[str, str, float, float]] = []

    for candidate in qualifying[1:]:
        incumbent_safety = float(
            successful[incumbent]["metrics"]["safety_score"]
        )
        candidate_safety = float(
            successful[candidate]["metrics"]["safety_score"]
        )
        safety_gain = candidate_safety - incumbent_safety
        candidate_distance = float(
            successful[candidate]["metrics"]["distance_km"]
        )
        extra_distance_pct = (
            100.0 * (candidate_distance - fastest_distance) / fastest_distance
            if fastest_distance > 0.0
            else 0.0
        )
        decisions.append(
            (incumbent, candidate, safety_gain, extra_distance_pct)
        )
        if safety_gain >= minimum_gain and extra_distance_pct <= maximum_extra_pct:
            incumbent = candidate

    if incumbent == qualifying[0]:
        if decisions:
            _, candidate, safety_gain, extra_distance_pct = decisions[0]
            reason = (
                f"{incumbent.title()} meets the {safety_floor:.1f} safety floor; "
                f"{candidate.title()} gains {safety_gain:.1f} safety points for "
                f"{extra_distance_pct:.1f}% additional distance, below the configured upgrade rule."
            )
        else:
            safety = float(successful[incumbent]["metrics"]["safety_score"])
            reason = (
                f"{incumbent.title()} is the only available route meeting the "
                f"{safety_floor:.1f} safety floor, with a score of {safety:.1f}."
            )
    else:
        selected_index = qualifying.index(incumbent)
        previous = qualifying[selected_index - 1]
        safety_gain = (
            float(successful[incumbent]["metrics"]["safety_score"])
            - float(successful[previous]["metrics"]["safety_score"])
        )
        selected_distance = float(
            successful[incumbent]["metrics"]["distance_km"]
        )
        extra_distance_pct = (
            100.0 * (selected_distance - fastest_distance) / fastest_distance
            if fastest_distance > 0.0
            else 0.0
        )
        reason = (
            f"{incumbent.title()} improves safety by {safety_gain:.1f} points "
            f"over {previous.title()} for {extra_distance_pct:.1f}% additional "
            "distance relative to Fastest."
        )

    return {
        "mode": incumbent,
        "reason": reason,
        "rule_applied": str(recommendation_cfg["rule"]),
    }


def comparison_table(routes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Return compact metrics for every successful mode in stable mode order."""
    table = []
    for mode in MODE_ORDER:
        route = routes.get(mode)
        if not route or not route.get("success"):
            continue
        metrics = route["metrics"]
        table.append(
            {
                "mode": mode,
                "distance_km": metrics["distance_km"],
                "eta_hours": metrics["eta_hours"],
                "risk_score": metrics["risk_score"],
                "safety_score": metrics["safety_score"],
                "fuel_index": metrics["fuel_index"],
                "fuel_vs_direct": metrics["fuel_vs_direct"],
            }
        )
    return table


def compare_routes(
    scenario: dict[str, Any],
    risk_grid: dict[str, Any],
    start_latlon: tuple[float, float],
    goal_latlon: tuple[float, float],
    cfg: dict[str, Any],
    forecast_data: dict[int, tuple[dict[str, Any], dict[str, Any]]] | None = None,
    departure_hour: float = 0.0,
) -> dict[str, Any]:
    """Plan all configured modes against one precomputed risk surface."""
    routes = {
        mode: plan_route(
            scenario,
            risk_grid,
            start_latlon,
            goal_latlon,
            float(cfg["route_modes"][mode]["alpha"]),
            cfg,
            mode=mode,
            forecast_data=forecast_data,
            departure_hour=departure_hour,
        )
        for mode in MODE_ORDER
    }
    straight_line_km = haversine_km(*start_latlon, *goal_latlon)
    successful = any(route.get("success") for route in routes.values())
    return {
        "success": successful,
        "forecast_hour": int(scenario["meta"].get("forecast_hour", 0)),
        "straight_line_km": round(straight_line_km, 1),
        "routes": routes,
        "recommendation": recommendation_for_routes(routes, cfg),
        "comparison_table": comparison_table(routes),
    }
