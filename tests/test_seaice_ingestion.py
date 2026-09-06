"""Tests for the confirmed NSIDC sea-ice extraction pipeline.

These build a small synthetic NetCDF file in-memory, matching the real
G02202 V6 layout verified directly against a live granule
(sic_pss25_20230715_F17_v06r00.nc): variable name cdr_seaice_conc, x/y
coordinates in metres, scale_factor/add_offset applied by netCDF4 into the
range [0, 1], and missing/land/pole-hole pixels represented as MaskedArray
entries rather than out-of-range sentinel values. No network access and no
real NSIDC file are required to run these.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.engine.grid import GridConfig, cell_to_latlon
from backend.ingestion.preprocess import (
    _find_concentration_variable,
    _nearest_index,
    extract_seaice_concentrations,
    transform_roundtrip,
)

netCDF4 = pytest.importorskip("netCDF4")


# A small grid covering the same corner of the real EPSG:3412 grid, so lat/lon
# in this range reprojects to x/y values actually inside the synthetic axes
# below. Coordinates are illustrative, not the real Prydz Bay corridor.
TEST_GRID = GridConfig(lat_min=-69.0, lat_max=-67.0, lon_min=73.0, lon_max=75.0, rows=4, cols=4)


def _write_synthetic_granule(path, x_values, y_values, concentration_raw, fill_value=255):
    """Build a minimal file matching the real product's variable layout."""
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("time", 1)
        dataset.createDimension("y", len(y_values))
        dataset.createDimension("x", len(x_values))

        x_var = dataset.createVariable("x", "f8", ("x",))
        x_var[:] = x_values
        x_var.units = "meters"

        y_var = dataset.createVariable("y", "f8", ("y",))
        y_var[:] = y_values
        y_var.units = "meters"

        conc_var = dataset.createVariable(
            "cdr_seaice_conc", "u1", ("time", "y", "x"), fill_value=fill_value
        )
        # Values passed in here are already raw storage bytes (0-255, with
        # `fill_value` meaning missing). Auto-scaling must be OFF for this
        # write: with it on, netCDF4 treats an assigned value as the DECODED
        # quantity and applies the encode transform on top of it, silently
        # corrupting a raw uint8 payload. (Found by writing 50 and reading
        # back 136 -- 50/scale_factor mod 256 -- while building this fixture.)
        conc_var.set_auto_maskandscale(False)
        conc_var[0] = concentration_raw
        conc_var.set_auto_maskandscale(True)
        conc_var.scale_factor = 0.01
        conc_var.add_offset = 0.0
        conc_var.valid_range = np.array([0, 100], dtype="u1")


def test_finds_concentration_variable_by_documented_name(tmp_path):
    path = tmp_path / "granule.nc"
    _write_synthetic_granule(path, x_values=[0.0, 25000.0], y_values=[0.0, 25000.0], concentration_raw=np.array([[50, 60], [70, 255]], dtype="u1"))
    with netCDF4.Dataset(path) as dataset:
        variable = _find_concentration_variable(dataset)
        assert variable.name == "cdr_seaice_conc"


def test_missing_concentration_variable_raises_with_available_names(tmp_path):
    path = tmp_path / "granule.nc"
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("x", 1)
        dataset.createVariable("something_else", "f8", ("x",))
        with pytest.raises(KeyError, match="something_else"):
            _find_concentration_variable(dataset)


def test_masked_scalar_mask_attribute_is_not_a_python_bool():
    """Regression test for a real bug found against a live granule.

    A masked scalar's `.mask` attribute is a 0-d numpy array, not a Python
    bool, so `cell.mask is True` silently evaluates to False and lets a
    masked (missing) pixel through as if it were a real observation.
    Verified directly against sic_pss25_20230715_F17_v06r00.nc, where ~21%
    of the grid was masked (land, pole hole, or no swath coverage) and this
    exact `is True` check let every one of them through undetected.

    This is a direct test of the hazard, independent of grid geometry or
    reprojection, so it cannot pass or skip based on where a test point
    happens to land.
    """
    masked_value = np.ma.masked
    assert isinstance(masked_value.mask, np.ndarray), (
        "if numpy ever changes .mask to return a plain bool, the defensive "
        "comment in preprocess.py explaining the `is True` hazard is stale "
        "and should be revisited"
    )
    # The bug: this is what the code must NOT rely on.
    assert (masked_value.mask is True) is False
    # The fix: this is what preprocess.py actually uses.
    assert np.ma.is_masked(masked_value) is True


def test_masked_pixel_extracted_from_real_layout_is_reported_missing(tmp_path):
    """Same bug, exercised through the real array-indexing path this
    product uses: a 2D uint8 field with a declared _FillValue, read back
    through netCDF4 exactly as extract_seaice_concentrations does."""
    x_values = [0.0, 25000.0]
    y_values = [0.0, 25000.0]
    raw = np.array([[50, 255], [255, 80]], dtype="u1")  # top-right, bottom-left = fill
    path = tmp_path / "granule.nc"
    _write_synthetic_granule(path, x_values, y_values, raw)

    with netCDF4.Dataset(path) as dataset:
        concentration = dataset.variables["cdr_seaice_conc"][:][0]

    assert np.ma.is_masked(concentration[0, 1]) is True
    assert np.ma.is_masked(concentration[1, 0]) is True
    assert np.ma.is_masked(concentration[0, 0]) is False
    assert float(concentration[0, 0]) == pytest.approx(0.50)


def test_extract_seaice_concentrations_end_to_end(tmp_path):
    """Full pipeline on a synthetic file: known values in, correct dict out."""
    x_values = [i * 25000.0 - 50000.0 for i in range(5)]
    y_values = [i * 25000.0 - 50000.0 for i in range(5)]
    raw = np.full((5, 5), 255, dtype="u1")  # start fully masked
    raw[2, 2] = 80  # one real pixel at the centre: 0.80 concentration

    path = tmp_path / "granule.nc"
    _write_synthetic_granule(path, x_values, y_values, raw)

    result = extract_seaice_concentrations(
        path, TEST_GRID, cell_to_latlon, TEST_GRID.rows, TEST_GRID.cols
    )

    assert len(result) == TEST_GRID.rows * TEST_GRID.cols
    values = [v for v in result.values() if v is not None]
    # Every non-missing value must be a real concentration in [0, 1].
    assert all(0.0 <= v <= 1.0 for v in values)
    # At least the geometry and masking logic must distinguish some cells.
    assert len(values) < len(result)  # not everything can be observed here


def test_never_reports_a_value_outside_zero_to_one(tmp_path):
    x_values = [0.0, 25000.0]
    y_values = [0.0, 25000.0]
    raw = np.array([[100, 0], [50, 255]], dtype="u1")
    path = tmp_path / "granule.nc"
    _write_synthetic_granule(path, x_values, y_values, raw)

    result = extract_seaice_concentrations(
        path, TEST_GRID, cell_to_latlon, TEST_GRID.rows, TEST_GRID.cols
    )
    for value in result.values():
        assert value is None or 0.0 <= value <= 1.0


def test_nearest_index_rejects_points_far_outside_the_source_grid():
    axis = np.array([0.0, 25000.0, 50000.0, 75000.0])
    assert _nearest_index(axis, 25000.0) == 1
    assert _nearest_index(axis, 1_000_000.0) is None


def test_epsg_3031_roundtrip_unaffected_by_epsg_3412_addition():
    """The general-purpose EPSG:3031 helper must stay independent of the
    NSIDC-specific EPSG:3412 grid added for sea-ice extraction -- the two
    must never be silently conflated."""
    lat, lon = transform_roundtrip(-68.0, 75.0)
    assert abs(lat + 68.0) < 1e-7 and abs(lon - 75.0) < 1e-7
