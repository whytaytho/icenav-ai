"""Small-area spherical geodesic helpers.

The functions use a spherical Earth with the IUGG mean radius. They are
appropriate for this bounded engineering demo, including Southern Hemisphere
coordinates, but are not a replacement for survey-grade geodesy.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088
KM_PER_NAUTICAL_MILE = 1.852
MPS_TO_KMH = 3.6


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometres between two WGS 84 points."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    haversine = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2.0) ** 2
    )
    central_angle = 2.0 * math.atan2(
        math.sqrt(haversine), math.sqrt(max(0.0, 1.0 - haversine))
    )
    return EARTH_RADIUS_KM * central_angle


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return initial bearing clockwise from true north in ``[0, 360)``."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)

    east_component = math.sin(delta_lon) * math.cos(lat2_rad)
    north_component = (
        math.cos(lat1_rad) * math.sin(lat2_rad)
        - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon)
    )
    return math.degrees(math.atan2(east_component, north_component)) % 360.0


def destination_point(
    lat: float, lon: float, bearing_deg: float, distance_km: float
) -> tuple[float, float]:
    """Return the point reached along a great-circle path.

    Longitude is normalized to ``[-180, 180)``. Distance must be non-negative.
    """
    if distance_km < 0:
        raise ValueError("distance_km must be non-negative")

    angular_distance = distance_km / EARTH_RADIUS_KM
    bearing_rad = math.radians(bearing_deg % 360.0)
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    destination_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(angular_distance)
        + math.cos(lat_rad)
        * math.sin(angular_distance)
        * math.cos(bearing_rad)
    )
    destination_lon_rad = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat_rad),
        math.cos(angular_distance)
        - math.sin(lat_rad) * math.sin(destination_lat_rad),
    )

    destination_lat = math.degrees(destination_lat_rad)
    destination_lon = (math.degrees(destination_lon_rad) + 180.0) % 360.0 - 180.0
    return destination_lat, destination_lon
