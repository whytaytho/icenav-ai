"""Leakage-safe track-only feature engineering in a local metric frame."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .geo import bearing_deg, haversine_km
from .iceberg import to_components

FEATURE_NAMES = [
    "lat", "lon", "velocity_north_kmh", "velocity_east_kmh",
    "previous_velocity_north_kmh", "previous_velocity_east_kmh",
    "hours_since_previous", "prediction_horizon_hours", "day_of_year",
]


def _stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def metric_displacement(start: dict[str, Any], end: dict[str, Any]) -> tuple[float, float]:
    distance = haversine_km(start["lat"], start["lon"], end["lat"], end["lon"])
    east, north = to_components(distance, bearing_deg(start["lat"], start["lon"], end["lat"], end["lon"]))
    return north, east


def build_examples(track: list[dict[str, Any]], horizon_hours: int = 24) -> list[dict[str, Any]]:
    """Build examples using only observations at or before each prediction time."""
    ordered = sorted(track, key=lambda item: item["timestamp"])
    examples = []
    for index in range(2, len(ordered) - 1):
        prev2, prev, current = ordered[index - 2:index + 1]
        target = next((item for item in ordered[index + 1:] if abs((_stamp(item["timestamp"]) - _stamp(current["timestamp"])).total_seconds() / 3600 - horizon_hours) <= 1), None)
        if target is None:
            continue
        hours = (_stamp(current["timestamp"]) - _stamp(prev["timestamp"])).total_seconds() / 3600
        previous_hours = (_stamp(prev["timestamp"]) - _stamp(prev2["timestamp"])).total_seconds() / 3600
        if hours <= 0 or previous_hours <= 0:
            continue
        north, east = metric_displacement(prev, current)
        previous_north, previous_east = metric_displacement(prev2, prev)
        target_north, target_east = metric_displacement(current, target)
        features = [current["lat"], current["lon"], north / hours, east / hours, previous_north / previous_hours, previous_east / previous_hours, hours, horizon_hours, _stamp(current["timestamp"]).timetuple().tm_yday]
        examples.append({"berg_id": current["berg_id"], "prediction_time": current["timestamp"], "latest_feature_timestamp": current["timestamp"], "target_timestamp": target["timestamp"], "features": features, "target": [target_north, target_east]})
    return examples


def group_split(examples: list[dict[str, Any]], test_fraction: float = 0.2) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bergs = sorted({item["berg_id"] for item in examples})
    count = max(1, round(len(bergs) * test_fraction))
    test_bergs = set(bergs[-count:])
    return [item for item in examples if item["berg_id"] not in test_bergs], [item for item in examples if item["berg_id"] in test_bergs]


def temporal_split(examples: list[dict[str, Any]], test_fraction: float = 0.2) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(examples, key=lambda item: item["prediction_time"])
    split = max(1, int(len(ordered) * (1 - test_fraction)))
    return ordered[:split], ordered[split:]
