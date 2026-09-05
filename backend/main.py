"""FastAPI application for the offline ICE-NAV AI Milestone 8 prototype."""

from __future__ import annotations

import json
import math
import csv
import pickle
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.engine.comparison import compare_routes
from backend.engine.risk import compute_risk_grid
from backend.engine.routing import plan_route
from backend.api.forecast import ForecastCache
from backend.engine.explain import explain_route_change
from backend.engine.hazard import detect_hazard, evaluate_route
from backend.engine.scenarios import ScenarioRegistry
from backend.engine.validation import run_backtest

SCENARIO_PATH = Path(__file__).resolve().parent / "data" / "demo_scenario.json"
CONFIG_PATH = Path(__file__).resolve().parent / "config" / "weights.yaml"


class Coordinate(BaseModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)


class TimedCoordinate(Coordinate):
    arrival_hour: Optional[float] = None


class RouteRequest(BaseModel):
    start: Coordinate
    destination: Coordinate
    mode: str
    forecast_hour: int = 0
    departure_hour: Optional[float] = None


class RouteComparisonRequest(BaseModel):
    start: Coordinate
    destination: Coordinate
    forecast_hour: int = 0


class RerouteRequest(BaseModel):
    current_route: list[TimedCoordinate]
    current_position: Coordinate
    destination: Coordinate
    mode: str = "balanced"
    departure_hour: float = 0.0
    evaluate_at_hour: int = 6


def _read_config(config_path: Path) -> dict[str, Any]:
    try:
        config_document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Risk config file not found: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise RuntimeError(f"Risk config contains invalid YAML: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"Risk config could not be read: {exc}") from exc
    if not isinstance(config_document, dict):
        raise RuntimeError("Configuration root must be a mapping")
    return config_document


def _validate_risk_model(config_document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config_document.get("risk_model"), dict):
        raise RuntimeError("Risk config is missing the risk_model block")
    risk_model = config_document["risk_model"]
    expected_weights = {"sea_ice", "iceberg", "wind", "current"}
    weights = risk_model.get("weights")
    if not isinstance(weights, dict) or set(weights) != expected_weights:
        raise RuntimeError("Risk config must define exactly four component weights")
    if not math.isclose(
        sum(float(weight) for weight in weights.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise RuntimeError("Risk component weights must sum to 1.0")
    return risk_model


def load_risk_config(config_path: Path) -> dict[str, Any]:
    """Load only the validated risk block, retained for focused tests/tools."""
    return _validate_risk_model(_read_config(config_path))


def load_app_config(config_path: Path) -> dict[str, Any]:
    """Load and validate all active application configuration once."""
    config = _read_config(config_path)
    _validate_risk_model(config)
    required_blocks = {
        "route_modes",
        "route_metrics",
        "vessel_model",
        "routing",
        "fuel_model",
        "recommendation",
        "forecast",
        "hazard",
        "ingestion",
    }
    missing = required_blocks.difference(config)
    if missing:
        raise RuntimeError(
            f"Application config is missing blocks: {', '.join(sorted(missing))}"
        )

    route_modes = config["route_modes"]
    if set(route_modes) != {"fastest", "balanced", "safest"}:
        raise RuntimeError("route_modes must define fastest, balanced, and safest")
    if any(float(mode["alpha"]) < 0.0 for mode in route_modes.values()):
        raise RuntimeError("Route mode alpha values must be non-negative")

    route_metric_weights = config["route_metrics"]
    if not math.isclose(
        float(route_metric_weights["mean_weight"])
        + float(route_metric_weights["max_weight"]),
        1.0,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise RuntimeError("Route metric weights must sum to 1.0")

    resistance = config["fuel_model"]["resistance_by_ice"]
    if any(float(factor) < 1.0 for _, factor in resistance):
        raise RuntimeError("Fuel resistance factors must all be at least 1.0")
    return config


APP_CONFIG = load_app_config(CONFIG_PATH)
RISK_CONFIG = APP_CONFIG["risk_model"]

app = FastAPI(
    title="ICE-NAV AI API",
    description="Offline forecast, hazard, ML trajectory, and validation API",
    version="0.8.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def load_scenario() -> dict[str, Any]:
    """Load and minimally validate the committed scenario."""
    try:
        scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Scenario file not found: {SCENARIO_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Scenario file contains invalid JSON: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"Scenario file could not be read: {exc}") from exc

    required_sections = {"meta", "vessel", "destination", "icebergs", "cells"}
    missing_sections = required_sections.difference(scenario)
    if missing_sections:
        missing = ", ".join(sorted(missing_sections))
        raise RuntimeError(f"Scenario file is missing required sections: {missing}")
    return scenario


DATA_DIR = SCENARIO_PATH.parent
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ScenarioRegistry(DATA_DIR, APP_CONFIG["ingestion"]["real_scenario_glob"])
FORECASTS = ForecastCache(SCENARIOS.load(), APP_CONFIG)


def _coordinates(coordinate: Coordinate) -> tuple[float, float]:
    return float(coordinate.lat), float(coordinate.lon)


def _validate_forecast_hour(forecast_hour: int) -> None:
    if forecast_hour not in FORECASTS.horizons:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported forecast hour. Valid values: {FORECASTS.horizons}",
        )


def _forecast_data() -> dict[int, tuple[dict[str, Any], dict[str, Any]]]:
    return {hour: (FORECASTS.scenario(hour), FORECASTS.risk(hour)) for hour in FORECASTS.horizons}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/scenarios")
def scenarios() -> list[dict[str, Any]]:
    return SCENARIOS.list()


@app.get("/environment/current")
def environment_current(scenario: Optional[str] = None) -> dict[str, Any]:
    try:
        return load_scenario() if scenario is None else SCENARIOS.load(scenario)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/environment/risk")
def environment_risk(forecast_hour: int = 0) -> dict[str, Any]:
    _validate_forecast_hour(forecast_hour)
    return FORECASTS.risk(forecast_hour)


@app.get("/forecast/horizons")
def forecast_horizons() -> dict[str, list[int]]:
    return {"horizons_hours": FORECASTS.horizons}


@app.get("/forecast")
def forecast(hour: int = 0) -> dict[str, Any]:
    _validate_forecast_hour(hour)
    return FORECASTS.scenario(hour)


@app.post("/forecast/rebuild")
def forecast_rebuild(drift_model: Optional[str] = None) -> dict[str, Any]:
    if drift_model is not None:
        if drift_model not in {"persistence", "free_drift", "ml"}:
            raise HTTPException(status_code=400, detail="drift_model must be persistence, free_drift, or ml")
        if drift_model == "ml" and not (REPOSITORY_ROOT / APP_CONFIG["forecast"]["ml_model_path"]).exists():
            drift_model = "free_drift"
        APP_CONFIG["forecast"]["drift_model"] = drift_model
    FORECASTS.rebuild()
    return {"status": "rebuilt", "horizons_hours": FORECASTS.horizons, "drift_model_used": APP_CONFIG["forecast"]["drift_model"]}


@app.get("/icebergs/trajectory")
def iceberg_trajectory(id: str = Query(...)) -> dict[str, Any]:
    try:
        return FORECASTS.trajectory(id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/config/risk")
def config_risk() -> dict[str, Any]:
    return RISK_CONFIG


@app.post("/route")
def route(request: RouteRequest) -> dict[str, Any]:
    _validate_forecast_hour(request.forecast_hour)
    if request.mode not in APP_CONFIG["route_modes"]:
        raise HTTPException(
            status_code=400,
            detail="mode must be one of: fastest, balanced, safest",
        )
    try:
        scenario = FORECASTS.scenario(request.forecast_hour)
        risk_grid = FORECASTS.risk(request.forecast_hour)
        return plan_route(
            scenario,
            risk_grid,
            _coordinates(request.start),
            _coordinates(request.destination),
            float(APP_CONFIG["route_modes"][request.mode]["alpha"]),
            APP_CONFIG,
            mode=request.mode,
            forecast_data=_forecast_data() if request.departure_hour is not None else None,
            departure_hour=float(request.departure_hour or 0.0),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/routes/compare")
def routes_compare(request: RouteComparisonRequest) -> dict[str, Any]:
    _validate_forecast_hour(request.forecast_hour)
    try:
        scenario = FORECASTS.scenario(request.forecast_hour)
        risk_grid = FORECASTS.risk(request.forecast_hour)
        return compare_routes(
            scenario,
            risk_grid,
            _coordinates(request.start),
            _coordinates(request.destination),
            APP_CONFIG,
            forecast_data=None,
            departure_hour=float(request.forecast_hour),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/route/reroute")
def route_reroute(request: RerouteRequest) -> dict[str, Any]:
    _validate_forecast_hour(request.evaluate_at_hour)
    if request.mode not in APP_CONFIG["route_modes"]:
        raise HTTPException(status_code=400, detail="mode must be fastest, balanced, or safest")
    route_points = [point.model_dump() for point in request.current_route]
    base_scenario, forecast_scenario = FORECASTS.scenario(0), FORECASTS.scenario(request.evaluate_at_hour)
    base_risk, forecast_risk = FORECASTS.risk(0), FORECASTS.risk(request.evaluate_at_hour)
    forecasts = _forecast_data()
    base_eval = evaluate_route(route_points, base_scenario, base_risk, APP_CONFIG, request.departure_hour)
    forecast_eval = evaluate_route(route_points, forecast_scenario, forecast_risk, APP_CONFIG, request.departure_hour)
    hazard = detect_hazard(route_points, base_eval, forecast_eval, APP_CONFIG)
    if not hazard["alert"]:
        return {**hazard, "original_route": forecast_eval, "alternate_route": None, "explanation": None}
    alternate = plan_route(forecast_scenario, forecast_risk, _coordinates(request.current_position), _coordinates(request.destination), float(APP_CONFIG["route_modes"][request.mode]["alpha"]), APP_CONFIG, mode=request.mode, departure_hour=request.evaluate_at_hour)
    alternate_eval = evaluate_route(alternate.get("route_raw", []), forecast_scenario, forecast_risk, APP_CONFIG, request.evaluate_at_hour) if alternate.get("success") else None
    if not alternate.get("success") or alternate_eval["safety_score"] <= forecast_eval["safety_score"]:
        return {**hazard, "original_route": forecast_eval, "alternate_route": None, "message": "No safer route meeting the configured constraints was found; human decision required.", "explanation": explain_route_change(base_eval, forecast_eval, hazard)}
    alternate["forecast_evaluation"] = alternate_eval
    explained_alternate = {**alternate, "metrics": {**alternate["metrics"], "safety_score": alternate_eval["safety_score"]}}
    explanation = explain_route_change(base_eval, forecast_eval, hazard, explained_alternate)
    current_metrics = {"safety_score": forecast_eval["safety_score"], "distance_km": 0.0, "eta_hours": 0.0, "fuel_index": 0.0}
    comparison = {}
    for key in ("safety_score", "distance_km", "eta_hours", "fuel_index"):
        original = current_metrics[key]
        new = alternate_eval["safety_score"] if key == "safety_score" else alternate["metrics"][key]
        comparison[key] = {"original": original, "alternate": new, "delta": round(new-original, 1)}
    return {**hazard, "original_route": forecast_eval, "alternate_route": alternate, "explanation": explanation, "comparison": comparison}


def _historical_tracks() -> dict[str, list[dict[str, Any]]]:
    path = DATA_DIR / "historical" / "iceberg_tracks.csv"
    tracks: dict[str, list[dict[str, Any]]] = {}
    if not path.exists():
        return tracks
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            tracks.setdefault(row["berg_id"], []).append({"berg_id": row["berg_id"], "timestamp": row["timestamp"], "lat": float(row["lat"]), "lon": float(row["lon"])})
    return tracks


@app.get("/validation/options")
def validation_options() -> dict[str, Any]:
    tracks = _historical_tracks()
    summary = None
    try:
        summary = json.loads((REPOSITORY_ROOT / APP_CONFIG["forecast"]["ml_metadata_path"]).read_text(encoding="utf-8"))["metrics"]
    except (OSError, KeyError, json.JSONDecodeError):
        pass
    return {"berg_ids": sorted(berg_id for berg_id, track in tracks.items() if len(track) >= 4), "validated_horizons_hours": [24], "data_source": "BYU/NIC Consolidated Antarctic Iceberg Tracking Database v8.0", "summary": summary}


@app.get("/validation/backtest")
def validation_backtest(berg_id: str, t0: Optional[str] = None, model: str = "persistence") -> dict[str, Any]:
    tracks = _historical_tracks()
    if berg_id not in tracks:
        raise HTTPException(status_code=404, detail="Historical iceberg not found")
    track = tracks[berg_id]
    selected_t0 = t0 or track[max(2, len(track)//2)]["timestamp"]
    predictor: Any = model
    if model == "ml":
        try:
            with (REPOSITORY_ROOT / APP_CONFIG["forecast"]["ml_model_path"]).open("rb") as source:
                predictor = pickle.load(source)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"ML model unavailable: {exc}") from exc
    elif model == "free_drift":
        return {"berg_id": berg_id, "t0": selected_t0, "model": model, "available": False, "reason": "No collocated historical wind/current dataset was confirmed; no free-drift accuracy claim is made."}
    try:
        return run_backtest(track, selected_t0, [24], predictor, APP_CONFIG)
    except (ValueError, StopIteration) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
