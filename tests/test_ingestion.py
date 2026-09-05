import json
import socket

from fastapi.testclient import TestClient
from backend.data.generate_scenario import build_scenario
from backend.engine.schema import validate_scenario
from backend.engine.scenarios import ScenarioRegistry
from backend.ingestion.preprocess import apply_observations, transform_roundtrip
from backend.main import app


def test_projection_roundtrip():
    lat, lon = transform_roundtrip(-68.0, 75.0)
    assert abs(lat + 68.0) < 1e-7 and abs(lon - 75.0) < 1e-7


def test_missing_data_is_flagged_not_zeroed():
    scenario = apply_observations(build_scenario(), {}, "confirmed_source", "real-test")
    assert all(cell["data_quality"] == "missing" and not cell["is_navigable"] for cell in scenario["cells"])
    validate_scenario(scenario)
    assert len(scenario["cells"]) == scenario["meta"]["grid"]["rows"] * scenario["meta"]["grid"]["cols"]
    assert all(0 <= cell["ice_concentration"] <= 1 for cell in scenario["cells"])


def test_registry_falls_back_to_synthetic(tmp_path):
    base = build_scenario()
    (tmp_path / "demo_scenario.json").write_text(json.dumps(base), encoding="utf-8")
    registry = ScenarioRegistry(tmp_path)
    assert registry.load("absent")["meta"]["scenario_id"] == "prydz-bay-demo-v1"


def test_request_time_paths_do_not_open_network_connections(monkeypatch):
    def reject_network(*args, **kwargs):
        raise AssertionError("runtime endpoint attempted an external network connection")

    # Patch create_connection rather than socket.connect: the latter also
    # catches the asyncio event loop self-pipe, which is local plumbing
    # rather than an outbound call.
    monkeypatch.setattr(socket, "create_connection", reject_network)
    client = TestClient(app)
    environment = client.get("/environment/current").json()
    start = {"lat": environment["vessel"]["lat"], "lon": environment["vessel"]["lon"]}
    destination = {
        "lat": environment["destination"]["lat"],
        "lon": environment["destination"]["lon"],
    }
    route = client.post(
        "/route", json={"start": start, "destination": destination, "mode": "balanced"}
    ).json()

    # Every endpoint the live demonstration touches, not a sample of them.
    # This test is the guarantee that a failed venue network cannot break the
    # presentation, so a new endpoint must be added here when it is added to
    # the application.
    responses = [
        client.get("/health"),
        client.get("/scenarios"),
        client.get("/environment/current"),
        client.get("/environment/risk"),
        client.get("/environment/risk?forecast_hour=6"),
        client.get("/config/risk"),
        client.get("/forecast/horizons"),
        client.get("/forecast?hour=6"),
        client.get("/icebergs/trajectory?id=IB-04"),
        client.get("/validation/options"),
        client.post(
            "/route",
            json={"start": start, "destination": destination, "mode": "balanced"},
        ),
        client.post(
            "/routes/compare", json={"start": start, "destination": destination}
        ),
        client.post(
            "/route/reroute",
            json={
                "current_route": [
                    {"lat": point["lat"], "lon": point["lon"]}
                    for point in route["route_raw"]
                ],
                "current_position": start,
                "destination": destination,
                "mode": "balanced",
                "evaluate_at_hour": 6,
            },
        ),
    ]
    assert all(response.status_code == 200 for response in responses)
