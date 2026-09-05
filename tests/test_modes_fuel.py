import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.engine.comparison import compare_routes, recommendation_for_routes
from backend.engine.fuel import fuel_index, resistance_factor
from backend.engine.risk import compute_risk_grid
from backend.engine.routing import path_metrics


SCENARIO_PATH = Path(__file__).parents[1] / "backend" / "data" / "demo_scenario.json"
client = TestClient(main.app)


@pytest.fixture(scope="module")
def demo_comparison():
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    risk_grid = compute_risk_grid(scenario, main.RISK_CONFIG)
    result = compare_routes(
        scenario,
        risk_grid,
        (scenario["vessel"]["lat"], scenario["vessel"]["lon"]),
        (scenario["destination"]["lat"], scenario["destination"]["lon"]),
        main.APP_CONFIG,
    )
    return scenario, risk_grid, result


def route_stub(mode, distance, safety):
    return {
        "success": True,
        "mode": mode,
        "metrics": {
            "distance_km": distance,
            "eta_hours": 10.0,
            "risk_score": 100.0 - safety,
            "safety_score": safety,
            "fuel_index": distance,
            "fuel_vs_direct": 1.0,
        },
    }


def test_real_mode_ordering_invariants(demo_comparison) -> None:
    _, _, result = demo_comparison
    routes = result["routes"]
    fastest_eta = routes["fastest"]["metrics"]["eta_hours"]
    assert fastest_eta <= routes["balanced"]["metrics"]["eta_hours"]
    assert fastest_eta <= routes["safest"]["metrics"]["eta_hours"]
    assert (
        routes["safest"]["metrics"]["safety_score"]
        >= routes["balanced"]["metrics"]["safety_score"]
    )


def test_real_modes_produce_distinct_paths(demo_comparison) -> None:
    _, _, result = demo_comparison
    paths = {
        tuple((point["row"], point["col"]) for point in route["route_raw"])
        for route in result["routes"].values()
    }
    assert len(paths) >= 2


def test_fuel_index_is_never_below_distance(demo_comparison) -> None:
    _, _, result = demo_comparison
    for route in result["routes"].values():
        assert route["metrics"]["fuel_index"] >= route["metrics"]["distance_km"]


def test_resistance_factor_is_monotonic_and_starts_at_one() -> None:
    values = [resistance_factor(index / 100.0, main.APP_CONFIG) for index in range(101)]
    assert values == sorted(values)
    assert resistance_factor(0.0, main.APP_CONFIG) == 1.0


def test_open_water_fuel_index_equals_distance() -> None:
    risk_grid = {
        "meta": {
            "bounds": {"lat_min": -68.1, "lat_max": -68.0, "lon_min": 74.0, "lon_max": 74.3},
            "grid": {"rows": 2, "cols": 2},
        },
        "cells": [
            {
                "row": row,
                "col": col,
                "total_risk": 0.0,
                "is_navigable": True,
                "ice_concentration": 0.0,
            }
            for row in range(2)
            for col in range(2)
        ],
    }
    path = [(0, 0), (1, 1)]
    distance = path_metrics(
        path, risk_grid, {"speed_knots_open_water": 12.0}, main.APP_CONFIG
    )["distance_km"]
    assert fuel_index(path, risk_grid, main.APP_CONFIG) == pytest.approx(distance)


def test_recommendation_is_deterministic() -> None:
    routes = {
        "fastest": route_stub("fastest", 100.0, 72.0),
        "balanced": route_stub("balanced", 108.0, 84.0),
        "safest": route_stub("safest", 120.0, 95.0),
    }
    first = recommendation_for_routes(routes, main.APP_CONFIG)
    second = recommendation_for_routes(routes, main.APP_CONFIG)
    assert first == second


def test_route_below_safety_floor_is_not_recommended() -> None:
    routes = {
        "fastest": route_stub("fastest", 100.0, 60.0),
        "balanced": route_stub("balanced", 108.0, 82.0),
        "safest": route_stub("safest", 130.0, 90.0),
    }
    recommendation = recommendation_for_routes(routes, main.APP_CONFIG)
    assert recommendation["mode"] != "fastest"


def test_fastest_remains_when_safety_gain_is_too_small() -> None:
    routes = {
        "fastest": route_stub("fastest", 100.0, 75.0),
        "balanced": route_stub("balanced", 104.0, 80.0),
        "safest": route_stub("safest", 110.0, 83.0),
    }
    recommendation = recommendation_for_routes(routes, main.APP_CONFIG)
    assert recommendation["mode"] == "fastest"


def test_recommendation_reason_contains_computed_numbers() -> None:
    routes = {
        "fastest": route_stub("fastest", 100.0, 72.0),
        "balanced": route_stub("balanced", 108.5, 84.0),
        "safest": route_stub("safest", 140.0, 90.0),
    }
    reason = recommendation_for_routes(routes, main.APP_CONFIG)["reason"]
    assert "12.0" in reason
    assert "8.5%" in reason


def test_compare_api_returns_three_full_modes() -> None:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    payload = {
        "start": {"lat": scenario["vessel"]["lat"], "lon": scenario["vessel"]["lon"]},
        "destination": {"lat": scenario["destination"]["lat"], "lon": scenario["destination"]["lon"]},
        "forecast_hour": 0,
    }
    response = client.post("/routes/compare", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert set(result["routes"]) == {"fastest", "balanced", "safest"}
    for route in result["routes"].values():
        assert route["success"] is True
        assert {"distance_km", "eta_hours", "safety_score", "fuel_index"}.issubset(route["metrics"])


def test_safest_single_route_matches_compare() -> None:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    base_payload = {
        "start": {"lat": scenario["vessel"]["lat"], "lon": scenario["vessel"]["lon"]},
        "destination": {"lat": scenario["destination"]["lat"], "lon": scenario["destination"]["lon"]},
        "forecast_hour": 0,
    }
    compare_result = client.post("/routes/compare", json=base_payload).json()
    route_result = client.post("/route", json={**base_payload, "mode": "safest"}).json()
    assert route_result == compare_result["routes"]["safest"]


def test_invalid_route_mode_returns_400() -> None:
    response = client.post(
        "/route",
        json={
            "start": {"lat": -69.02, "lon": 72.1},
            "destination": {"lat": -66.92, "lon": 78.18},
            "mode": "reckless",
            "forecast_hour": 0,
        },
    )
    assert response.status_code == 400


def test_route_accepts_supported_forecast_hour() -> None:
    response = client.post(
        "/route",
        json={
            "start": {"lat": -69.02, "lon": 72.1},
            "destination": {"lat": -66.92, "lon": 78.18},
            "mode": "balanced",
            "forecast_hour": 6,
        },
    )
    assert response.status_code == 200
    assert response.json()["forecast_hour"] == 6
