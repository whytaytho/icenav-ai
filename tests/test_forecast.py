import copy
import math

from fastapi.testclient import TestClient

from backend.api.forecast import build_forecast_scenario
from backend.data.generate_scenario import build_scenario
from backend.engine.geo import haversine_km
from backend.engine.iceberg import from_components, propagate_iceberg, to_components
from backend.engine.seaice import advect_seaice
from backend.main import APP_CONFIG, app

client = TestClient(app)


def test_compass_components_and_roundtrip():
    assert to_components(10, 0) == (0.0, 10.0)
    east, north = to_components(10, 90)
    assert math.isclose(east, 10, abs_tol=1e-9) and math.isclose(north, 0, abs_tol=1e-9)
    assert math.isclose(to_components(10, 180)[1], -10, abs_tol=1e-9)
    for direction in (-10, 0, 90, 180, 370):
        speed, recovered = from_components(*to_components(3.4, direction))
        assert math.isclose(speed, 3.4) and math.isclose(recovered, direction % 360, abs_tol=1e-9)


def test_iceberg_propagation_is_pure_and_deterministic():
    scenario = build_scenario()
    original = copy.deepcopy(scenario["icebergs"][3])
    first = propagate_iceberg(original, scenario, 6, APP_CONFIG)
    second = propagate_iceberg(original, scenario, 6, APP_CONFIG)
    assert original == scenario["icebergs"][3]
    assert first == second
    assert haversine_km(original["lat"], original["lon"], first["lat"], first["lon"]) > 0


def test_advection_bounds_land_and_disable_switch():
    scenario = build_scenario()
    forecast = advect_seaice(scenario, 24, APP_CONFIG)
    assert all(0 <= cell["ice_concentration"] <= 1 for cell in forecast)
    for before, after in zip(scenario["cells"], forecast):
        if before["is_land"]:
            assert before == after
    disabled = copy.deepcopy(APP_CONFIG)
    disabled["forecast"]["advection_enabled"] = False
    assert advect_seaice(scenario, 24, disabled) == scenario["cells"]


def test_forecast_shape_cache_and_api_validation():
    scenario = build_forecast_scenario(build_scenario(), 6, APP_CONFIG)
    assert scenario["meta"]["forecast_hour"] == 6
    assert len(scenario["cells"]) == 900
    assert client.get("/forecast?hour=6").json() == client.get("/forecast?hour=6").json()
    invalid = client.get("/forecast?hour=5")
    assert invalid.status_code == 400 and "[0, 3, 6, 12, 24]" in invalid.json()["detail"]


def test_route_reports_time_expanded_snapshots():
    scenario = build_scenario()
    result = client.post("/route", json={"start": scenario["vessel"], "destination": scenario["destination"], "mode": "balanced", "departure_hour": 0}).json()
    assert result["success"]
    assert result["timing"]["arrival_hour"] >= result["metrics"]["eta_hours"] - 0.2
    assert len(result["timing"]["snapshots_used"]) > 1
