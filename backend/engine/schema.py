"""Shared scenario contract validation."""

from __future__ import annotations

from typing import Any


def validate_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    required = {"meta", "vessel", "destination", "icebergs", "cells"}
    missing = required.difference(scenario)
    if missing:
        raise ValueError(f"Scenario missing sections: {sorted(missing)}")
    rows, cols = int(scenario["meta"]["grid"]["rows"]), int(scenario["meta"]["grid"]["cols"])
    if len(scenario["cells"]) != rows * cols:
        raise ValueError("Scenario cell count does not match grid dimensions")
    for cell in scenario["cells"]:
        concentration = float(cell["ice_concentration"])
        if not 0 <= concentration <= 1:
            raise ValueError("ice_concentration must be normalized to [0, 1]")
        if cell.get("data_quality") == "missing" and cell.get("is_navigable", True):
            raise ValueError("missing observations cannot be navigable")
    return scenario
