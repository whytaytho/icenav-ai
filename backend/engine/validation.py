"""Historical position backtests with strict pre-T0 feature boundaries."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from .geo import bearing_deg, destination_point, haversine_km
from .iceberg_features import build_examples, metric_displacement


def error_statistics(errors: list[float]) -> dict[str, float | int]:
    if not errors:
        return {"sample_size": 0, "mean_error_km": 0.0, "median_error_km": 0.0, "rmse_km": 0.0, "p90_error_km": 0.0}
    ordered = sorted(errors)
    return {"sample_size": len(errors), "mean_error_km": round(sum(errors) / len(errors), 3), "median_error_km": round(ordered[len(ordered)//2], 3), "rmse_km": round(math.sqrt(sum(value * value for value in errors) / len(errors)), 3), "p90_error_km": round(ordered[min(len(ordered)-1, int(.9*len(ordered)))], 3)}


def run_backtest(track_data: list[dict[str, Any]], t0: str, horizons: list[int], model: Any, cfg: dict[str, Any]) -> dict[str, Any]:
    ordered = sorted(track_data, key=lambda item: item["timestamp"])
    index = next(index for index, item in enumerate(ordered) if item["timestamp"] == t0)
    if index < 1:
        raise ValueError("T0 requires at least one prior observation")
    current, previous = ordered[index], ordered[index - 1]
    current_time = datetime.fromisoformat(t0.replace("Z", "+00:00"))
    prior_hours = (current_time - datetime.fromisoformat(previous["timestamp"].replace("Z", "+00:00"))).total_seconds()/3600
    north, east = metric_displacement(previous, current)
    speed = math.hypot(north, east) / prior_hours
    heading = math.degrees(math.atan2(east, north)) % 360
    predictions = []
    for horizon in horizons:
        target_time = current_time + timedelta(hours=horizon)
        observed = next((item for item in ordered[index+1:] if datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")) == target_time), None)
        if observed is None:
            continue
        if model == "persistence":
            predicted_lat, predicted_lon = destination_point(current["lat"], current["lon"], heading, speed * horizon)
        elif hasattr(model, "predict"):
            example = build_examples(ordered[:index+2], horizon)
            if not example:
                continue
            delta_north, delta_east = model.predict([example[-1]["features"]])[0]
            predicted_lat, predicted_lon = destination_point(current["lat"], current["lon"], math.degrees(math.atan2(delta_east, delta_north)) % 360, math.hypot(delta_north, delta_east))
        else:
            continue
        error = haversine_km(predicted_lat, predicted_lon, observed["lat"], observed["lon"])
        predictions.append({"horizon_hours": horizon, "predicted": {"lat": predicted_lat, "lon": predicted_lon}, "observed": {"lat": observed["lat"], "lon": observed["lon"]}, "error_km": round(error, 3), "feature_cutoff": t0})
    return {"berg_id": current["berg_id"], "t0": t0, "model": "ml" if hasattr(model, "predict") else str(model), "predictions": predictions, "statistics": error_statistics([item["error_km"] for item in predictions])}
