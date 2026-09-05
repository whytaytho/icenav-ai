from datetime import datetime

import backend.engine.validation as validation
from backend.engine.validation import error_statistics, run_backtest
from backend.main import APP_CONFIG


TRACK = [{"berg_id": "T1", "timestamp": f"2020-01-0{day}T00:00:00Z", "lat": -68.0 + day * .01, "lon": 75.0} for day in range(1, 6)]


def test_error_statistics_zero_and_nonnegative():
    assert error_statistics([0])["mean_error_km"] == 0
    assert error_statistics([1, 2, 3])["mean_error_km"] >= 0


def test_backtest_is_deterministic_and_has_no_future_feature():
    first = run_backtest(TRACK, TRACK[2]["timestamp"], [24], "persistence", APP_CONFIG)
    second = run_backtest(TRACK, TRACK[2]["timestamp"], [24], "persistence", APP_CONFIG)
    assert first == second
    assert first["predictions"][0]["feature_cutoff"] == TRACK[2]["timestamp"]
    assert all(
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        <= datetime.fromisoformat(TRACK[2]["timestamp"].replace("Z", "+00:00"))
        for timestamp in first["predictions"][0]["feature_timestamps"]
    )
    assert first["predictions"][0]["error_km"] >= 0


def test_backtest_position_error_uses_haversine(monkeypatch):
    monkeypatch.setattr(validation, "haversine_km", lambda *args: 12.345)
    result = run_backtest(TRACK, TRACK[2]["timestamp"], [24], "persistence", APP_CONFIG)
    assert result["predictions"][0]["error_km"] == 12.345


def test_error_generally_grows_for_accelerating_track():
    track = [
        {"berg_id": "T2", "timestamp": f"2020-01-{day:02d}T00:00:00Z", "lat": -68.0 + (day * day) * 0.002, "lon": 75.0}
        for day in range(1, 8)
    ]
    result = run_backtest(track, track[2]["timestamp"], [24, 48, 72], "persistence", APP_CONFIG)
    errors = [item["error_km"] for item in result["predictions"]]
    assert errors == sorted(errors)
