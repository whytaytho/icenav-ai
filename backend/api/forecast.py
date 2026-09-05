"""In-memory deterministic forecast and derived-risk cache."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.engine.geo import haversine_km
from backend.engine.iceberg import propagate_all
from backend.engine.risk import compute_risk_grid
from backend.engine.seaice import advect_seaice


def build_forecast_scenario(base_scenario: dict[str, Any], hours: int, cfg: dict[str, Any]) -> dict[str, Any]:
    scenario = deepcopy(base_scenario)
    scenario["meta"]["forecast_hour"] = int(hours)
    scenario["meta"]["data_source"] = "synthetic" if hours == 0 else "synthetic_forecast"
    scenario["icebergs"] = propagate_all(base_scenario, hours, cfg)
    models = sorted({berg.get("drift_model_used", cfg["forecast"].get("drift_model", "free_drift")) for berg in scenario["icebergs"]})
    scenario["meta"]["drift_model_used"] = models[0] if len(models) == 1 else "+".join(models)
    if scenario["meta"]["drift_model_used"] == "ml":
        metadata = cfg["forecast"].get("ml_validation_metadata") or {}
        validated_horizons = metadata.get("horizons_hours", [])
        scenario["meta"]["trajectory_validation"] = {
            "validated": hours in validated_horizons,
            "validated_horizons_hours": validated_horizons,
            "group_holdout": metadata.get("metrics", {}).get("group_holdout", {}).get("ml"),
            "temporal_holdout": metadata.get("metrics", {}).get("temporal_holdout", {}).get("ml"),
            "population": "giant tabular icebergs",
        }
    scenario["cells"] = advect_seaice(base_scenario, hours, cfg)
    return scenario


class ForecastCache:
    def __init__(self, base_scenario: dict[str, Any], cfg: dict[str, Any]):
        self.base_scenario = deepcopy(base_scenario)
        self.cfg = cfg
        self.scenarios: dict[int, dict[str, Any]] = {}
        self.risks: dict[tuple[int, str], dict[str, Any]] = {}
        self.rebuild()

    @property
    def horizons(self) -> list[int]:
        return [int(hour) for hour in self.cfg["forecast"]["horizons_hours"]]

    def rebuild(self) -> None:
        self.scenarios = {hour: build_forecast_scenario(self.base_scenario, hour, self.cfg) for hour in self.horizons}
        version = str(self.cfg["risk_model"]["version"])
        self.risks = {(hour, version): compute_risk_grid(scenario, self.cfg["risk_model"]) for hour, scenario in self.scenarios.items()}

    def scenario(self, hour: int) -> dict[str, Any]:
        if hour not in self.scenarios:
            raise ValueError(f"Unsupported forecast hour {hour}; valid values: {self.horizons}")
        return deepcopy(self.scenarios[hour])

    def risk(self, hour: int) -> dict[str, Any]:
        version = str(self.cfg["risk_model"]["version"])
        if (hour, version) not in self.risks:
            raise ValueError(f"Unsupported forecast hour {hour}; valid values: {self.horizons}")
        return deepcopy(self.risks[(hour, version)])

    def nearest_hour(self, hour: float) -> int:
        return min(self.horizons, key=lambda candidate: (abs(candidate - hour), candidate))

    def trajectory(self, iceberg_id: str) -> dict[str, Any]:
        points = []
        origin = next((berg for berg in self.scenarios[0]["icebergs"] if berg["id"] == iceberg_id), None)
        if origin is None:
            raise ValueError(f"Unknown iceberg id: {iceberg_id}")
        for hour in self.horizons:
            berg = next(item for item in self.scenarios[hour]["icebergs"] if item["id"] == iceberg_id)
            points.append({"forecast_hour": hour, "lat": berg["lat"], "lon": berg["lon"], "distance_from_t0_km": round(haversine_km(origin["lat"], origin["lon"], berg["lat"], berg["lon"]), 3)})
        return {"iceberg_id": iceberg_id, "drift_model_used": self.cfg["forecast"].get("drift_model", "free_drift"), "points": points}
