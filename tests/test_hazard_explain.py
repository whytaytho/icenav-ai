from backend.engine.explain import explain_route_change
from backend.engine.hazard import detect_hazard
from backend.main import APP_CONFIG
from backend.main import app
from fastapi.testclient import TestClient


def _evaluation(safety, blocked=False, weighted=(1, 2, 3, 4)):
    return {"safety_score": safety, "blocked_waypoints": [0] if blocked else [], "waypoints": [{"index": 0, "arrival_hour": 6, "total_risk": 100-safety, "is_navigable": not blocked, "block_reason": "iceberg_exclusion" if blocked else None, "components": {"sea_ice": {"weighted": weighted[0]}, "iceberg": {"weighted": weighted[1], "nearest_iceberg_id": "IB-04"}, "wind": {"weighted": weighted[2]}, "current": {"weighted": weighted[3]}}}]}


def test_unchanged_route_has_no_alert():
    base = _evaluation(80)
    assert not detect_hazard([], base, _evaluation(80), APP_CONFIG)["alert"]


def test_blocked_route_is_critical_and_names_iceberg():
    hazard = detect_hazard([], _evaluation(85), _evaluation(40, True), APP_CONFIG)
    assert hazard["alert"] and hazard["severity"] == "critical"
    assert hazard["first_conflict_waypoint_index"] == 0
    assert hazard["responsible_icebergs"] == ["IB-04"]


def test_explanation_components_sum_and_sort():
    base, forecast = _evaluation(85, weighted=(1, 2, 3, 4)), _evaluation(40, True, weighted=(5, 20, 4, 4.5))
    hazard = detect_hazard([], base, forecast, APP_CONFIG)
    explanation = explain_route_change(base, forecast, hazard)["route_change"]
    impacts = [item["impact"] for item in explanation["contributors"]]
    assert abs(sum(impacts) - explanation["total_risk_delta"]) < 1e-9
    assert [abs(value) for value in impacts] == sorted([abs(value) for value in impacts], reverse=True)
    assert explanation["primary_entity"] == "IB-04"


def test_demo_closing_lead_reroutes_around_ib04():
    client = TestClient(app)
    environment = client.get("/environment/current").json()
    route = client.post("/route", json={"start": environment["vessel"], "destination": environment["destination"], "mode": "balanced"}).json()
    result = client.post("/route/reroute", json={"current_route": [{"lat": point["lat"], "lon": point["lon"], "arrival_hour": point.get("arrival_hour")} for point in route["route_raw"]], "current_position": environment["vessel"], "destination": environment["destination"], "mode": "balanced", "evaluate_at_hour": 6}).json()
    assert result["original_safety"] >= 65
    assert result["forecast_safety"] <= result["original_safety"] - 20
    assert result["responsible_icebergs"] == ["IB-04"]
    assert result["alternate_route"]["forecast_evaluation"]["safety_score"] > result["forecast_safety"]
