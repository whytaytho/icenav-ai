"""Optional Random Forest training and inference helpers."""

from __future__ import annotations

import json
import math
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .iceberg_features import FEATURE_NAMES, group_split, temporal_split


def _metrics(model: Any, examples: list[dict[str, Any]]) -> dict[str, Any]:
    if not examples:
        return {"sample_size": 0}
    predictions = model.predict([item["features"] for item in examples])
    errors = [math.hypot(pred[0] - item["target"][0], pred[1] - item["target"][1]) for pred, item in zip(predictions, examples)]
    ordered = sorted(errors)
    return {
        "sample_size": len(errors), "mean_position_error_km": sum(errors) / len(errors),
        "median_position_error_km": ordered[len(ordered) // 2],
        "p90_position_error_km": ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))],
        "rmse_km": math.sqrt(sum(error * error for error in errors) / len(errors)),
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
        errors.append(math.hypot(predicted[0] - item["target"][0], predicted[1] - item["target"][1]))
    ordered = sorted(errors)
    return {"sample_size": len(errors), "mean_position_error_km": sum(errors)/len(errors), "median_position_error_km": ordered[len(ordered)//2], "p90_position_error_km": ordered[min(len(ordered)-1, int(.9*len(ordered)))], "rmse_km": math.sqrt(sum(value*value for value in errors)/len(errors))}


def train_random_forest(examples: list[dict[str, Any]], model_path: Path, metadata_path: Path) -> dict[str, Any]:
    from sklearn.ensemble import RandomForestRegressor
    import sklearn

    group_train, group_test = group_split(examples)
    temporal_train, temporal_test = temporal_split(examples)
    model = RandomForestRegressor(n_estimators=120, max_depth=14, min_samples_leaf=2, random_state=26059, n_jobs=-1)
    model.fit([item["features"] for item in group_train], [item["target"] for item in group_train])
    temporal_model = RandomForestRegressor(n_estimators=120, max_depth=14, min_samples_leaf=2, random_state=26059, n_jobs=-1)
    temporal_model.fit([item["features"] for item in temporal_train], [item["target"] for item in temporal_train])
    model_path.parent.mkdir(parents=True, exist_ok=True)
    with model_path.open("wb") as output:
        pickle.dump(model, output)
    metadata = {
        "trained_at": datetime.now(timezone.utc).isoformat(), "sklearn_version": sklearn.__version__,
        "feature_names": FEATURE_NAMES, "horizons_hours": [24], "data_source": "BYU/NIC Consolidated Antarctic Iceberg Tracking Database v8.0",
        "split_strategy": "group by berg_id; temporal holdout additionally reported", "training_samples": len(group_train),
        "metrics": {
            "group_holdout": {"ml": _metrics(model, group_test), "persistence": _baseline_metrics(group_test, "persistence"), "zero": _baseline_metrics(group_test, "zero"), "free_drift": {"available": False, "reason": "No collocated historical wind/current dataset was confirmed."}},
            "temporal_holdout": {"ml": _metrics(temporal_model, temporal_test), "persistence": _baseline_metrics(temporal_test, "persistence"), "zero": _baseline_metrics(temporal_test, "zero"), "free_drift": {"available": False, "reason": "No collocated historical wind/current dataset was confirmed."}},
        },
        "validated_resolution": "daily (+24h only)",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata
