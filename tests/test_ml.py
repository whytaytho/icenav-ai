import json

from backend.engine.iceberg_features import FEATURE_NAMES, build_examples, group_split
from backend.engine.iceberg import propagate_iceberg
from backend.data.generate_scenario import build_scenario
from backend.main import APP_CONFIG


def _track(berg):
    return [{"berg_id": berg, "timestamp": f"2020-01-0{day}T00:00:00Z", "lat": -68 + day * .01, "lon": 74 + day * .02} for day in range(1, 6)]


def test_group_split_has_no_berg_leakage():
    examples = build_examples(_track("A"), 24) + build_examples(_track("B"), 24)
    train, test = group_split(examples, .5)
    assert {item["berg_id"] for item in train}.isdisjoint({item["berg_id"] for item in test})


def test_feature_order_matches_metadata():
    metadata = json.load(open("backend/models/iceberg_model_meta.json", encoding="utf-8"))
    assert metadata["feature_names"] == FEATURE_NAMES


def test_missing_model_falls_back_deterministically():
    cfg = json.loads(json.dumps(APP_CONFIG))
    cfg["forecast"]["drift_model"] = "ml"
    cfg["forecast"]["ml_model_path"] = "backend/models/missing.pkl"
    scenario = build_scenario()
    first = propagate_iceberg(scenario["icebergs"][0], scenario, 6, cfg)
    second = propagate_iceberg(scenario["icebergs"][0], scenario, 6, cfg)
    assert first == second and first["drift_model_used"] == "free_drift"
