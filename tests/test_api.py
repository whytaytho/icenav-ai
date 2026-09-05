from fastapi.testclient import TestClient

import backend.main as main


client = TestClient(main.app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert payload["version"]

    components = payload["components"]
    assert set(components) == {
        "scenario",
        "forecast_cache",
        "iceberg_model",
        "risk_config",
    }
    # No component may be in error on a correctly installed checkout.
    assert all(component["status"] != "error" for component in components.values())

    # The health report must describe the real loaded scenario, so a stale or
    # wrong scenario is visible before a demonstration rather than during one.
    assert components["scenario"]["scenario_id"] == "prydz-bay-demo-v1"
    assert components["scenario"]["cells"] == 900
    assert components["forecast_cache"]["cached_horizons"] == len(
        components["forecast_cache"]["horizons_hours"]
    )
    # Whatever drift model is requested, health must state which one is
    # actually in force after any fallback.
    assert components["iceberg_model"]["effective_drift_model"] in {
        "persistence",
        "free_drift",
        "ml",
    }


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


def test_risk_endpoint() -> None:
    response = client.get("/environment/risk")
    assert response.status_code == 200
    risk_grid = response.json()
    assert risk_grid["meta"]["risk_model_version"] == "v1"
    assert len(risk_grid["cells"]) == 900
    assert risk_grid["summary"]["navigable_cells"] > 0
    assert risk_grid["summary"]["blocked_cells"] > 0


def test_risk_endpoint_accepts_supported_future_hour() -> None:
    response = client.get("/environment/risk?forecast_hour=6")
    assert response.status_code == 200
    assert response.json()["meta"]["forecast_hour"] == 6


def test_risk_config_endpoint() -> None:
    response = client.get("/config/risk")
    assert response.status_code == 200
    risk_config = response.json()
    assert risk_config["version"] == "v1"
    assert sum(risk_config["weights"].values()) == 1.0


def test_missing_scenario_fails_clearly(monkeypatch, tmp_path) -> None:
    missing_path = tmp_path / "missing-scenario.json"
    monkeypatch.setattr(main, "SCENARIO_PATH", missing_path)

    response = client.get("/environment/current")

    assert response.status_code == 500
    assert response.json()["detail"] == f"Scenario file not found: {missing_path}"
