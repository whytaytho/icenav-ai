from fastapi.testclient import TestClient

import backend.main as main


client = TestClient(main.app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_local_frontend_origin_is_allowed() -> None:
    response = client.get(
        "/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_environment_endpoint() -> None:
    response = client.get("/environment/current")
    assert response.status_code == 200
    scenario = response.json()
    assert scenario["meta"]["scenario_id"] == "prydz-bay-demo-v1"
    assert len(scenario["cells"]) == 900


def test_missing_scenario_fails_clearly(monkeypatch, tmp_path) -> None:
    missing_path = tmp_path / "missing-scenario.json"
    monkeypatch.setattr(main, "SCENARIO_PATH", missing_path)

    response = client.get("/environment/current")

    assert response.status_code == 500
    assert response.json()["detail"] == f"Scenario file not found: {missing_path}"
