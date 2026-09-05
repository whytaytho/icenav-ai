"""Independent rectangular grid utilities for the bounded demo corridor.

Rows progress south-to-north and columns west-to-east. Latitude and longitude
cell spacing are calculated independently; no degree-to-kilometre equivalence
is assumed. Production-scale Antarctic work should use a polar projection.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GridConfig:
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    rows: int
    cols: int

    def __post_init__(self) -> None:
        if self.rows <= 0 or self.cols <= 0:
            raise ValueError("rows and cols must be positive")
        if self.lat_min >= self.lat_max:
            raise ValueError("lat_min must be less than lat_max")
        if self.lon_min >= self.lon_max:
            raise ValueError("lon_min must be less than lon_max")

    @property
    def cell_height_deg(self) -> float:
        return (self.lat_max - self.lat_min) / self.rows

    @property
    def cell_width_deg(self) -> float:
        return (self.lon_max - self.lon_min) / self.cols


def is_valid_cell(row: int, col: int, rows: int, cols: int) -> bool:
    """Return whether a row/column pair lies inside the grid."""
    return 0 <= row < rows and 0 <= col < cols


def cell_to_latlon(row: int, col: int, config: GridConfig) -> tuple[float, float]:
    """Return the decimal-degree centre of a grid cell."""
    if not is_valid_cell(row, col, config.rows, config.cols):
        raise IndexError(f"cell ({row}, {col}) is outside the grid")

    lat = config.lat_min + (row + 0.5) * config.cell_height_deg
    lon = config.lon_min + (col + 0.5) * config.cell_width_deg
    return lat, lon


def latlon_to_cell(lat: float, lon: float, config: GridConfig) -> tuple[int, int]:
    """Return the containing cell for a coordinate inside the closed bounds.

    Coordinates exactly on the north or east boundary belong to the final cell.
    """
    if not (config.lat_min <= lat <= config.lat_max):
        raise ValueError("latitude is outside grid bounds")
    if not (config.lon_min <= lon <= config.lon_max):
        raise ValueError("longitude is outside grid bounds")

    row = min(int((lat - config.lat_min) / config.cell_height_deg), config.rows - 1)
    col = min(int((lon - config.lon_min) / config.cell_width_deg), config.cols - 1)
    return row, col


def neighbors8(row: int, col: int, rows: int, cols: int) -> list[tuple[int, int]]:
    """Return valid horizontal, vertical, and diagonal neighbours."""
    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive")
    if not is_valid_cell(row, col, rows, cols):
        raise IndexError(f"cell ({row}, {col}) is outside the grid")

    neighbours: list[tuple[int, int]] = []
    for row_offset in (-1, 0, 1):
        for col_offset in (-1, 0, 1):
            if row_offset == 0 and col_offset == 0:
                continue
            neighbour = (row + row_offset, col + col_offset)
            if is_valid_cell(*neighbour, rows, cols):
                neighbours.append(neighbour)
    return neighbours

