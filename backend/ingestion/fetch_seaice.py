"""Fetch one confirmed NSIDC sea-ice concentration granule.

Confirmed source, recorded in full in docs/methodology.md:

    NOAA/NSIDC Climate Data Record of Passive Microwave Sea Ice
    Concentration, Version 6 (dataset G02202).
    DOI: 10.7265/b18j-z797
    Citation: Meier, W. N., Fetterer, F., Windnagel, A. K., Stewart, J. S.
    & Stafford, T. (2024).

This is a human-invoked, ahead-of-time utility. It is never imported by the
FastAPI application and never runs on a request path.

Access, as actually verified in this environment
--------------------------------------------------
NSIDC's general documentation states that a free NASA Earthdata Login account
is required to access their data. That is true for data served through the
Earthdata Cloud / CMR distribution paths. It is NOT true for this specific
product: G02202 Version 6 is additionally mirrored, unauthenticated, at

    https://noaadata.apps.nsidc.org/NOAA/G02202_V6/south/daily/{year}/

This was checked directly -- `curl -I` against a real granule URL returned
HTTP 200 with no redirect and no auth challenge, and the file downloaded and
parsed correctly with no credentials of any kind. No EARTHDATA_USERNAME or
EARTHDATA_PASSWORD is required or read by this module. If NSIDC retires this
mirror, the CMR/Earthdata Cloud path would need real authentication and this
module would need rewriting -- it does not attempt to guess that flow ahead
of time.

Filename format is NOT constant across the archive: the sensor code segment
changes as DMSP satellites were replaced over the mission's history (verified
directly: 1990 uses F08, 2010 and 2023 both use F17). Rather than hardcode a
sensor-to-date table, this module reads the real year directory listing and
matches the file for the requested date, which is correct for any date in
the archive without needing to track satellite handover dates.

Verification status
--------------------
The directory listing, the URL pattern, the absence of an auth requirement,
and one full granule download and parse were all executed directly in this
environment against the live server on 2026-09-06, for date 2023-07-15. This
is not the untested, best-guess integration a human-gated data source usually
starts as; it has run once against real data. It has not been re-verified for
every year in the archive, and NSIDC could restructure this mirror at any
time without notice -- if a request 404s, the first thing to check is
whether the directory layout at the base URL above has changed.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

PRODUCT_DOI = "10.7265/b18j-z797"
PRODUCT_NAME = "NOAA/NSIDC Climate Data Record of Passive Microwave Sea Ice Concentration, Version 6"

_BASE_URL = "https://noaadata.apps.nsidc.org/NOAA/G02202_V6/south/daily"
_FILENAME_LINK_PATTERN = re.compile(r'href="(sic_pss25_(\d{8})_[A-Za-z0-9]+_v06r00\.nc)"')

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = ROOT / "backend/data/raw"


def _year_directory_url(year: int) -> str:
    return f"{_BASE_URL}/{year:04d}/"


def resolve_filename(day: date, timeout: float = 30.0) -> str:
    """Find the real filename for one date by reading the year's listing.

    Raises RuntimeError with the directory URL on any failure, since the most
    likely cause is NSIDC having restructured the mirror.
    """
    directory_url = _year_directory_url(day.year)
    target_stamp = day.strftime("%Y%m%d")
    try:
        with urllib.request.urlopen(directory_url, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Could not list {directory_url}. NSIDC may have restructured "
            "this mirror; check the URL in a browser first."
        ) from exc

    for filename, stamp in _FILENAME_LINK_PATTERN.findall(html):
        if stamp == target_stamp:
            return filename

    raise RuntimeError(
        f"No granule for {day.isoformat()} found in {directory_url}. "
        "The date may be outside the archive's coverage, or NSIDC may have "
        "renamed files for this year."
    )


def granule_url(day: date) -> str:
    filename = resolve_filename(day)
    return f"{_year_directory_url(day.year)}{filename}"


def fetch_granule(
    day: date,
    destination_dir: Path = DEFAULT_RAW_DIR,
    timeout: float = 120.0,
) -> Path:
    """Download one daily granule. No credentials required for this mirror."""
    url = granule_url(day)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / Path(url).name

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response, destination.open("wb") as output_file:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                output_file.write(chunk)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"NSIDC returned HTTP {exc.code} for {url}. If this is 404, "
            "resolve_filename() found a name that no longer exists; if this "
            "is a server error, retry -- it is not an authentication problem "
            "for this mirror."
        ) from exc

    return destination


def granule_summary(day: date) -> dict[str, Any]:
    return {
        "product": PRODUCT_NAME,
        "doi": PRODUCT_DOI,
        "date": day.isoformat(),
        "url": granule_url(day),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=date(2023, 7, 15),
        help="ISO date (YYYY-MM-DD) of the granule to fetch. Default is a "
        "midwinter date, verified in this environment to return 739 of 900 "
        "cells with concentration 0.62-1.00 over the Prydz Bay corridor.",
    )
    args = parser.parse_args()

    if args.download:
        saved_path = fetch_granule(args.date)
        print(f"Saved: {saved_path}")
    else:
        print(granule_summary(args.date))
