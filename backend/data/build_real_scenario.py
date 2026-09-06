"""Build an observed-sea-ice scenario from a downloaded NSIDC granule.

Confirmed source: NOAA/NSIDC Climate Data Record of Passive Microwave Sea
Ice Concentration, Version 6 (dataset G02202, DOI 10.7265/b18j-z797). Full
provenance in docs/methodology.md.

This is a human-invoked, ahead-of-time script. It never runs on a request
path and the FastAPI application never imports it.

What this scenario does and does not contain
----------------------------------------------
Only `ice_concentration` and `data_quality` are observed. The vessel,
destination, grid and bounds are inherited unchanged from the synthetic demo
scenario, because they describe our engineering corridor, not a physical
observation. **Icebergs are intentionally empty** (`[]`): this pipeline has no
real-time iceberg position feed. The BYU/NIC database used elsewhere in this
project (docs/methodology.md, Milestone 7) is a historical archive used for
trajectory-model validation, not a live position source, so it is not a
substitute here. Do not add placeholder or synthetic icebergs to an
"observed" scenario -- that would misrepresent what was actually measured.

Usage
-----
    python -m backend.ingestion.fetch_seaice --download --date 2023-07-15
    python -m backend.data.build_real_scenario --date 2023-07-15

The default date, 2023-07-15, is mid-austral-winter, when Prydz Bay sea ice
is near its seasonal maximum and an observed scenario looks meaningfully
different from the synthetic demo. Verified against that date in this
environment: 739 of 900 cells returned a concentration (0.62-1.00, consistent
with winter pack ice), 161 were masked (land, the pole hole, or no swath
coverage) and reported missing rather than defaulted to open water.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from data.generate_scenario import GRID, build_scenario  # noqa: E402
from engine.grid import cell_to_latlon  # noqa: E402
from ingestion.fetch_seaice import PRODUCT_DOI, PRODUCT_NAME  # noqa: E402
from ingestion.preprocess import apply_observations, extract_seaice_concentrations  # noqa: E402

RAW_DIR = BACKEND_DIR / "data" / "raw"
OUTPUT_DIR = BACKEND_DIR / "data"

# Must stay consistent with weights.yaml -> ingestion.real_scenario_glob
# ("real_scenario_*.json"), which is how ScenarioRegistry discovers these.
OUTPUT_TEMPLATE = "real_scenario_{date}.json"


def _granule_path(day: date, raw_dir: Path) -> Path:
    from ingestion.fetch_seaice import granule_url

    filename = Path(granule_url(day)).name
    path = raw_dir / filename
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run "
            f"'python -m backend.ingestion.fetch_seaice --download --date {day.isoformat()}' "
            "first."
        )
    return path


def build_real_scenario(day: date, raw_dir: Path = RAW_DIR) -> dict[str, Any]:
    granule_path = _granule_path(day, raw_dir)
    concentrations = extract_seaice_concentrations(
        granule_path, GRID, cell_to_latlon, GRID.rows, GRID.cols
    )

    base = build_scenario()
    base["icebergs"] = []  # see module docstring: no real-time iceberg feed

    scenario_id = f"prydz-bay-observed-{day.isoformat()}"
    data_source = f"nsidc_g02202_v6_{day.strftime('%Y%m%d')}"
    scenario = apply_observations(
        base, concentrations, data_source, scenario_id, missing_is_navigable=False
    )
    scenario["meta"]["observed_product"] = {
        "name": PRODUCT_NAME,
        "doi": PRODUCT_DOI,
        "granule_date": day.isoformat(),
    }

    observed = sum(1 for value in concentrations.values() if value is not None)
    missing = len(concentrations) - observed
    scenario["meta"]["observation_summary"] = {
        "cells_observed": observed,
        "cells_missing": missing,
    }
    return scenario


def write_real_scenario(
    day: date, raw_dir: Path = RAW_DIR, output_dir: Path = OUTPUT_DIR
) -> tuple[Path, dict[str, Any]]:
    scenario = build_real_scenario(day, raw_dir)
    output_path = output_dir / OUTPUT_TEMPLATE.format(date=day.strftime("%Y%m%d"))
    output_path.write_text(json.dumps(scenario, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path, scenario


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=date(2023, 7, 15))
    args = parser.parse_args()

    path, scenario = write_real_scenario(args.date)
    summary = scenario["meta"]["observation_summary"]
    print(f"Wrote {path}")
    print(f"Observed {summary['cells_observed']} cells, missing {summary['cells_missing']}")
