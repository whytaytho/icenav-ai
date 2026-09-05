"""Offline-only scenario discovery and loading."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .schema import validate_scenario

LOGGER = logging.getLogger(__name__)


class ScenarioRegistry:
    def __init__(self, data_dir: Path, real_glob: str = "real_scenario_*.json"):
        self.data_dir = data_dir
        self.real_glob = real_glob
        self._scenarios: dict[str, Path] = {}
        self.refresh()

    def refresh(self) -> None:
        paths = [self.data_dir / "demo_scenario.json", *sorted(self.data_dir.glob(self.real_glob))]
        self._scenarios = {}
        for path in paths:
            if not path.exists():
                continue
            try:
                scenario = validate_scenario(json.loads(path.read_text(encoding="utf-8")))
                self._scenarios[str(scenario["meta"]["scenario_id"])] = path
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                LOGGER.warning("Ignoring invalid scenario %s: %s", path, exc)

    def list(self) -> list[dict[str, Any]]:
        return [{"scenario_id": scenario_id, "data_source": self.load(scenario_id)["meta"]["data_source"]} for scenario_id in sorted(self._scenarios)]

    def load(self, scenario_id: str | None = None) -> dict[str, Any]:
        selected = scenario_id or "prydz-bay-demo-v1"
        path = self._scenarios.get(selected)
        if path is None:
            LOGGER.warning("Scenario %s unavailable; falling back to synthetic", selected)
            path = self._scenarios.get("prydz-bay-demo-v1")
        if path is None:
            raise RuntimeError("No valid synthetic scenario is available")
        return validate_scenario(json.loads(path.read_text(encoding="utf-8")))
