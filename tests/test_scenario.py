import json
from pathlib import Path

from backend.data.generate_scenario import build_scenario


SCENARIO_PATH = Path(__file__).parents[1] / "backend" / "data" / "demo_scenario.json"


def test_committed_scenario_matches_generator() -> None:
    committed = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    assert committed == build_scenario()


def test_scenario_contract_and_counts() -> None:
    scenario = build_scenario()
    assert set(scenario) == {"meta", "vessel", "destination", "icebergs", "cells"}
    assert set(scenario["meta"]) == {
        "scenario_id",
        "generated_at",
        "forecast_hour",
        "bounds",
        "grid",
        "data_source",
    }
    assert set(scenario["meta"]["bounds"]) == {
        "lat_min",
        "lat_max",
        "lon_min",
        "lon_max",
    }
    assert set(scenario["meta"]["grid"]) == {
        "rows",
        "cols",
        "cell_height_km",
        "cell_width_km",
    }
    assert scenario["meta"]["grid"]["rows"] == 30
    assert scenario["meta"]["grid"]["cols"] == 30
    assert scenario["meta"]["forecast_hour"] == 0
    assert scenario["meta"]["data_source"] == "synthetic"
    assert len(scenario["cells"]) == 900
    assert len(scenario["icebergs"]) == 8
    assert set(scenario["vessel"]) == {
        "id",
        "name",
        "lat",
        "lon",
        "speed_knots_open_water",
    }
    assert set(scenario["destination"]) == {"name", "lat", "lon"}
    assert all(
        set(iceberg)
        == {
            "id",
            "lat",
            "lon",
            "velocity_kmh",
            "heading_deg",
            "radius_km",
            "safety_buffer_km",
        }
        for iceberg in scenario["icebergs"]
    )
    assert all(
        set(cell)
        == {
            "row",
            "col",
            "lat",
            "lon",
            "ice_concentration",
            "wind_speed_ms",
            "wind_direction_deg",
            "current_speed_ms",
            "current_direction_deg",
            "is_land",
            "is_navigable",
        }
        for cell in scenario["cells"]
    )
    assert any(iceberg["id"] == "IB-04" for iceberg in scenario["icebergs"])
    assert any(cell["is_land"] for cell in scenario["cells"])
    assert all(0.0 <= cell["ice_concentration"] <= 1.0 for cell in scenario["cells"])
    assert all(not cell["is_navigable"] for cell in scenario["cells"] if cell["is_land"])
