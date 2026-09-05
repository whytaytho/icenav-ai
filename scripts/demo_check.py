"""Measure the numbers the live demo depends on, without starting a server.

Run this after any change to the scenario, the risk model, or the routing
configuration. It prints the figures a judge actually sees, so the presentation
can never drift away from what the engine really produces.

    python scripts/demo_check.py

Exit status is non-zero when a demo-critical expectation fails, which makes it
usable as a pre-presentation smoke test.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.api.forecast import ForecastCache  # noqa: E402
from backend.engine.comparison import compare_routes  # noqa: E402
from backend.engine.explain import explain_route_change  # noqa: E402
from backend.engine.hazard import (  # noqa: E402
    detect_hazard,
    evaluate_route,
    remaining_route_metrics,
)
from backend.engine.routing import plan_route  # noqa: E402
from backend.main import CONFIG_PATH, load_app_config, load_scenario  # noqa: E402


def _fmt(value: Any, width: int = 7, places: int = 1) -> str:
    if value is None:
        return "n/a".rjust(width)
    return f"{float(value):{width}.{places}f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hour",
        type=int,
        default=6,
        help="forecast hour used for the headline reroute check (default: 6)",
    )
    args = parser.parse_args()

    config = load_app_config(CONFIG_PATH)
    scenario = load_scenario()
    forecasts = ForecastCache(scenario, config)

    vessel = scenario["vessel"]
    destination = scenario["destination"]
    start = (float(vessel["lat"]), float(vessel["lon"]))
    goal = (float(destination["lat"]), float(destination["lon"]))

    failures: list[str] = []

    # ---------------------------------------------------------------- T+0 modes
    comparison = compare_routes(
        forecasts.scenario(0),
        forecasts.risk(0),
        start,
        goal,
        config,
        forecast_data=None,
        departure_hour=0.0,
    )
    print("=" * 68)
    print("T+0 ROUTE COMPARISON")
    print("=" * 68)
    print(f"  straight line: {comparison['straight_line_km']:.1f} km")
    print(f"  {'mode':9s} {'dist km':>8s} {'eta h':>7s} {'safety':>7s} {'fuel':>8s} {'detour':>7s}")
    table = {row["mode"]: row for row in comparison["comparison_table"]}
    for mode in ("fastest", "balanced", "safest"):
        row = table.get(mode)
        if row is None:
            failures.append(f"mode {mode} produced no route")
            continue
        detour = row["distance_km"] / comparison["straight_line_km"]
        print(
            f"  {mode:9s} {_fmt(row['distance_km'], 8)} {_fmt(row['eta_hours'], 7)}"
            f" {_fmt(row['safety_score'], 7)} {_fmt(row['fuel_index'], 8)} {detour:6.2f}x"
        )
        if row["fuel_index"] < row["distance_km"]:
            failures.append(
                f"{mode}: fuel_index {row['fuel_index']:.1f} < distance {row['distance_km']:.1f}"
            )

    recommendation = comparison.get("recommendation", {})
    print(f"  recommended: {recommendation.get('mode')}")
    print(f"  reason     : {recommendation.get('reason')}")

    distinct_paths = {
        tuple((point["row"], point["col"]) for point in comparison["routes"][mode]["route"])
        for mode in ("fastest", "balanced", "safest")
        if comparison["routes"].get(mode, {}).get("success")
    }
    print(f"  distinct paths across the three modes: {len(distinct_paths)}")
    if len(distinct_paths) < 2:
        failures.append("all three modes produced the same path; alphas or scenario need tuning")

    safeties = {mode: table[mode]["safety_score"] for mode in table}
    if not safeties.get("safest", 0) >= safeties.get("balanced", 0) >= safeties.get("fastest", 0):
        failures.append(f"safety ordering violated: {safeties}")

    # ------------------------------------------------------------ hazard sweep
    balanced = comparison["routes"]["balanced"]
    committed = balanced["route"]
    print()
    print("=" * 68)
    print("HAZARD SWEEP (committed balanced route vs each horizon)")
    print("=" * 68)
    print(f"  {'hour':>5s} {'alert':>6s} {'severity':>9s} {'safety':>7s} {'primary cause':>26s}")

    base_eval = evaluate_route(committed, forecasts.scenario(0), forecasts.risk(0), config, 0.0)
    headline: dict[str, Any] | None = None
    for hour in forecasts.horizons:
        forecast_eval = evaluate_route(
            committed, forecasts.scenario(hour), forecasts.risk(hour), config, 0.0
        )
        hazard = detect_hazard(committed, base_eval, forecast_eval, config)
        cause = "-"
        if hazard["alert"]:
            explanation = explain_route_change(base_eval, forecast_eval, hazard)
            cause = explanation["route_change"]["contributors"][0]["factor"]
        print(
            f"  {hour:5d} {str(hazard['alert']):>6s} {hazard['severity']:>9s}"
            f" {_fmt(forecast_eval['safety_score'], 7)} {cause:>26s}"
        )
        if hour == args.hour:
            headline = {"hazard": hazard, "forecast_eval": forecast_eval}

    # --------------------------------------------------------- headline reroute
    print()
    print("=" * 68)
    print(f"HEADLINE DEMO SEQUENCE (+{args.hour}h)")
    print("=" * 68)
    if headline is None or not headline["hazard"]["alert"]:
        failures.append(f"no hazard alert at +{args.hour}h; the demo has nothing to show")
        print(f"  NO ALERT at +{args.hour}h")
    else:
        hazard = headline["hazard"]
        forecast_eval = headline["forecast_eval"]
        alternate = plan_route(
            forecasts.scenario(args.hour),
            forecasts.risk(args.hour),
            start,
            goal,
            float(config["route_modes"]["balanced"]["alpha"]),
            config,
            mode="balanced",
            departure_hour=args.hour,
        )
        alternate_eval = (
            evaluate_route(
                alternate.get("route_raw", []),
                forecasts.scenario(args.hour),
                forecasts.risk(args.hour),
                config,
                float(args.hour),
            )
            if alternate.get("success")
            else None
        )
        remaining = remaining_route_metrics(
            forecast_eval["waypoints"],
            start,
            forecasts.scenario(args.hour),
            forecasts.risk(args.hour),
            config,
            float(alternate.get("straight_line_km") or 0.0),
        )
        print(f"  planned safety at T+0      : {hazard['original_safety']:.1f}")
        print(f"  forecast safety at +{args.hour}h     : {hazard['forecast_safety']:.1f}")
        print(f"  safety delta               : {hazard['safety_delta']:.1f}")
        print(f"  first conflict waypoint    : {hazard['first_conflict_waypoint_index']}"
              f" of {len(committed)} (hour {hazard['first_conflict_hour']})")
        print(f"  responsible icebergs       : {hazard['responsible_icebergs']}")
        if alternate_eval is None:
            failures.append("no alternate route was found at the headline horizon")
            print("  alternate route            : NONE FOUND")
        else:
            recovered = alternate_eval["safety_score"]
            print(f"  alternate route safety     : {recovered:.1f}")
            if remaining:
                print(f"  additional distance        : {alternate['metrics']['distance_km'] - remaining['distance_km']:+.1f} km")
                print(f"  additional time            : {alternate['metrics']['eta_hours'] - remaining['eta_hours']:+.1f} h")
                print(f"  additional fuel index      : {alternate['metrics']['fuel_index'] - remaining['fuel_index']:+.1f}")
            explanation = explain_route_change(base_eval, forecast_eval, hazard, alternate)
            change = explanation["route_change"]
            print(f"  primary reason             : {change['primary_reason']} ({change['primary_entity']})")
            for contributor in change["contributors"]:
                print(f"      {contributor['factor']:28s} {contributor['impact']:+8.2f}")
            total = sum(item["impact"] for item in change["contributors"])
            print(f"      {'sum of contributors':28s} {total:+8.2f}  (reported {change['total_risk_delta']:+.2f})")
            if abs(total - change["total_risk_delta"]) > 1e-6:
                failures.append("explanation contributors do not sum to the reported total")
            if recovered <= hazard["forecast_safety"]:
                failures.append(
                    f"reroute did not improve safety ({hazard['forecast_safety']:.1f}"
                    f" -> {recovered:.1f})"
                )

    print()
    print("=" * 68)
    if failures:
        print(f"DEMO CHECK FAILED ({len(failures)} issue(s))")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("DEMO CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
