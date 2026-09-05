import json

from backend.data.generate_scenario import build_scenario
from backend.engine.schema import validate_scenario
from backend.engine.scenarios import ScenarioRegistry
from backend.ingestion.preprocess import apply_observations, transform_roundtrip


def test_projection_roundtrip():
    lat, lon = transform_roundtrip(-68.0, 75.0)
    assert abs(lat + 68.0) < 1e-7 and abs(lon - 75.0) < 1e-7


def test_missing_data_is_flagged_not_zeroed():
    scenario = apply_observations(build_scenario(), {}, "confirmed_source", "real-test")
    assert all(cell["data_quality"] == "missing" and not cell["is_navigable"] for cell in scenario["cells"])
    validate_scenario(scenario)


def test_registry_falls_back_to_synthetic(tmp_path):
    base = build_scenario()
    (tmp_path / "demo_scenario.json").write_text(json.dumps(base), encoding="utf-8")
    registry = ScenarioRegistry(tmp_path)
    assert registry.load("absent")["meta"]["scenario_id"] == "prydz-bay-demo-v1"
