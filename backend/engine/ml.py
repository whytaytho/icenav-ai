"""Optional Random Forest training and inference helpers."""

from __future__ import annotations

import json
import math
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .iceberg_features import FEATURE_NAMES, group_split, temporal_split
from .geo import destination_point, haversine_km


def _position_error_km(example: dict[str, Any], prediction: list[float]) -> float:
    origin_lat, origin_lon = float(example["features"][0]), float(example["features"][1])

    def endpoint(vector: list[float]) -> tuple[float, float]:
        north_km, east_km = float(vector[0]), float(vector[1])
        distance_km = math.hypot(north_km, east_km)
        heading_deg = math.degrees(math.atan2(east_km, north_km)) % 360.0
        return destination_point(origin_lat, origin_lon, heading_deg, distance_km)

    predicted_lat, predicted_lon = endpoint(prediction)
    observed_lat, observed_lon = endpoint(example["target"])
    return haversine_km(predicted_lat, predicted_lon, observed_lat, observed_lon)


def _metrics(model: Any, examples: list[dict[str, Any]]) -> dict[str, Any]:
    if not examples:
        return {"sample_size": 0}
    predictions = model.predict([item["features"] for item in examples])
    errors = [_position_error_km(item, pred) for pred, item in zip(predictions, examples)]
    north_errors = [abs(float(pred[0]) - float(item["target"][0])) for pred, item in zip(predictions, examples)]
    east_errors = [abs(float(pred[1]) - float(item["target"][1])) for pred, item in zip(predictions, examples)]
    ordered = sorted(errors)
    return {
        "sample_size": len(errors), "mean_position_error_km": sum(errors) / len(errors),
        "median_position_error_km": ordered[len(ordered) // 2],
        "p90_position_error_km": ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))],
        "rmse_km": math.sqrt(sum(error * error for error in errors) / len(errors)),
        "mae_north_km": sum(north_errors) / len(north_errors),
        "mae_east_km": sum(east_errors) / len(east_errors),
    }


def _baseline_metrics(examples: list[dict[str, Any]], baseline: str) -> dict[str, Any]:
    if not examples:
        return {"sample_size": 0}
    errors = []
    for item in examples:
        if baseline == "persistence":
            horizon = float(item["features"][7])
            predicted = [float(item["features"][2]) * horizon, float(item["features"][3]) * horizon]
        else:
            predicted = [0.0, 0.0]
        errors.append(_position_error_km(item, predicted))
    north_errors = [
        abs((float(item["features"][2]) * float(item["features"][7]) if baseline == "persistence" else 0.0) - float(item["target"][0]))
        for item in examples
    ]
    east_errors = [
        abs((float(item["features"][3]) * float(item["features"][7]) if baseline == "persistence" else 0.0) - float(item["target"][1]))
        for item in examples
    ]
    ordered = sorted(errors)
    return {"sample_size": len(errors), "mean_position_error_km": sum(errors)/len(errors), "median_position_error_km": ordered[len(ordered)//2], "p90_position_error_km": ordered[min(len(ordered)-1, int(.9*len(ordered)))], "rmse_km": math.sqrt(sum(value*value for value in errors)/len(errors)), "mae_north_km": sum(north_errors)/len(north_errors), "mae_east_km": sum(east_errors)/len(east_errors)}


def train_random_forest(examples: list[dict[str, Any]], model_path: Path, metadata_path: Path) -> dict[str, Any]:
    from sklearn.ensemble import RandomForestRegressor
    import sklearn

    group_train, group_test = group_split(examples)
    temporal_train, temporal_test = temporal_split(examples)
    hyperparameters = {"n_estimators": 120, "max_depth": 14, "min_samples_leaf": 2, "random_state": 26059, "n_jobs": -1}
    model = RandomForestRegressor(**hyperparameters)
    model.fit([item["features"] for item in group_train], [item["target"] for item in group_train])
    temporal_model = RandomForestRegressor(**hyperparameters)
    temporal_model.fit([item["features"] for item in temporal_train], [item["target"] for item in temporal_train])
    model_path.parent.mkdir(parents=True, exist_ok=True)
    with model_path.open("wb") as output:
        pickle.dump(model, output)
    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(), "sklearn_version": sklearn.__version__,
        "feature_names": FEATURE_NAMES, "horizons_hours": [24], "data_source": "BYU/NIC Consolidated Antarctic Iceberg Tracking Database v8.0",
        "split_strategy": "group by berg_id; temporal holdout additionally reported", "training_samples": len(group_train),
        "hyperparameters": {key: value for key, value in hyperparameters.items() if key != "n_jobs"},
        "parameter_selection": "Fixed before holdout evaluation; neither holdout set was used for tuning.",
        "metrics": {
            "group_holdout": {"ml": _metrics(model, group_test), "persistence": _baseline_metrics(group_test, "persistence"), "zero": _baseline_metrics(group_test, "zero"), "free_drift": {"available": False, "reason": "No collocated historical wind/current dataset was confirmed."}},
            "temporal_holdout": {"ml": _metrics(temporal_model, temporal_test), "persistence": _baseline_metrics(temporal_test, "persistence"), "zero": _baseline_metrics(temporal_test, "zero"), "free_drift": {"available": False, "reason": "No collocated historical wind/current dataset was confirmed."}},
        },
        "validated_resolution": "daily (+24h only)",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata
