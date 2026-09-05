import heapq
import json
from copy import deepcopy
from pathlib import Path

import pytest

from backend.engine.geo import haversine_km
from backend.engine.grid import GridConfig, cell_to_latlon
from backend.engine.risk import compute_risk_grid
from backend.engine.routing import (
    astar,
    build_graph,
    path_metrics,
    plan_route,
    smooth_path,
    step_cost_km_equivalent,
)
from backend.main import APP_CONFIG, RISK_CONFIG


SCENARIO_PATH = Path(__file__).parents[1] / "backend" / "data" / "demo_scenario.json"


def make_risk_grid(
    rows=10,
    cols=10,
    blocked=None,
    risks=None,
    ice=None,
    bounds=None,
):
    blocked = blocked or set()
    risks = risks or {}
    ice = ice or {}
    bounds = bounds or {
        "lat_min": -68.1,
        "lat_max": -68.0,
        "lon_min": 74.0,
        "lon_max": 74.3,
    }
    cells = []
    for row in range(rows):
        for col in range(cols):
            node = (row, col)
            is_blocked = node in blocked
            cells.append(
                {
                    "row": row,
                    "col": col,
                    "total_risk": 100.0 if is_blocked else float(risks.get(node, 0.0)),
                    "is_navigable": not is_blocked,
                    "block_reason": "heavy_ice" if is_blocked else None,
                    "components": {},
                    "ice_concentration": float(ice.get(node, 0.0)),
                }
            )
    return {
        "meta": {
            "bounds": bounds,
            "grid": {"rows": rows, "cols": cols},
        },
        "cells": cells,
        "summary": {
            "navigable_cells": rows * cols - len(blocked),
            "blocked_cells": len(blocked),
        },
    }


def make_scenario(risk_grid):
    meta = risk_grid["meta"]
    grid_cfg = GridConfig(
        **meta["bounds"],
        rows=meta["grid"]["rows"],
        cols=meta["grid"]["cols"],
    )
    cells = []
    for risk_cell in risk_grid["cells"]:
        lat, lon = cell_to_latlon(risk_cell["row"], risk_cell["col"], grid_cfg)
        cells.append(
            {
                "row": risk_cell["row"],
                "col": risk_cell["col"],
                "lat": lat,
                "lon": lon,
                "ice_concentration": risk_cell["ice_concentration"],
                "is_land": False,
                "is_navigable": risk_cell["is_navigable"],
            }
        )
    return {
        "meta": meta,
        "cells": cells,
        "icebergs": [],
        "vessel": {"speed_knots_open_water": 12.0},
        "destination": {},
    }


def direct_cell_distance(risk_grid, start, goal):
    meta = risk_grid["meta"]
    grid_cfg = GridConfig(
        **meta["bounds"],
        rows=meta["grid"]["rows"],
        cols=meta["grid"]["cols"],
    )
    return haversine_km(
        *cell_to_latlon(*start, grid_cfg),
        *cell_to_latlon(*goal, grid_cfg),
    )


def dijkstra_cost(risk_grid, start, goal, alpha):
    graph = build_graph(risk_grid)
    distances = {start: 0.0}
    heap = [(0.0, start)]
    while heap:
        cost, node = heapq.heappop(heap)
        if cost != distances[node]:
            continue
        if node == goal:
            return cost
        for neighbour in graph[node]:
            candidate = cost + step_cost_km_equivalent(
                node, neighbour, risk_grid, alpha
            )
            if candidate < distances.get(neighbour, float("inf")):
                distances[neighbour] = candidate
                heapq.heappush(heap, (candidate, neighbour))
    return float("inf")


def test_zero_risk_corner_route_is_near_straight() -> None:
    risk_grid = make_risk_grid()
    result = astar(risk_grid, (0, 0), (9, 9), 2.0, APP_CONFIG)
    metrics = path_metrics(
        result["path"], risk_grid, {"speed_knots_open_water": 12.0}, APP_CONFIG
    )
    direct = direct_cell_distance(risk_grid, (0, 0), (9, 9))
    assert result["success"] is True
    assert metrics["distance_km"] <= direct * 1.10


def test_astar_cost_matches_dijkstra_on_varied_risk() -> None:
    risks = {
        (row, col): float((row * 13 + col * 17 + row * col) % 70)
        for row in range(10)
        for col in range(10)
    }
    risk_grid = make_risk_grid(risks=risks)
    alpha = 2.0
    astar_result = astar(risk_grid, (0, 0), (9, 9), alpha, APP_CONFIG)
    expected_cost = dijkstra_cost(risk_grid, (0, 0), (9, 9), alpha)
    assert astar_result["success"] is True
    assert astar_result["total_cost_km_equivalent"] == pytest.approx(
        expected_cost, rel=1e-12
    )


def test_raw_and_smoothed_paths_never_return_blocked_nodes() -> None:
    blocked = {(4, col) for col in range(9)}
    risk_grid = make_risk_grid(blocked=blocked)
    result = astar(risk_grid, (0, 0), (9, 9), 2.0, APP_CONFIG)
    smoothed = smooth_path(result["path"], risk_grid, APP_CONFIG)
    blocked_lookup = {
        (cell["row"], cell["col"])
        for cell in risk_grid["cells"]
        if not cell["is_navigable"]
    }
    assert all(cell not in blocked_lookup for cell in result["path"])
    assert all(cell not in blocked_lookup for cell in smoothed)


def test_iceberg_on_direct_line_forces_longer_detour() -> None:
    base_grid = make_risk_grid()
    scenario = make_scenario(base_grid)
    grid_cfg = GridConfig(**base_grid["meta"]["bounds"], rows=10, cols=10)
    iceberg_lat, iceberg_lon = cell_to_latlon(5, 5, grid_cfg)
    scenario["icebergs"] = [
        {
            "id": "IB-BLOCK",
            "lat": iceberg_lat,
            "lon": iceberg_lon,
            "radius_km": 0.2,
            "safety_buffer_km": 1.4,
        }
    ]
    environment_cells = []
    for cell in scenario["cells"]:
        environment_cells.append(
            {
                **cell,
                "wind_speed_ms": 0.0,
                "current_speed_ms": 0.0,
            }
        )
    scenario["cells"] = environment_cells
    iceberg_grid = compute_risk_grid(scenario, RISK_CONFIG)
    open_result = astar(base_grid, (1, 1), (8, 8), 0.0, APP_CONFIG)
    blocked_result = astar(iceberg_grid, (1, 1), (8, 8), 0.0, APP_CONFIG)
    open_metrics = path_metrics(
        open_result["path"], base_grid, {"speed_knots_open_water": 12.0}, APP_CONFIG
    )
    iceberg_routing_grid = deepcopy(iceberg_grid)
    for risk_cell in iceberg_routing_grid["cells"]:
        risk_cell["ice_concentration"] = 0.0
    blocked_metrics = path_metrics(
        blocked_result["path"],
        iceberg_routing_grid,
        {"speed_knots_open_water": 12.0},
        APP_CONFIG,
    )
    assert blocked_result["success"] is True
    assert blocked_metrics["distance_km"] > open_metrics["distance_km"]


def test_diagonal_corner_cutting_is_refused() -> None:
    risk_grid = make_risk_grid(rows=2, cols=2, blocked={(0, 1), (1, 0)})
    result = astar(risk_grid, (0, 0), (1, 1), 2.0, APP_CONFIG)
    assert result["success"] is False
    assert (1, 1) not in build_graph(risk_grid)[(0, 0)]


def test_smoothing_does_not_cross_a_corner_clipped_blocked_cell() -> None:
    risk_grid = make_risk_grid(rows=3, cols=3, blocked={(0, 1)})
    raw_path = [(0, 0), (1, 1), (2, 2)]
    assert smooth_path(raw_path, risk_grid, APP_CONFIG) == raw_path


def test_start_equal_goal_returns_one_node() -> None:
    risk_grid = make_risk_grid()
    result = astar(risk_grid, (3, 4), (3, 4), 2.0, APP_CONFIG)
    assert result["success"] is True
    assert result["path"] == [(3, 4)]
    assert result["total_cost_km_equivalent"] == 0.0


def test_routing_is_byte_deterministic_across_five_runs() -> None:
    risk_grid = make_risk_grid(
        risks={(row, col): float((row + col) % 5) for row in range(10) for col in range(10)}
    )
    outputs = [
        json.dumps(astar(risk_grid, (0, 0), (9, 9), 2.0, APP_CONFIG), sort_keys=True)
        for _ in range(5)
    ]
    assert len(set(outputs)) == 1


def test_route_metrics_are_complementary_and_plausible() -> None:
    risk_grid = make_risk_grid(
        risks={(row, col): float(row + col) for row in range(10) for col in range(10)},
        ice={(row, col): 0.3 for row in range(10) for col in range(10)},
    )
    result = astar(risk_grid, (0, 0), (9, 9), 2.0, APP_CONFIG)
    raw_metrics = path_metrics(
        result["path"], risk_grid, {"speed_knots_open_water": 12.0}, APP_CONFIG
    )
    smoothed_path = smooth_path(result["path"], risk_grid, APP_CONFIG)
    metrics = path_metrics(
        smoothed_path, risk_grid, {"speed_knots_open_water": 12.0}, APP_CONFIG
    )
    assert metrics["risk_score"] + metrics["safety_score"] == pytest.approx(100.0)
    assert metrics["distance_km"] <= raw_metrics["distance_km"] + 1e-9
    assert metrics["eta_hours"] > 0.0
    assert metrics["max_cell_risk"] >= metrics["mean_cell_risk"]


def test_walled_goal_returns_structured_failure() -> None:
    blocked = {(7, 7), (7, 8), (7, 9), (8, 7), (8, 9), (9, 7), (9, 8)}
    risk_grid = make_risk_grid(blocked=blocked)
    scenario = make_scenario(risk_grid)
    grid_cfg = GridConfig(**risk_grid["meta"]["bounds"], rows=10, cols=10)
    result = plan_route(
        scenario,
        risk_grid,
        cell_to_latlon(0, 0, grid_cfg),
        cell_to_latlon(8, 8, grid_cfg),
        2.0,
        APP_CONFIG,
    )
    assert result["success"] is False
    assert result["reason"] == "no_route_found"


def test_blocked_start_snaps_and_reports_the_move() -> None:
    risk_grid = make_risk_grid(blocked={(0, 0)})
    scenario = make_scenario(risk_grid)
    grid_cfg = GridConfig(**risk_grid["meta"]["bounds"], rows=10, cols=10)
    result = plan_route(
        scenario,
        risk_grid,
        cell_to_latlon(0, 0, grid_cfg),
        cell_to_latlon(9, 9, grid_cfg),
        2.0,
        APP_CONFIG,
    )
    assert result["success"] is True
    assert result["start_snapped_from"]["row"] == 0
    assert result["start_snapped_from"]["col"] == 0
    assert (
        result["start_snapped_to"]["row"],
        result["start_snapped_to"]["col"],
    ) != (0, 0)


def test_goal_outside_bounds_raises_clear_error() -> None:
    risk_grid = make_risk_grid()
    scenario = make_scenario(risk_grid)
    grid_cfg = GridConfig(**risk_grid["meta"]["bounds"], rows=10, cols=10)
    with pytest.raises(ValueError, match="latitude is outside grid bounds"):
        plan_route(
            scenario,
            risk_grid,
            cell_to_latlon(0, 0, grid_cfg),
            (-70.0, 74.1),
            2.0,
            APP_CONFIG,
        )


def test_demo_scenario_route_succeeds_with_plausible_distance() -> None:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    risk_grid = compute_risk_grid(scenario, RISK_CONFIG)
    result = plan_route(
        scenario,
        risk_grid,
        (scenario["vessel"]["lat"], scenario["vessel"]["lon"]),
        (scenario["destination"]["lat"], scenario["destination"]["lon"]),
        APP_CONFIG["route_modes"]["balanced"]["alpha"],
        APP_CONFIG,
    )
    assert result["success"] is True
    assert 300.0 < result["metrics"]["distance_km"] < 500.0
    assert result["metrics"]["distance_km"] / result["straight_line_km"] < 1.5
