from fastapi.testclient import TestClient

from rxguard.api import app

client = TestClient(app)


def test_health_discloses_synthetic_mode():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "synthetic_only": True,
        "scenarios": 6,
        "explainer": "offline",
    }


def test_scenario_run_returns_evidence_and_fhir():
    response = client.post("/api/scenarios/retroactive-loss/run")
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["actual_margin"] == "-5.85"
    assert body["explanation"]["accepted"] is True
    assert body["fhir_eob"]["resourceType"] == "ExplanationOfBenefit"


def test_unknown_scenario_is_404():
    assert client.post("/api/scenarios/not-real/run").status_code == 404


def test_standards_registry_exposes_authority():
    response = client.get("/api/standards")
    authorities = {item["id"]: item["authority"] for item in response.json()["claims"]}
    assert authorities["carin-bb:pharmacy-eob-2.2.0"] == "spec-referenced"
    assert authorities["rxguard:operational-event-0.1"] == "declared"

