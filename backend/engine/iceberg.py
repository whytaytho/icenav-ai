"""Deterministic iceberg propagation for forecast snapshots.

The free-drift baseline adds ocean-current velocity to a configurable fraction
of wind velocity. A roughly two-percent wind contribution is a widely used
first-order approximation, but the coefficient varies with iceberg geometry,
draft, and sail area. TODO(citation): locate and read an appropriate scientific
reference before presenting this coefficient as sourced.

Directions are degrees clockwise from true north and wind direction means the
direction toward which the vector acts. Forward Euler integration uses small,
configurable substeps and therefore has first-order truncation error.
"""

from __future__ import annotations

import json
import logging
import math
import pickle
from functools import lru_cache
from copy import deepcopy
from pathlib import Path
from typing import Any

from .geo import MPS_TO_KMH, destination_point
from .grid import GridConfig, latlon_to_cell

LOGGER = logging.getLogger(__name__)


class FeatureOrderMismatchError(ValueError):
    pass


def to_components(speed: float, direction_deg: float) -> tuple[float, float]:
    """Return east and north components for a compass-bearing vector."""
    direction_rad = math.radians(direction_deg % 360.0)
    return speed * math.sin(direction_rad), speed * math.cos(direction_rad)


def from_components(east: float, north: float) -> tuple[float, float]:
    """Return speed and compass direction normalized to ``[0, 360)``."""
    return math.hypot(east, north), math.degrees(math.atan2(east, north)) % 360.0


def persistence_velocity(berg: dict[str, Any]) -> tuple[float, float]:
    return float(berg["velocity_kmh"]), float(berg["heading_deg"]) % 360.0


def free_drift_velocity(cell: dict[str, Any], cfg: dict[str, Any]) -> tuple[float, float]:
    forecast_cfg = cfg.get("forecast", cfg)
    wind_factor = float(forecast_cfg["iceberg_wind_factor"])
    wind_east, wind_north = to_components(
        float(cell["wind_speed_ms"]), float(cell["wind_direction_deg"])
    )
    current_east, current_north = to_components(
        float(cell["current_speed_ms"]), float(cell["current_direction_deg"])
    )
    east_kmh = (current_east + wind_factor * wind_east) * MPS_TO_KMH
    north_kmh = (current_north + wind_factor * wind_north) * MPS_TO_KMH
    return from_components(east_kmh, north_kmh)


def _grid(scenario: dict[str, Any]) -> GridConfig:
    meta = scenario["meta"]
    return GridConfig(**meta["bounds"], rows=meta["grid"]["rows"], cols=meta["grid"]["cols"])


def _cell_at(scenario: dict[str, Any], lat: float, lon: float) -> dict[str, Any]:
    grid = _grid(scenario)
    row, col = latlon_to_cell(
        min(max(lat, grid.lat_min), grid.lat_max),
        min(max(lon, grid.lon_min), grid.lon_max),
        grid,
    )
    return scenario["cells"][row * grid.cols + col]


def _inside(scenario: dict[str, Any], lat: float, lon: float) -> bool:
    bounds = scenario["meta"]["bounds"]
    return bounds["lat_min"] <= lat <= bounds["lat_max"] and bounds["lon_min"] <= lon <= bounds["lon_max"]


def propagate_iceberg(
    berg: dict[str, Any], scenario: dict[str, Any], hours: float, cfg: dict[str, Any]
) -> dict[str, Any]:
    """Advance one iceberg without mutating inputs; flag corridor exits."""
    result = deepcopy(berg)
    if hours <= 0:
        result["exited_bounds"] = not _inside(scenario, float(result["lat"]), float(result["lon"]))
        return result
    forecast_cfg = cfg.get("forecast", cfg)
    model = str(forecast_cfg.get("drift_model", "free_drift"))
    if model == "ml":
        try:
            north_km, east_km = _ml_displacement(result, hours, cfg)
            distance = math.hypot(north_km, east_km)
            heading = math.degrees(math.atan2(east_km, north_km)) % 360.0
            lat, lon = destination_point(float(result["lat"]), float(result["lon"]), heading, distance)
            result.update(lat=round(lat, 6), lon=round(lon, 6), velocity_kmh=round(distance / hours, 4), heading_deg=round(heading, 2), drift_model_used="ml")
            result["exited_bounds"] = not _inside(scenario, lat, lon)
            return result
        except Exception as exc:
            if not bool(forecast_cfg.get("ml_fallback_on_error", True)):
                raise
            LOGGER.warning("ML inference failed; using free drift: %s", exc)
            model = "free_drift"
    step_limit = float(forecast_cfg.get("substep_hours", 0.5))
    elapsed = 0.0
    while elapsed < hours:
        step = min(step_limit, hours - elapsed)
        if model == "persistence":
            speed_kmh, heading = persistence_velocity(berg)
        else:
            speed_kmh, heading = free_drift_velocity(
                _cell_at(scenario, float(result["lat"]), float(result["lon"])), cfg
            )
        lat, lon = destination_point(float(result["lat"]), float(result["lon"]), heading, speed_kmh * step)
        result.update(lat=round(lat, 6), lon=round(lon, 6), velocity_kmh=round(speed_kmh, 4), heading_deg=round(heading, 2))
        elapsed += step
    result["exited_bounds"] = not _inside(scenario, float(result["lat"]), float(result["lon"]))
    result["drift_model_used"] = model
    return result


def propagate_all(scenario: dict[str, Any], hours: float, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    return [propagate_iceberg(berg, scenario, hours, cfg) for berg in scenario["icebergs"]]


class OptionalMLPredictor:
    """Load a model once and fail safely to the free-drift baseline."""

    def __init__(self, cfg: dict[str, Any], repository_root: Path):
        forecast_cfg = cfg["forecast"]
        self.model = None
        self.metadata: dict[str, Any] | None = None
        self.error: str | None = None
        try:
            model_path = repository_root / forecast_cfg["ml_model_path"]
            metadata_path = repository_root / forecast_cfg["ml_metadata_path"]
            self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            with model_path.open("rb") as model_file:
                self.model = pickle.load(model_file)
        except Exception as exc:  # optional artifact must never break the demo
            self.error = str(exc)
            LOGGER.warning("ML iceberg model unavailable; using free drift: %s", exc)

    @property
    def available(self) -> bool:
        return self.model is not None and self.metadata is not None


@lru_cache(maxsize=4)
def _load_ml(model_path: str, metadata_path: str) -> tuple[Any, dict[str, Any]]:
    from .iceberg_features import FEATURE_NAMES
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    if metadata.get("feature_names") != FEATURE_NAMES:
        raise FeatureOrderMismatchError("ML feature order does not match model metadata")
    with Path(model_path).open("rb") as source:
        return pickle.load(source), metadata


def warm_ml_model(cfg: dict[str, Any], repository_root: Path) -> dict[str, Any] | None:
    """Load and validate the optional model once during application startup."""
    forecast_cfg = cfg["forecast"]
    model_path = (repository_root / forecast_cfg["ml_model_path"]).resolve()
    metadata_path = (repository_root / forecast_cfg["ml_metadata_path"]).resolve()
    forecast_cfg["ml_model_path"] = str(model_path)
    forecast_cfg["ml_metadata_path"] = str(metadata_path)
    try:
        _, metadata = _load_ml(str(model_path), str(metadata_path))
        forecast_cfg["ml_validation_metadata"] = metadata
        return metadata
    except FeatureOrderMismatchError:
        raise
    except Exception as exc:
        forecast_cfg["ml_validation_metadata"] = None
        LOGGER.warning("ML iceberg model unavailable at startup; free drift remains available: %s", exc)
        return None


def _ml_displacement(berg: dict[str, Any], hours: float, cfg: dict[str, Any]) -> tuple[float, float]:
    from .iceberg_features import FEATURE_NAMES
    forecast_cfg = cfg["forecast"]
    model_path = str(Path(forecast_cfg["ml_model_path"]).resolve())
    metadata_path = str(Path(forecast_cfg["ml_metadata_path"]).resolve())
    model, _ = _load_ml(model_path, metadata_path)
    east_velocity, north_velocity = to_components(float(berg["velocity_kmh"]), float(berg["heading_deg"]))
    features = [float(berg["lat"]), float(berg["lon"]), north_velocity, east_velocity, north_velocity, east_velocity, 24.0, float(hours), 1.0]
    if len(features) != len(FEATURE_NAMES):
        raise ValueError("ML inference feature count mismatch")
    north_km, east_km = model.predict([features])[0]
    distance = math.hypot(float(north_km), float(east_km))
    maximum = float(forecast_cfg.get("max_iceberg_speed_kmh", 5.0)) * max(hours, 1e-9)
    if distance > maximum:
        scale = maximum / distance
        north_km, east_km = north_km * scale, east_km * scale
    return float(north_km), float(east_km)
