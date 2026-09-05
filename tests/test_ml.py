import json
import pickle

import pytest

from backend.engine.geo import destination_point, haversine_km
from backend.engine.iceberg_features import FEATURE_NAMES, build_examples, group_split, metric_displacement
from backend.engine.iceberg import FeatureOrderMismatchError, _load_ml, propagate_iceberg
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
    for split in ("group_holdout", "temporal_holdout"):
        assert "mae_north_km" in metadata["metrics"][split]["ml"]
        assert "mae_east_km" in metadata["metrics"][split]["ml"]


def test_feature_timestamps_never_exceed_prediction_time():
    examples = build_examples(_track("A"), 24)
    assert examples
    assert all(item["latest_feature_timestamp"] <= item["prediction_time"] < item["target_timestamp"] for item in examples)


def test_metric_displacement_round_trips_through_destination_point():
    start, end = _track("A")[1:3]
    north_km, east_km = metric_displacement(start, end)
    distance_km = (north_km ** 2 + east_km ** 2) ** 0.5
    heading_deg = __import__("math").degrees(__import__("math").atan2(east_km, north_km)) % 360
    lat, lon = destination_point(start["lat"], start["lon"], heading_deg, distance_km)
    assert haversine_km(lat, lon, end["lat"], end["lon"]) < 1e-6


def test_missing_model_falls_back_deterministically():
    cfg = json.loads(json.dumps(APP_CONFIG))
    cfg["forecast"]["drift_model"] = "ml"
    cfg["forecast"]["ml_model_path"] = "backend/models/missing.pkl"
    scenario = build_scenario()
    first = propagate_iceberg(scenario["icebergs"][0], scenario, 6, cfg)
    second = propagate_iceberg(scenario["icebergs"][0], scenario, 6, cfg)
    assert first == second and first["drift_model_used"] == "free_drift"


def test_corrupt_model_falls_back_without_raising(tmp_path):
    model_path = tmp_path / "corrupt.pkl"
    metadata_path = tmp_path / "meta.json"
    model_path.write_bytes(b"not-a-pickle")
    metadata_path.write_text(json.dumps({"feature_names": FEATURE_NAMES}), encoding="utf-8")
    cfg = json.loads(json.dumps(APP_CONFIG))
    cfg["forecast"].update(drift_model="ml", ml_model_path=str(model_path), ml_metadata_path=str(metadata_path))
    scenario = build_scenario()
    result = propagate_iceberg(scenario["icebergs"][0], scenario, 6, cfg)
    assert result["drift_model_used"] == "free_drift"


def test_feature_order_mismatch_raises_loudly(tmp_path):
    model_path = tmp_path / "model.pkl"
    metadata_path = tmp_path / "meta.json"
    model_path.write_bytes(pickle.dumps(object()))
    metadata_path.write_text(json.dumps({"feature_names": list(reversed(FEATURE_NAMES))}), encoding="utf-8")
    _load_ml.cache_clear()
    with pytest.raises(FeatureOrderMismatchError):
        _load_ml(str(model_path), str(metadata_path))
