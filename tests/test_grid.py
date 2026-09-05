import pytest

from backend.engine.grid import (
    GridConfig,
    cell_to_latlon,
    is_valid_cell,
    latlon_to_cell,
    neighbors8,
)


@pytest.fixture
def config() -> GridConfig:
    return GridConfig(
        lat_min=-69.5,
        lat_max=-66.5,
        lon_min=71.0,
        lon_max=79.0,
        rows=30,
        cols=30,
    )


def test_valid_grid_dimensions(config: GridConfig) -> None:
    assert config.rows == 30
    assert config.cols == 30
    assert config.cell_height_deg == pytest.approx(0.1)
    assert config.cell_width_deg == pytest.approx(8.0 / 30.0)


def test_all_cell_centres_remain_within_bounds(config: GridConfig) -> None:
    for row in range(config.rows):
        for col in range(config.cols):
            lat, lon = cell_to_latlon(row, col, config)
            assert config.lat_min < lat < config.lat_max
            assert config.lon_min < lon < config.lon_max


def test_neighbors_never_leave_grid(config: GridConfig) -> None:
    for row in range(config.rows):
        for col in range(config.cols):
            assert all(
                is_valid_cell(neighbour_row, neighbour_col, config.rows, config.cols)
                for neighbour_row, neighbour_col in neighbors8(
                    row, col, config.rows, config.cols
                )
            )


def test_corner_has_three_neighbors(config: GridConfig) -> None:
    assert len(neighbors8(0, 0, config.rows, config.cols)) == 3


def test_interior_has_eight_neighbors(config: GridConfig) -> None:
    assert len(neighbors8(15, 15, config.rows, config.cols)) == 8


def test_all_cell_centres_round_trip(config: GridConfig) -> None:
    for row in range(config.rows):
        for col in range(config.cols):
            lat, lon = cell_to_latlon(row, col, config)
            assert latlon_to_cell(lat, lon, config) == (row, col)


def test_bounds_and_invalid_cells(config: GridConfig) -> None:
    assert latlon_to_cell(config.lat_max, config.lon_max, config) == (29, 29)
    with pytest.raises(ValueError):
        latlon_to_cell(-70.0, 75.0, config)
    with pytest.raises(IndexError):
        cell_to_latlon(30, 0, config)

