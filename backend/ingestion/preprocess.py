"""Convert already-downloaded geospatial sea-ice samples to the shared schema.

The selected environmental product must be confirmed by a human before this
adapter is bound to a concrete NetCDF/HDF/GeoTIFF layout. Coordinate conversion
uses pyproj EPSG:3031 transforms; nearest-neighbour sampling preserves observed
concentration values and never invents open water for missing pixels.
"""

from __future__ import annotations

from typing import Any


def transform_roundtrip(lat: float, lon: float) -> tuple[float, float]:
    from pyproj import Transformer
    forward = Transformer.from_crs("EPSG:4326", "EPSG:3031", always_xy=True)
    inverse = Transformer.from_crs("EPSG:3031", "EPSG:4326", always_xy=True)
    x, y = forward.transform(lon, lat)
    roundtrip_lon, roundtrip_lat = inverse.transform(x, y)
    return roundtrip_lat, roundtrip_lon


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
