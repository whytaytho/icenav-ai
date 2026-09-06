"""Convert already-downloaded geospatial sea-ice samples to the shared schema.

The confirmed source is the NOAA/NSIDC Climate Data Record of Passive
Microwave Sea Ice Concentration, Version 6 (dataset G02202, DOI
10.7265/b18j-z797). Full provenance is recorded in docs/methodology.md.

Two distinct polar stereographic definitions appear in this module and must
not be conflated:

  * EPSG:3031 -- the general-purpose Antarctic Polar Stereographic
    projection. ``transform_roundtrip`` below uses this one; it exists
    independently of any specific data product.
  * EPSG:3412 -- "NSIDC Sea Ice Polar Stereographic South", the specific grid
    definition G02202 is distributed on. ``extract_seaice_concentrations``
    uses this one, because sampling the source file requires its own native
    grid, not a different projection that merely looks similar.

Sampling is nearest-neighbour only: the source is 25 km resolution displayed
on our roughly 11 km grid, so interpolation would manufacture detail the
observation does not contain. A cell with no covering source pixel, or whose
nearest pixel carries a flag value rather than a real concentration, is
reported as ``None`` and the caller marks it as missing -- never as open
water.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Verified directly against a real granule
# (sic_pss25_20230715_F17_v06r00.nc, downloaded from
# noaadata.apps.nsidc.org/NOAA/G02202_V6/): netCDF4 applies the file's own
# scale_factor/add_offset and _FillValue automatically, returning
# cdr_seaice_conc as a numpy MaskedArray already in the range [0.0, 1.0].
# Land, the pole hole, and missing swaths are MASKED entries, not
# out-of-range numbers -- roughly 21% of the grid was masked in that granule.
# (Older raw NASA Team / Bootstrap NSIDC products encode land and the pole
# hole as flag values like 2.53/2.54 in the same field; this CDR product does
# not, and the two must not be confused.) The clamp below exists only as a
# defensive backstop against a value outside [0, 1] slipping through, which
# has not been observed.
_CONCENTRATION_VARIABLE_CANDIDATES = (
    "cdr_seaice_conc",
    "seaice_conc_cdr",
    "nsidc_cdr_seaice_conc",
)


def transform_roundtrip(lat: float, lon: float) -> tuple[float, float]:
    from pyproj import Transformer
    forward = Transformer.from_crs("EPSG:4326", "EPSG:3031", always_xy=True)
    inverse = Transformer.from_crs("EPSG:3031", "EPSG:4326", always_xy=True)
    x, y = forward.transform(lon, lat)
    roundtrip_lon, roundtrip_lat = inverse.transform(x, y)
    return roundtrip_lat, roundtrip_lon


def _find_concentration_variable(dataset: Any):
    """Locate the concentration array by name, searching root then groups.

    NSIDC has reorganised this file's internal layout across versions (the
    V6 user guide notes added groups). Rather than hardcode one path and fail
    silently on a mismatch, this searches known names at the root and one
    level of grouping, and raises with the actual variable names present if
    none match -- so a real file that does not match what is coded here fails
    with something a person can act on, not a bare KeyError.
    """
    containers = [dataset]
    groups = getattr(dataset, "groups", None)
    if groups:
        containers.extend(groups.values())
    for container in containers:
        for name in _CONCENTRATION_VARIABLE_CANDIDATES:
            if name in container.variables:
                return container.variables[name]
    seen = sorted(
        {name for container in containers for name in container.variables}
    )
    raise KeyError(
        "No known sea-ice concentration variable found. Looked for "
        f"{_CONCENTRATION_VARIABLE_CANDIDATES!r}; file contains {seen!r}. "
        "Update _CONCENTRATION_VARIABLE_CANDIDATES in preprocess.py to match "
        "the actual variable name in this file, and record the change in "
        "docs/methodology.md."
    )


def extract_seaice_concentrations(
    netcdf_path: Path,
    grid_config: Any,
    cell_to_latlon: Any,
    rows: int,
    cols: int,
) -> dict[tuple[int, int], float | None]:
    """Sample one G02202 daily granule onto our grid by nearest neighbour.

    ``cell_to_latlon`` is passed in rather than imported, so this function has
    no dependency on the rest of the engine package and can be unit tested
    against a synthetic NetCDF file in isolation.

    Returns a dict keyed by (row, col). A cell absent from the dict, or
    mapped to ``None``, has no usable observation and must be treated as
    missing by the caller -- never defaulted to open water.
    """
    import numpy as np
    from netCDF4 import Dataset
    from pyproj import Transformer

    to_grid = Transformer.from_crs("EPSG:4326", "EPSG:3412", always_xy=True)

    with Dataset(netcdf_path, "r") as dataset:
        concentration_var = _find_concentration_variable(dataset)
        concentration = concentration_var[:]
        # Daily files carry a leading time dimension of length 1.
        if concentration.ndim == 3:
            concentration = concentration[0]

        xgrid = _find_coordinate(dataset, ("xgrid", "x"))
        ygrid = _find_coordinate(dataset, ("ygrid", "y"))

    results: dict[tuple[int, int], float | None] = {}
    for row in range(rows):
        for col in range(cols):
            lat, lon = cell_to_latlon(row, col, grid_config)
            x, y = to_grid.transform(lon, lat)

            col_index = _nearest_index(xgrid, x)
            row_index = _nearest_index(ygrid, y)
            if col_index is None or row_index is None:
                results[(row, col)] = None
                continue

            try:
                cell_value = concentration[row_index, col_index]
            except IndexError:
                results[(row, col)] = None
                continue

            # numpy.ma.is_masked() is used deliberately over `.mask is True`
            # or truthiness checks: a masked scalar's `.mask` attribute is a
            # 0-d ndarray, not a Python bool, so `.mask is True` silently
            # evaluates to False and lets a masked (missing) pixel through as
            # if it were a real observation. Verified against a real granule.
            if cell_value is None or np.ma.is_masked(cell_value):
                results[(row, col)] = None
                continue
            try:
                raw_value = float(cell_value)
            except (ValueError, TypeError):
                results[(row, col)] = None
                continue

            # Defensive only: real granules stay within [0, 1] once netCDF4
            # applies scale_factor and masks the fill value (verified above).
            if raw_value < 0.0 or raw_value > 1.0:
                results[(row, col)] = None
            else:
                results[(row, col)] = raw_value

    return results


def _find_coordinate(dataset: Any, candidate_names: tuple[str, ...]):
    for name in candidate_names:
        if name in dataset.variables:
            return dataset.variables[name][:]
    raise KeyError(
        f"No coordinate variable found among {candidate_names!r}; "
        f"file contains {sorted(dataset.variables)!r}"
    )


def _nearest_index(axis_values, target: float) -> int | None:
    """Return the index of the closest axis value, or None if far outside it.

    A tolerance of 1.5 source pixels (37.5 km on this 25 km grid) distinguishes
    "just outside the grid" from "the source has genuinely no data here",
    which matters because the two should not be reported identically -- both
    end up as ``None`` from the caller's perspective in this version, but the
    distinction is kept available for a future data-quality breakdown.
    """
    import numpy as np

    array = np.asarray(axis_values)
    index = int(np.abs(array - target).argmin())
    pixel_size = abs(float(array[1] - array[0])) if len(array) > 1 else float("inf")
    if abs(float(array[index]) - target) > 1.5 * pixel_size:
        return None
    return index


def apply_observations(base_scenario: dict[str, Any], concentrations: dict[tuple[int, int], float | None], data_source: str, scenario_id: str, missing_is_navigable: bool = False) -> dict[str, Any]:
    from copy import deepcopy
    scenario = deepcopy(base_scenario)
    scenario["meta"].update(scenario_id=scenario_id, data_source=data_source)
    for cell in scenario["cells"]:
        value = concentrations.get((cell["row"], cell["col"]))
        if value is None:
            cell["data_quality"] = "missing"
            cell["is_navigable"] = bool(missing_is_navigable)
        else:
            cell["ice_concentration"] = min(1.0, max(0.0, float(value)))
            cell["data_quality"] = "observed"
    return scenario
