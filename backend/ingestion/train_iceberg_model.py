"""Train the optional +24 h iceberg displacement Random Forest."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from backend.engine.iceberg_features import build_examples
from backend.engine.ml import train_random_forest

ROOT = Path(__file__).resolve().parents[2]


def load_tracks(path: Path) -> dict[str, list[dict[str, object]]]:
    tracks = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            tracks[row["berg_id"]].append({"berg_id": row["berg_id"], "timestamp": row["timestamp"], "lat": float(row["lat"]), "lon": float(row["lon"])})
    return tracks


def main() -> None:
    tracks = load_tracks(ROOT / "backend/data/historical/iceberg_tracks.csv")
    examples = [example for track in tracks.values() for example in build_examples(track, 24)]
    metadata = train_random_forest(examples, ROOT / "backend/models/iceberg_model.pkl", ROOT / "backend/models/iceberg_model_meta.json")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
