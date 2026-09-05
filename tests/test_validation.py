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
    assert first["predictions"][0]["error_km"] >= 0
