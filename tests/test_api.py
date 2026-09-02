from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent.actions.service import reset_default_store
from app.main import app

SPIKE = "spk-coord-20260118-02"
FESTIVE = "spk-fest-20260114-18"
client = TestClient(app)

REQUIRED_REPORT_KEYS = {
    "spike_id",
    "verdict",
    "confidence",
    "summary",
    "supporting_evidence",
    "contradicting_evidence",
    "key_entities",
    "reasoning",
    "recommended_action",
    "human_approval_required",
    "limitations",
    "provider",
}


@pytest.fixture(autouse=True)
def _fresh_action_store() -> None:
    reset_default_store()


def test_health_check_still_works() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_list_spikes_returns_detected_spikes() -> None:
    response = client.get("/api/spikes")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    ids = {item["spike_id"] for item in payload["spikes"]}
    assert SPIKE in ids
    assert FESTIVE in ids


def test_list_spikes_is_json_serializable() -> None:
    payload = client.get("/api/spikes").json()
    encoded = json.dumps(payload)
    assert SPIKE in encoded


def test_get_valid_spike() -> None:
    response = client.get(f"/api/spikes/{SPIKE}")
    assert response.status_code == 200
    body = response.json()
    assert body["spike_id"] == SPIKE
    assert "volume" in body
    assert "anomaly_reasons" in body


def test_get_invalid_spike_returns_404() -> None:
    response = client.get("/api/spikes/spk-does-not-exist")
    assert response.status_code == 404


def test_deterministic_investigation_works() -> None:
    response = client.get(f"/api/spikes/{SPIKE}/investigation?provider=deterministic")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "deterministic_reasoner"
    assert REQUIRED_REPORT_KEYS <= set(body["report"])
    assert body["report"]["human_approval_required"] is True


def test_unknown_spike_investigation_returns_404() -> None:
    response = client.get("/api/spikes/spk-does-not-exist/investigation")
    assert response.status_code == 404


def test_invalid_provider_is_rejected() -> None:
    response = client.get(f"/api/spikes/{SPIKE}/investigation?provider=made_up")
    assert response.status_code == 422


def test_action_proposal_from_valid_recommendation() -> None:
    report = client.get(f"/api/spikes/{SPIKE}/investigation").json()["report"]
    response = client.post("/api/actions/propose", json=report)
    assert response.status_code == 200
    body = response.json()
    assert body["spike_id"] == SPIKE
    assert body["status"] == "proposed"
    assert body["human_approval_required"] is True


def test_invalid_action_proposal_is_rejected() -> None:
    response = client.post(
        "/api/actions/propose",
        json={
            "spike_id": SPIKE,
            "verdict": "coordinated_abuse",
            "recommended_action": {
                "type": "block_all",
                "scope": "all customers",
                "reason": "unsafe",
            },
            "human_approval_required": True,
        },
    )
    assert response.status_code == 400


def test_action_approval_and_lookup() -> None:
    report = client.get(f"/api/spikes/{SPIKE}/investigation").json()["report"]
    action_id = client.post("/api/actions/propose", json=report).json()["action_id"]
    approval = client.post(
        f"/api/actions/{action_id}/approve",
        json={"approved_by": "analyst", "note": "ok"},
    )
    assert approval.status_code == 200
    assert approval.json()["approved"] is True
    lookup = client.get(f"/api/actions/{action_id}")
    assert lookup.status_code == 200
    assert lookup.json()["approval"]["approved_by"] == "analyst"
    assert lookup.json()["execution"] is None


def test_execution_before_approval_is_rejected() -> None:
    report = client.get(f"/api/spikes/{SPIKE}/investigation").json()["report"]
    action_id = client.post("/api/actions/propose", json=report).json()["action_id"]
    response = client.post(f"/api/actions/{action_id}/execute")
    assert response.status_code == 409
    assert "not been explicitly approved" in response.json()["detail"]


def test_approved_execution_is_simulated() -> None:
    report = client.get(f"/api/spikes/{SPIKE}/investigation").json()["report"]
    action_id = client.post("/api/actions/propose", json=report).json()["action_id"]
    client.post(f"/api/actions/{action_id}/approve", json={"approved_by": "analyst"})
    response = client.post(f"/api/actions/{action_id}/execute")
    assert response.status_code == 200
    body = response.json()
    assert body["simulated"] is True
    assert body["message"].startswith("SIMULATED:")
    assert body["verification"]["production_api_called"] is False
    lookup = client.get(f"/api/actions/{action_id}")
    assert lookup.json()["verification"]["message"] == "Simulation verified."


def test_audit_listing_and_filters() -> None:
    report = client.get(f"/api/spikes/{SPIKE}/investigation").json()["report"]
    action_id = client.post("/api/actions/propose", json=report).json()["action_id"]
    client.post(f"/api/actions/{action_id}/approve", json={"approved_by": "analyst"})
    client.post(f"/api/actions/{action_id}/execute")
    all_events = client.get("/api/audit")
    assert all_events.status_code == 200
    assert all_events.json()["count"] >= 4
    by_action = client.get(f"/api/audit?action_id={action_id}")
    assert by_action.json()["count"] >= 4
    assert {item["action_id"] for item in by_action.json()["events"]} == {action_id}
    by_spike = client.get(f"/api/audit?spike_id={SPIKE}")
    assert by_spike.json()["count"] >= 4
    assert {item["spike_id"] for item in by_spike.json()["events"]} == {SPIKE}


def test_no_endpoint_exposes_full_ledger() -> None:
    for path in ("/transactions", "/all-data", "/ledger", "/api/transactions", "/api/ledger"):
        assert client.get(path).status_code == 404
    spikes = json.dumps(client.get("/api/spikes").json())
    assert "transaction_id" not in spikes


def test_llm_provider_errors_are_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    response = client.get(f"/api/spikes/{SPIKE}/investigation?provider=llm")
    assert response.status_code == 503
    body = response.json()
    assert body["fail_closed"] is True
    assert "report" not in body
    assert body["provider"] == "llm"


def test_unknown_action_lookup_is_404() -> None:
    response = client.get("/api/actions/act-missing")
    assert response.status_code == 404
