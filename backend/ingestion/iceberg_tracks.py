"""Parse the confirmed BYU/NIC consolidated iceberg archive into tidy CSV."""

from __future__ import annotations

import argparse
import csv
import io
import statistics
import urllib.request
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

SOURCE_URL = "https://www.scp.byu.edu/data/iceberg/consolidated_database_v8.0.zip"
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = ROOT / "backend/data/raw/consolidated_database_v8.0.zip"
DEFAULT_OUTPUT = ROOT / "backend/data/historical/iceberg_tracks.csv"


def yyyyddd_to_iso(value: str) -> str:
    text = str(value).strip()
    if len(text) != 7 or not text.isdigit():
        raise ValueError(f"Invalid YYYYDDD date: {value}")
    timestamp = datetime(int(text[:4]), 1, 1, tzinfo=timezone.utc) + timedelta(days=int(text[4:]) - 1)
    return timestamp.isoformat().replace("+00:00", "Z")


def _position(row: dict[str, str]) -> tuple[float, float] | None:
    for prefix in ("nic", "ascat", "oscat", "qscat", "seawinds", "nscat", "ers"):
        for suffix in ("", "_1"):
            lat_key = prefix + suffix
            lon_key = prefix + ("_2" if suffix else "_lon")
            if lat_key in row and lon_key in row:
                try:
                    lat, lon = float(row[lat_key]), float(row[lon_key])
                except (TypeError, ValueError):
                    continue
                if lat != 0.0 and lon != 0.0:
                    return lat, lon
    return None


def process_archive(
    archive_path: Path = DEFAULT_ARCHIVE,
    output_path: Path = DEFAULT_OUTPUT,
    lat_min: float = -80.0,
    lat_max: float = -60.0,
    lon_min: float = 60.0,
    lon_max: float = 90.0,
) -> dict[str, object]:
    observations = []
    with zipfile.ZipFile(archive_path) as archive:
        for name in sorted(item for item in archive.namelist() if item.lower().endswith(".csv")):
            berg_id = Path(name).stem.upper()
            reader = csv.DictReader(io.TextIOWrapper(archive.open(name), encoding="utf-8-sig"))
            for row in reader:
                position = _position(row)
                if position is None:
                    continue
                lat, lon = position
                if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                    try:
                        timestamp = yyyyddd_to_iso(row["date"])
                    except (KeyError, ValueError):
                        continue
                    observations.append({"berg_id": berg_id, "timestamp": timestamp, "lat": lat, "lon": lon})
    observations.sort(key=lambda item: (item["berg_id"], item["timestamp"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=["berg_id", "timestamp", "lat", "lon"])
        writer.writeheader()
        writer.writerows(observations)
    counts = Counter(item["berg_id"] for item in observations)
    intervals = []
    previous = {}
    for item in observations:
        stamp = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
        if item["berg_id"] in previous:
            intervals.append((stamp - previous[item["berg_id"]]).total_seconds() / 3600)
        previous[item["berg_id"]] = stamp
    return {
        "icebergs": len(counts), "observations": len(observations),
        "date_min": observations[0]["timestamp"] if observations else None,
        "date_max": observations[-1]["timestamp"] if observations else None,
        "median_sampling_hours": statistics.median(intervals) if intervals else None,
        "observations_per_berg": dict(sorted(counts.items())),
    }


def fetch_archive(destination: Path = DEFAULT_ARCHIVE) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(SOURCE_URL, destination)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.download:
        fetch_archive()
    print(process_archive())
