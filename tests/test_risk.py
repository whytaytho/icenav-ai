import json
from copy import deepcopy
from pathlib import Path

import pytest

import backend.main as main
from backend.engine.geo import destination_point
from backend.engine.risk import (
    cell_risk,
    compute_risk_grid,
    iceberg_risk,
    is_navigable,
    sea_ice_risk,
)


SCENARIO_PATH = Path(__file__).parents[1] / "backend" / "data" / "demo_scenario.json"


@pytest.fixture
def risk_cfg() -> dict:
    return deepcopy(main.RISK_CONFIG)


def make_cell(**overrides) -> dict:
    cell = {
        "row": 0,
        "col": 0,
        "lat": -68.0,
        "lon": 75.0,
        "ice_concentration": 0.0,
        "wind_speed_ms": 0.0,
        "wind_direction_deg": 0.0,
        "current_speed_ms": 0.0,
        "current_direction_deg": 0.0,
        "is_land": False,
        "is_navigable": True,
    }
    cell.update(overrides)
    return cell


def make_iceberg(**overrides) -> dict:
    iceberg = {
        "id": "IB-TEST",
        "lat": -68.0,
        "lon": 75.0,
        "velocity_kmh": 0.0,
        "heading_deg": 0.0,
        "radius_km": 1.0,
        "safety_buffer_km": 4.0,
    }
    iceberg.update(overrides)
    return iceberg


def test_weights_load_and_sum_to_one(risk_cfg) -> None:
    assert set(risk_cfg["weights"]) == {"sea_ice", "iceberg", "wind", "current"}
    assert sum(risk_cfg["weights"].values()) == pytest.approx(1.0)


def test_invalid_weight_sum_fails_at_load_time(tmp_path) -> None:
    invalid_config = tmp_path / "invalid-weights.yaml"
    invalid_config.write_text(
        """
risk_model:
  weights:
    sea_ice: 0.5
    iceberg: 0.25
    wind: 0.15
    current: 0.15
""".strip(),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="sum to 1.0"):
        main.load_risk_config(invalid_config)


def test_land_cell_is_blocked(risk_cfg) -> None:
    assert is_navigable(make_cell(is_land=True), [], risk_cfg) == (False, "land")


def test_heavy_ice_boundary_is_inclusive(risk_cfg) -> None:
    assert is_navigable(make_cell(ice_concentration=0.80), [], risk_cfg) == (
        False,
        "heavy_ice",
    )


def test_cell_below_heavy_ice_boundary_is_navigable(risk_cfg) -> None:
    assert is_navigable(make_cell(ice_concentration=0.79), [], risk_cfg) == (
        True,
        None,
    )


def test_cell_inside_iceberg_exclusion_is_blocked(risk_cfg) -> None:
    iceberg = make_iceberg()
    lat, lon = destination_point(iceberg["lat"], iceberg["lon"], 0.0, 4.9)
    assert is_navigable(make_cell(lat=lat, lon=lon), [iceberg], risk_cfg) == (
        False,
        "iceberg_exclusion",
    )


def test_cell_outside_iceberg_exclusion_is_navigable(risk_cfg) -> None:
    iceberg = make_iceberg()
    lat, lon = destination_point(iceberg["lat"], iceberg["lon"], 0.0, 5.1)
    assert is_navigable(make_cell(lat=lat, lon=lon), [iceberg], risk_cfg) == (
        True,
        None,
    )


def test_sea_ice_risk_is_monotonic(risk_cfg) -> None:
    values = [sea_ice_risk(index / 100.0, risk_cfg) for index in range(80)]
    assert values == sorted(values)
    assert values[0] == 0.0
    assert values[-1] < 100.0


def test_every_demo_risk_value_is_bounded(risk_cfg) -> None:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    result = compute_risk_grid(scenario, risk_cfg)
    for cell in result["cells"]:
        assert 0.0 <= cell["total_risk"] <= 100.0
        for component in cell["components"].values():
            assert 0.0 <= component["raw"] <= 100.0
            assert 0.0 <= component["weighted"] <= 100.0


def test_iceberg_risk_decreases_with_distance(risk_cfg) -> None:
    iceberg = make_iceberg(lat=0.0, lon=0.0)
    risks = []
    for edge_distance_km in [2.0, 4.0, 7.0, 15.0, 25.0, 35.0]:
        lat, lon = destination_point(
            iceberg["lat"],
            iceberg["lon"],
            90.0,
            iceberg["radius_km"] + edge_distance_km,
        )
        risk, _ = iceberg_risk(lat, lon, [iceberg], risk_cfg)
        risks.append(risk)
    assert risks == sorted(risks, reverse=True)
    assert risks[0] == 100.0
    assert risks[-1] == 0.0


def test_iceberg_risk_returns_nearest_iceberg_id(risk_cfg) -> None:
    near_lat, near_lon = destination_point(0.0, 0.0, 0.0, 12.0)
    far_lat, far_lon = destination_point(0.0, 0.0, 180.0, 25.0)
    icebergs = [
        make_iceberg(id="IB-NEAR", lat=near_lat, lon=near_lon),
        make_iceberg(id="IB-FAR", lat=far_lat, lon=far_lon),
    ]
    _, nearest_id = iceberg_risk(0.0, 0.0, icebergs, risk_cfg)
    assert nearest_id == "IB-NEAR"


def test_all_zero_environment_has_zero_total_risk(risk_cfg) -> None:
    result = cell_risk(make_cell(), [], risk_cfg)
    assert result["is_navigable"] is True
    assert result["total_risk"] == 0.0


def test_maximal_navigable_inputs_are_close_to_full_risk(risk_cfg) -> None:
    iceberg_lat, iceberg_lon = destination_point(-68.0, 75.0, 0.0, 2.0)
    iceberg = make_iceberg(
        lat=iceberg_lat,
        lon=iceberg_lon,
        radius_km=0.0,
        safety_buffer_km=0.0,
    )
    result = cell_risk(
        make_cell(
            ice_concentration=0.79,
            wind_speed_ms=25.0,
            current_speed_ms=1.5,
        ),
        [iceberg],
        risk_cfg,
    )
    assert result["is_navigable"] is True
    assert result["total_risk"] == pytest.approx(
        99.375 * risk_cfg["soft_risk_scale"], abs=0.01
    )


def test_demo_grid_contract_counts_and_mixed_navigability(risk_cfg) -> None:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    result = compute_risk_grid(scenario, risk_cfg)
    expected_cells = scenario["meta"]["grid"]["rows"] * scenario["meta"]["grid"]["cols"]
    assert len(result["cells"]) == expected_cells
    assert result["summary"]["navigable_cells"] + result["summary"]["blocked_cells"] == expected_cells
    assert result["summary"]["navigable_cells"] > 0
    assert result["summary"]["blocked_cells"] > 0
    assert result["meta"]["risk_model_version"] == risk_cfg["version"]


def test_risk_grid_is_byte_deterministic(risk_cfg) -> None:
    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    first = json.dumps(compute_risk_grid(scenario, risk_cfg), sort_keys=True)
    second = json.dumps(compute_risk_grid(scenario, risk_cfg), sort_keys=True)
    assert first.encode("utf-8") == second.encode("utf-8")
