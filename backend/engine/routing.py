"""Deterministic A* routing over the ICE-NAV navigation risk surface."""

from __future__ import annotations

import heapq
import itertools
from typing import Any

from .fuel import fuel_metrics
from .geo import KM_PER_NAUTICAL_MILE, haversine_km
from .grid import GridConfig, cell_to_latlon, is_valid_cell, latlon_to_cell, neighbors8

Cell = tuple[int, int]
TimedCell = tuple[int, int, int]


def _grid_config(risk_grid: dict[str, Any]) -> GridConfig:
    meta = risk_grid["meta"]
    return GridConfig(
        **meta["bounds"],
        rows=int(meta["grid"]["rows"]),
        cols=int(meta["grid"]["cols"]),
    )


def _cell_lookup(risk_grid: dict[str, Any]) -> dict[Cell, dict[str, Any]]:
    return {(int(cell["row"]), int(cell["col"])): cell for cell in risk_grid["cells"]}


def build_graph(
    risk_grid: dict[str, Any], cfg: dict[str, Any] | None = None
) -> dict[Cell, list[Cell]]:
    """Return an 8-connected graph containing navigable cells only.

    A diagonal edge is removed when both orthogonal cells beside that edge are
    blocked, preventing a vessel from squeezing between two forbidden cells.
    """
    grid_cfg = _grid_config(risk_grid)
    cells = _cell_lookup(risk_grid)
    navigable = {node for node, cell in cells.items() if cell["is_navigable"]}
    routing_cfg = cfg["routing"] if cfg is not None else {}
    allow_diagonal = bool(routing_cfg.get("allow_diagonal", True))
    forbid_corner_cutting = bool(
        routing_cfg.get("forbid_diagonal_corner_cutting", True)
    )
    graph: dict[Cell, list[Cell]] = {}

    for node in sorted(navigable):
        row, col = node
        edges: list[Cell] = []
        for neighbour in neighbors8(row, col, grid_cfg.rows, grid_cfg.cols):
            if neighbour not in navigable:
                continue
            neighbour_row, neighbour_col = neighbour
            if row != neighbour_row and col != neighbour_col:
                if not allow_diagonal:
                    continue
                orthogonal_a = (neighbour_row, col)
                orthogonal_b = (row, neighbour_col)
                if (
                    forbid_corner_cutting
                    and orthogonal_a not in navigable
                    and orthogonal_b not in navigable
                ):
                    continue
            edges.append(neighbour)
        graph[node] = sorted(edges)
    return graph


def heuristic_km(
    row: int,
    col: int,
    goal_row: int,
    goal_col: int,
    grid_cfg: GridConfig,
) -> float:
    """Return straight-line haversine distance from a cell to the goal.

    This heuristic is admissible because the minimum edge-cost multiplier is
    1.0. True remaining kilometre-equivalent cost is therefore always at least
    the straight-line distance in kilometres.
    """
    lat, lon = cell_to_latlon(row, col, grid_cfg)
    goal_lat, goal_lon = cell_to_latlon(goal_row, goal_col, grid_cfg)
    return haversine_km(lat, lon, goal_lat, goal_lon)


def step_cost_km_equivalent(
    from_cell: Cell,
    to_cell: Cell,
    risk_grid: dict[str, Any],
    alpha: float,
) -> float:
    """Return ``segment_km * (1 + alpha * mean_risk / 100)``."""
    grid_cfg = _grid_config(risk_grid)
    cells = _cell_lookup(risk_grid)
    from_lat, from_lon = cell_to_latlon(*from_cell, grid_cfg)
    to_lat, to_lon = cell_to_latlon(*to_cell, grid_cfg)
    segment_km = haversine_km(from_lat, from_lon, to_lat, to_lon)
    risk_norm = (
        float(cells[from_cell]["total_risk"])
        + float(cells[to_cell]["total_risk"])
    ) / 200.0
    return segment_km * (1.0 + float(alpha) * risk_norm)


def _step_cost_precomputed(
    from_cell: Cell,
    to_cell: Cell,
    cells: dict[Cell, dict[str, Any]],
    coordinates: dict[Cell, tuple[float, float]],
    alpha: float,
    cfg: dict[str, Any],
    vessel: dict[str, Any],
    mode: str,
) -> float:
    segment_km = haversine_km(*coordinates[from_cell], *coordinates[to_cell])
    if mode == "fastest":
        mean_ice = (
            float(cells[from_cell]["ice_concentration"])
            + float(cells[to_cell]["ice_concentration"])
        ) / 2.0
        effective_speed_kmh = (
            float(vessel["speed_knots_open_water"])
            * _interpolate_speed_factor(mean_ice, cfg)
            * KM_PER_NAUTICAL_MILE
        )
        return segment_km / effective_speed_kmh

    risk_norm = (
        float(cells[from_cell]["total_risk"])
        + float(cells[to_cell]["total_risk"])
    ) / 200.0
    return segment_km * (1.0 + alpha * risk_norm)


def _reconstruct_path(came_from: dict[Cell, Cell], current: Cell) -> list[Cell]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def astar(
    risk_grid: dict[str, Any],
    start_cell: Cell,
    goal_cell: Cell,
    alpha: float | None,
    cfg: dict[str, Any],
    vessel: dict[str, Any] | None = None,
    mode: str = "balanced",
) -> dict[str, Any]:
    """Find a deterministic route for the selected optimisation mode."""
    graph = build_graph(risk_grid, cfg)
    if start_cell not in graph or goal_cell not in graph:
        return {
            "success": False,
            "reason": "no_route_found",
            "path": [],
            "nodes_expanded": 0,
        }

    active_alpha = (
        float(alpha)
        if alpha is not None
        else float(cfg["route_modes"]["balanced"]["alpha"])
    )
    active_vessel = vessel or {"speed_knots_open_water": 12.0}
    if start_cell == goal_cell:
        return {
            "success": True,
            "path": [start_cell],
            "total_cost_km_equivalent": 0.0,
            "nodes_expanded": 1,
        }

    grid_cfg = _grid_config(risk_grid)
    cells = _cell_lookup(risk_grid)
    coordinates = {
        cell: cell_to_latlon(*cell, grid_cfg)
        for cell in cells
    }
    max_expansions = int(cfg["routing"]["max_node_expansions"])
    counter = itertools.count()
    start_h = heuristic_km(*start_cell, *goal_cell, grid_cfg)
    if mode == "fastest":
        open_water_speed_kmh = (
            float(active_vessel["speed_knots_open_water"]) * KM_PER_NAUTICAL_MILE
        )
        start_h = start_h / open_water_speed_kmh
    open_heap: list[tuple[float, float, int, int, int, Cell]] = [
        (start_h, start_h, start_cell[0], start_cell[1], next(counter), start_cell)
    ]
    came_from: dict[Cell, Cell] = {}
    g_score: dict[Cell, float] = {start_cell: 0.0}
    closed: set[Cell] = set()
    nodes_expanded = 0

    while open_heap:
        _, _, _, _, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        closed.add(current)
        nodes_expanded += 1

        if current == goal_cell:
            return {
                "success": True,
                "path": _reconstruct_path(came_from, current),
                "total_cost_km_equivalent": g_score[current],
                "nodes_expanded": nodes_expanded,
            }
        if nodes_expanded >= max_expansions:
            return {
                "success": False,
                "reason": "search_limit_exceeded",
                "path": [],
                "nodes_expanded": nodes_expanded,
            }

        for neighbour in graph[current]:
            if neighbour in closed:
                continue
            tentative_g = g_score[current] + _step_cost_precomputed(
                current,
                neighbour,
                cells,
                coordinates,
                active_alpha,
                cfg,
                active_vessel,
                mode,
            )
            if tentative_g >= g_score.get(neighbour, float("inf")):
                continue
            came_from[neighbour] = current
            g_score[neighbour] = tentative_g
            neighbour_h = heuristic_km(*neighbour, *goal_cell, grid_cfg)
            if mode == "fastest":
                neighbour_h = neighbour_h / open_water_speed_kmh
            heapq.heappush(
                open_heap,
                (
                    tentative_g + neighbour_h,
                    neighbour_h,
                    neighbour[0],
                    neighbour[1],
                    next(counter),
                    neighbour,
                ),
            )

    return {
        "success": False,
        "reason": "no_route_found",
        "path": [],
        "nodes_expanded": nodes_expanded,
    }


def astar_time_expanded(
    forecast_data: dict[int, tuple[dict[str, Any], dict[str, Any]]],
    start_cell: Cell,
    goal_cell: Cell,
    alpha: float,
    cfg: dict[str, Any],
    vessel: dict[str, Any],
    mode: str,
    departure_hour: float = 0.0,
) -> dict[str, Any]:
    """Route through nearest forecast snapshots with time-bucketed A* states.

    Nearest-snapshot selection is deliberately discrete and explainable. The
    distance heuristic (or open-water travel-time heuristic for fastest mode)
    remains admissible because no edge multiplier is below one and no modeled
    speed exceeds open-water speed. Linear snapshot interpolation is future work.
    """
    horizons = sorted(forecast_data)
    if not horizons:
        raise ValueError("forecast_data must contain at least one horizon")
    risk_signatures = [
        tuple((cell["row"], cell["col"], cell["total_risk"], cell["is_navigable"]) for cell in forecast_data[hour][1]["cells"])
        for hour in horizons
    ]
    if all(signature == risk_signatures[0] for signature in risk_signatures[1:]):
        static = astar(forecast_data[horizons[0]][1], start_cell, goal_cell, alpha, cfg, vessel, mode)
        static.update(arrival_hour=departure_hour, snapshots_used=[horizons[0]], beyond_forecast_horizon=departure_hour > horizons[-1])
        if static.get("success"):
            routing_grid = _routing_grid(forecast_data[horizons[0]][0], forecast_data[horizons[0]][1])
            eta = path_metrics(static["path"], routing_grid, vessel, cfg)["eta_hours"]
            static["arrival_hour"] = departure_hour + float(eta)
        return static

    grid_cfg = _grid_config(forecast_data[horizons[0]][1])
    coordinates = {(row, col): cell_to_latlon(row, col, grid_cfg) for row in range(grid_cfg.rows) for col in range(grid_cfg.cols)}
    bucket_hours = float(cfg["routing"].get("time_bucket_hours", 1.0))
    open_water_speed = float(vessel["speed_knots_open_water"]) * KM_PER_NAUTICAL_MILE

    def nearest_hour(hour: float) -> int:
        return min(horizons, key=lambda candidate: (abs(candidate - hour), candidate))

    def snapshot(hour: float) -> tuple[dict[Cell, dict[str, Any]], dict[Cell, dict[str, Any]], int]:
        selected = nearest_hour(hour)
        scenario, risk = forecast_data[selected]
        environment = {(cell["row"], cell["col"]): cell for cell in scenario["cells"]}
        return environment, _cell_lookup(risk), selected

    start_state: TimedCell = (*start_cell, round(departure_hour / bucket_hours))
    counter = itertools.count()
    start_h = heuristic_km(*start_cell, *goal_cell, grid_cfg)
    if mode == "fastest":
        start_h /= open_water_speed
    heap = [(start_h, start_h, *start_state, next(counter), start_state)]
    g_score = {start_state: 0.0}
    elapsed = {start_state: 0.0}
    came_from: dict[TimedCell, TimedCell] = {}
    closed: set[TimedCell] = set()
    used: set[int] = set()
    nodes_expanded = 0
    max_expansions = int(cfg["routing"]["max_node_expansions"])

    while heap:
        *_, current = heapq.heappop(heap)
        if current in closed:
            continue
        closed.add(current)
        nodes_expanded += 1
        current_cell = (current[0], current[1])
        current_hour = departure_hour + elapsed[current]
        if current_cell == goal_cell:
            states = [current]
            while states[-1] in came_from:
                states.append(came_from[states[-1]])
            states.reverse()
            return {
                "success": True,
                "path": [(state[0], state[1]) for state in states],
                "total_cost_km_equivalent": g_score[current],
                "nodes_expanded": nodes_expanded,
                "arrival_hour": current_hour,
                "snapshots_used": sorted(used),
                "beyond_forecast_horizon": current_hour > horizons[-1],
            }
        if nodes_expanded >= max_expansions:
            break
        environment, current_risks, selected = snapshot(current_hour)
        used.add(selected)
        for neighbour in neighbors8(*current_cell, grid_cfg.rows, grid_cfg.cols):
            segment_km = haversine_km(*coordinates[current_cell], *coordinates[neighbour])
            mean_ice = (float(environment[current_cell]["ice_concentration"]) + float(environment[neighbour]["ice_concentration"])) / 2
            segment_hours = segment_km / (open_water_speed * _interpolate_speed_factor(mean_ice, cfg))
            arrival = current_hour + segment_hours
            arrival_environment, arrival_risks, arrival_snapshot = snapshot(arrival)
            used.add(arrival_snapshot)
            if not arrival_risks[neighbour]["is_navigable"]:
                continue
            bucket = round(arrival / bucket_hours)
            neighbour_state: TimedCell = (*neighbour, bucket)
            risk_norm = (float(current_risks[current_cell]["total_risk"]) + float(arrival_risks[neighbour]["total_risk"])) / 200
            edge_cost = segment_hours if mode == "fastest" else segment_km * (1 + alpha * risk_norm)
            tentative = g_score[current] + edge_cost
            if tentative >= g_score.get(neighbour_state, float("inf")):
                continue
            came_from[neighbour_state] = current
            g_score[neighbour_state] = tentative
            elapsed[neighbour_state] = elapsed[current] + segment_hours
            heuristic = heuristic_km(*neighbour, *goal_cell, grid_cfg)
            if mode == "fastest":
                heuristic /= open_water_speed
            heapq.heappush(heap, (tentative + heuristic, heuristic, *neighbour_state, next(counter), neighbour_state))
    return {"success": False, "reason": "no_route_found", "path": [], "nodes_expanded": nodes_expanded}


def _supercover_cells(start: Cell, end: Cell) -> list[Cell]:
    """Enumerate every cell touched by a centre-to-centre grid segment."""
    row, col = start
    end_row, end_col = end
    delta_row = end_row - row
    delta_col = end_col - col
    row_steps = abs(delta_row)
    col_steps = abs(delta_col)
    row_sign = 0 if delta_row == 0 else (1 if delta_row > 0 else -1)
    col_sign = 0 if delta_col == 0 else (1 if delta_col > 0 else -1)
    row_progress = 0
    col_progress = 0
    result = [(row, col)]

    def append(cell: Cell) -> None:
        if cell not in result:
            result.append(cell)

    while row_progress < row_steps or col_progress < col_steps:
        col_boundary = (1 + 2 * col_progress) * row_steps
        row_boundary = (1 + 2 * row_progress) * col_steps
        if col_boundary == row_boundary:
            append((row, col + col_sign))
            append((row + row_sign, col))
            col += col_sign
            row += row_sign
            col_progress += 1
            row_progress += 1
            append((row, col))
        elif col_boundary < row_boundary:
            col += col_sign
            col_progress += 1
            append((row, col))
        else:
            row += row_sign
            row_progress += 1
            append((row, col))
    return result


def _has_line_of_sight(start: Cell, end: Cell, navigable: set[Cell]) -> bool:
    return all(cell in navigable for cell in _supercover_cells(start, end))


def smooth_path(
    path: list[Cell],
    risk_grid: dict[str, Any],
    cfg: dict[str, Any],
) -> list[Cell]:
    """Apply navigability-only supercover string-pulling to a raw grid path."""
    if len(path) <= 2 or not bool(cfg["routing"]["smoothing_enabled"]):
        return list(path)

    cells = _cell_lookup(risk_grid)
    navigable = {node for node, cell in cells.items() if cell["is_navigable"]}
    smoothed = [path[0]]
    anchor_index = 0
    while anchor_index < len(path) - 1:
        furthest_index = anchor_index + 1
        for candidate_index in range(anchor_index + 2, len(path)):
            if _has_line_of_sight(
                path[anchor_index], path[candidate_index], navigable
            ):
                furthest_index = candidate_index
        smoothed.append(path[furthest_index])
        anchor_index = furthest_index
    return smoothed


def _interpolate_speed_factor(ice_concentration: float, cfg: dict[str, Any]) -> float:
    breakpoints = [
        (float(concentration), float(factor))
        for concentration, factor in cfg["vessel_model"]["speed_factor_by_ice"]
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


def _traversed_cells(path: list[Cell], risk_grid: dict[str, Any]) -> list[Cell]:
    if not path:
        return []
    navigable = {
        node for node, cell in _cell_lookup(risk_grid).items() if cell["is_navigable"]
    }
    traversed: list[Cell] = []
    segments = zip(path, path[1:]) if len(path) > 1 else []
    for start, end in segments:
        for cell in _supercover_cells(start, end):
            if cell in navigable and (not traversed or traversed[-1] != cell):
                traversed.append(cell)
    if len(path) == 1:
        traversed.append(path[0])
    return traversed


def path_metrics(
    path: list[Cell],
    risk_grid: dict[str, Any],
    vessel: dict[str, Any],
    cfg: dict[str, Any],
    start_latlon: tuple[float, float] | None = None,
    goal_latlon: tuple[float, float] | None = None,
) -> dict[str, float | int]:
    """Compute full-precision distance, ETA, and mean-plus-peak route risk."""
    if not path:
        raise ValueError("path must contain at least one cell")

    grid_cfg = _grid_config(risk_grid)
    cells = _cell_lookup(risk_grid)
    distance_km = 0.0
    eta_hours = 0.0
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
        effective_speed_kmh = (
            float(vessel["speed_knots_open_water"])
            * _interpolate_speed_factor(mean_ice, cfg)
            * KM_PER_NAUTICAL_MILE
        )
        distance_km += segment_km
        eta_hours += segment_km / effective_speed_kmh

    traversed = _traversed_cells(path, risk_grid)
    route_risks = [float(cells[cell]["total_risk"]) for cell in traversed]
    mean_risk = sum(route_risks) / len(route_risks)
    max_risk = max(route_risks)
    route_metrics_cfg = cfg["route_metrics"]
    risk_score = (
        float(route_metrics_cfg["mean_weight"]) * mean_risk
        + float(route_metrics_cfg["max_weight"]) * max_risk
    )
    return {
        "distance_km": distance_km,
        "eta_hours": eta_hours,
        "risk_score": risk_score,
        "safety_score": 100.0 - risk_score,
        "mean_cell_risk": mean_risk,
        "max_cell_risk": max_risk,
        "cells_traversed": len(traversed),
    }


def _routing_grid(
    scenario: dict[str, Any], risk_grid: dict[str, Any]
) -> dict[str, Any]:
    environment_cells = {
        (int(cell["row"]), int(cell["col"])): cell for cell in scenario["cells"]
    }
    cells = []
    for risk_cell in risk_grid["cells"]:
        node = (int(risk_cell["row"]), int(risk_cell["col"]))
        cells.append(
            {
                **risk_cell,
                "ice_concentration": float(
                    environment_cells[node]["ice_concentration"]
                ),
            }
        )
    return {**risk_grid, "cells": cells}


def _nearest_navigable(
    requested_latlon: tuple[float, float],
    original: Cell,
    risk_grid: dict[str, Any],
    cfg: dict[str, Any],
) -> Cell | None:
    cells = _cell_lookup(risk_grid)
    if cells[original]["is_navigable"]:
        return original

    grid_cfg = _grid_config(risk_grid)
    requested_lat, requested_lon = requested_latlon
    max_radius = int(cfg["routing"]["snap_radius_cells"])
    for radius in range(1, max_radius + 1):
        candidates: list[tuple[float, int, int, Cell]] = []
        for row_offset in range(-radius, radius + 1):
            for col_offset in range(-radius, radius + 1):
                if max(abs(row_offset), abs(col_offset)) != radius:
                    continue
                candidate = (original[0] + row_offset, original[1] + col_offset)
                if not is_valid_cell(*candidate, grid_cfg.rows, grid_cfg.cols):
                    continue
                if not cells[candidate]["is_navigable"]:
                    continue
                lat, lon = cell_to_latlon(*candidate, grid_cfg)
                candidates.append(
                    (
                        haversine_km(requested_lat, requested_lon, lat, lon),
                        candidate[0],
                        candidate[1],
                        candidate,
                    )
                )
        if candidates:
            return min(candidates)[3]
    return None


def _route_point(cell: Cell, grid_cfg: GridConfig) -> dict[str, float | int]:
    lat, lon = cell_to_latlon(*cell, grid_cfg)
    return {
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "row": cell[0],
        "col": cell[1],
    }


def _requested_point(
    latlon: tuple[float, float], cell: Cell
) -> dict[str, float | int]:
    return {"lat": latlon[0], "lon": latlon[1], "row": cell[0], "col": cell[1]}


def plan_route(
    scenario: dict[str, Any],
    risk_grid: dict[str, Any],
    start_latlon: tuple[float, float],
    goal_latlon: tuple[float, float],
    alpha: float | None,
    cfg: dict[str, Any],
    mode: str = "balanced",
    forecast_data: dict[int, tuple[dict[str, Any], dict[str, Any]]] | None = None,
    departure_hour: float = 0.0,
) -> dict[str, Any]:
    """Snap endpoints, run A*, smooth the path, and report route metrics."""
    routing_grid = _routing_grid(scenario, risk_grid)
    grid_cfg = _grid_config(routing_grid)
    start_original = latlon_to_cell(*start_latlon, grid_cfg)
    goal_original = latlon_to_cell(*goal_latlon, grid_cfg)
    cells = _cell_lookup(routing_grid)
    start_cell = _nearest_navigable(
        start_latlon, start_original, routing_grid, cfg
    )
    goal_cell = _nearest_navigable(goal_latlon, goal_original, routing_grid, cfg)

    diagnostics = {
        "start_cell_navigable": bool(cells[start_original]["is_navigable"]),
        "goal_cell_navigable": bool(cells[goal_original]["is_navigable"]),
        "start_block_reason": cells[start_original]["block_reason"],
        "goal_block_reason": cells[goal_original]["block_reason"],
        "nodes_expanded": 0,
    }
    if start_cell is None or goal_cell is None:
        return {
            "success": False,
            "reason": "no_route_found",
            "message": "No navigable path exists between start and destination under the current risk surface.",
            "diagnostics": diagnostics,
        }

    active_alpha = (
        float(alpha)
        if alpha is not None
        else float(cfg["route_modes"]["balanced"]["alpha"])
    )
    search = (
        astar_time_expanded(forecast_data, start_cell, goal_cell, active_alpha, cfg, scenario["vessel"], mode, departure_hour)
        if forecast_data and bool(cfg["routing"].get("time_expanded", False))
        else astar(routing_grid, start_cell, goal_cell, active_alpha, cfg, scenario["vessel"], mode)
    )
    diagnostics["nodes_expanded"] = search["nodes_expanded"]
    if not search["success"]:
        return {
            "success": False,
            "reason": search["reason"],
            "message": "No navigable path exists between start and destination under the current risk surface.",
            "diagnostics": diagnostics,
        }

    raw_path = search["path"]
    route_path = smooth_path(raw_path, routing_grid, cfg)
    straight_line_km = haversine_km(*start_latlon, *goal_latlon)
    route_start_latlon = start_latlon if start_cell == start_original else None
    route_goal_latlon = goal_latlon if goal_cell == goal_original else None
    metrics = path_metrics(
        route_path,
        routing_grid,
        scenario["vessel"],
        cfg,
        start_latlon=route_start_latlon,
        goal_latlon=route_goal_latlon,
    )
    metrics.update(
        fuel_metrics(
            route_path,
            routing_grid,
            straight_line_km,
            cfg,
            start_latlon=route_start_latlon,
            goal_latlon=route_goal_latlon,
        )
    )
    risk_score = round(float(metrics["risk_score"]), 1)
    reported_metrics = {
        "distance_km": round(float(metrics["distance_km"]), 1),
        "eta_hours": round(float(metrics["eta_hours"]), 1),
        "risk_score": risk_score,
        "safety_score": round(100.0 - risk_score, 1),
        "mean_cell_risk": round(float(metrics["mean_cell_risk"]), 1),
        "max_cell_risk": round(float(metrics["max_cell_risk"]), 1),
        "cells_traversed": int(metrics["cells_traversed"]),
        "fuel_index": round(float(metrics["fuel_index"]), 1),
        "fuel_vs_direct": round(float(metrics["fuel_vs_direct"]), 2),
    }
    route_points = [_route_point(cell, grid_cfg) for cell in route_path]
    raw_route_points = [_route_point(cell, grid_cfg) for cell in raw_path]
    cumulative_hours = 0.0
    raw_route_points[0]["arrival_hour"] = round(departure_hour, 3)
    routing_cells = _cell_lookup(routing_grid)
    for index, (start, end) in enumerate(zip(raw_path, raw_path[1:]), start=1):
        segment_km = haversine_km(*cell_to_latlon(*start, grid_cfg), *cell_to_latlon(*end, grid_cfg))
        mean_ice = (float(routing_cells[start]["ice_concentration"]) + float(routing_cells[end]["ice_concentration"])) / 2.0
        speed_kmh = float(scenario["vessel"]["speed_knots_open_water"]) * KM_PER_NAUTICAL_MILE * _interpolate_speed_factor(mean_ice, cfg)
        cumulative_hours += segment_km / speed_kmh
        raw_route_points[index]["arrival_hour"] = round(departure_hour + cumulative_hours, 3)
    if start_cell == start_original:
        route_points[0].update({"lat": start_latlon[0], "lon": start_latlon[1]})
        raw_route_points[0].update({"lat": start_latlon[0], "lon": start_latlon[1]})
    if goal_cell == goal_original:
        route_points[-1].update({"lat": goal_latlon[0], "lon": goal_latlon[1]})
        raw_route_points[-1].update({"lat": goal_latlon[0], "lon": goal_latlon[1]})

    response: dict[str, Any] = {
        "success": True,
        "mode": mode,
        "alpha": active_alpha,
        "forecast_hour": int(scenario["meta"].get("forecast_hour", 0)),
        "straight_line_km": round(straight_line_km, 1),
        "route": route_points,
        "route_raw": raw_route_points,
        "metrics": reported_metrics,
        "search_stats": {
            "nodes_expanded": search["nodes_expanded"],
            "navigable_cells": risk_grid["summary"]["navigable_cells"],
            "blocked_cells": risk_grid["summary"]["blocked_cells"],
            "total_cost_km_equivalent": round(
                float(search["total_cost_km_equivalent"]), 1
            ),
            "total_cost": round(float(search["total_cost_km_equivalent"]), 3),
            "cost_units": "hours" if mode == "fastest" else "km_equivalent",
        },
    }
    eta_hours = float(reported_metrics["eta_hours"])
    response["timing"] = {
        "departure_hour": round(departure_hour, 2),
        "arrival_hour": round(departure_hour + eta_hours, 2),
        "beyond_forecast_horizon": bool(search.get("beyond_forecast_horizon", False) or departure_hour + eta_hours > max(forecast_data or {24: None})),
        "snapshots_used": search.get("snapshots_used", [int(scenario["meta"].get("forecast_hour", 0))]),
    }

    if start_cell != start_original:
        response["start_snapped_from"] = _requested_point(
            start_latlon, start_original
        )
        response["start_snapped_to"] = _route_point(start_cell, grid_cfg)
    if goal_cell != goal_original:
        response["destination_snapped_from"] = _requested_point(
            goal_latlon, goal_original
        )
        response["destination_snapped_to"] = _route_point(goal_cell, grid_cfg)
    return response
