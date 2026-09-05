import pytest

from backend.engine.geo import bearing_deg, destination_point, haversine_km


def test_same_coordinate_has_zero_distance() -> None:
    assert haversine_km(-68.2, 74.1, -68.2, 74.1) == pytest.approx(0.0, abs=1e-9)


def test_one_degree_north_south_is_about_111_km() -> None:
    assert haversine_km(-69.0, 74.0, -68.0, 74.0) == pytest.approx(111.2, abs=0.3)


def test_one_degree_longitude_near_68_s_is_physically_shorter() -> None:
    distance = haversine_km(-68.0, 74.0, -68.0, 75.0)
    assert distance == pytest.approx(41.65, abs=0.3)
    assert distance < 0.5 * haversine_km(-69.0, 74.0, -68.0, 74.0)


def test_haversine_symmetry_sanity_check() -> None:
    outward = haversine_km(-69.1, 71.4, -67.2, 78.2)
    return_trip = haversine_km(-67.2, 78.2, -69.1, 71.4)
    assert outward == pytest.approx(return_trip, rel=1e-12)
    assert 300.0 < outward < 400.0


def test_destination_point_northward() -> None:
    lat, lon = destination_point(-68.0, 74.0, 0.0, 111.2)
    assert lat == pytest.approx(-67.0, abs=0.01)
    assert lon == pytest.approx(74.0, abs=0.01)


def test_destination_point_round_trip_distance() -> None:
    lat, lon = destination_point(-68.0, 74.0, 93.0, 50.0)
    assert haversine_km(-68.0, 74.0, lat, lon) == pytest.approx(50.0, abs=1e-6)
    assert -180.0 <= lon < 180.0


def test_bearing_is_normalized() -> None:
    eastward = bearing_deg(-68.0, 74.0, -68.0, 75.0)
    westward = bearing_deg(-68.0, 74.0, -68.0, 73.0)
    assert 0.0 <= eastward < 360.0
    assert 0.0 <= westward < 360.0
    assert eastward == pytest.approx(90.46, abs=0.2)
    assert westward == pytest.approx(269.54, abs=0.2)

