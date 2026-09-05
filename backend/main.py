"""FastAPI application for the ICE-NAV AI Milestone 1 demo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

SCENARIO_PATH = Path(__file__).resolve().parent / "data" / "demo_scenario.json"

app = FastAPI(
    title="ICE-NAV AI API",
    description="Milestone 1 deterministic Antarctic environment API",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/environment/current")
def environment_current() -> dict[str, Any]:
    try:
        return load_scenario()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

