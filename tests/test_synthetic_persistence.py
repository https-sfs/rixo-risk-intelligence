from __future__ import annotations

from fastapi.testclient import TestClient

from agent.actions.service import reset_default_store
from app.main import app

SPIKE_A = "spk-coord-20260118-02"
SPIKE_B = "spk-fest-20260114-18"
client = TestClient(app)


def setup_function() -> None:
    reset_default_store()


def _complete(spike_id: str) -> str:
    report = client.get(f"/api/spikes/{spike_id}/investigation").json()["report"]
    action_id = client.post("/api/actions/propose", json=report).json()["action_id"]
    client.post(f"/api/actions/{action_id}/approve", json={"approved_by": "analyst"})
    simulated = client.post(f"/api/actions/{action_id}/execute")
    assert simulated.status_code == 200
    return action_id


def test_empty_synthetic_investigation_state() -> None:
    body = client.get(f"/api/spikes/{SPIKE_A}/investigation").json()
    gov = body["investigation_state"]
    assert gov["decision"] is None
    assert gov["proposal"] is None
    assert gov["approval"] is None
    assert gov["execution"] is None
    assert gov["audit"] == []
    assert gov["status"]["decision"] == "not_recorded"
    assert gov["status"]["simulation"] == "not_simulated"


def test_synthetic_reopen_restores_completed_state_without_duplicates() -> None:
    action_id = _complete(SPIKE_A)
    first = client.get(f"/api/spikes/{SPIKE_A}/investigation").json()["investigation_state"]
    assert first["proposal"]["action_id"] == action_id
    assert first["proposal"]["spike_id"] == SPIKE_A
    assert first["approval"]["approved"] is True
    assert first["execution"]["simulated"] is True
    kinds = [event["event_type"] for event in first["audit"]]
    assert kinds == [
        "DECISION_RECORDED",
        "ACTION_PROPOSED",
        "ACTION_APPROVED",
        "ACTION_SIMULATED",
        "ACTION_VERIFIED",
    ]
    assert first["decision"]["representation"] == "proposal_read_model"
    assert first["decision_representation"] == "proposal_read_model"
    assert all(event["spike_id"] == SPIKE_A for event in first["audit"])

    report = client.get(f"/api/spikes/{SPIKE_A}/investigation").json()["report"]
    again = client.post("/api/actions/propose", json=report).json()
    assert again["action_id"] == action_id
    reopened = client.get(f"/api/spikes/{SPIKE_A}/investigation").json()["investigation_state"]
    assert reopened["proposal"]["action_id"] == action_id
    assert [event["event_type"] for event in reopened["audit"]] == kinds
    assert len(reopened["audit"]) == 5


def test_synthetic_spike_b_stays_independent() -> None:
    _complete(SPIKE_A)
    other = client.get(f"/api/spikes/{SPIKE_B}/investigation").json()["investigation_state"]
    assert other["proposal"] is None
    assert other["approval"] is None
    assert other["execution"] is None
    assert other["audit"] == []
    assert other["status"]["decision"] == "not_recorded"

    still_a = client.get(f"/api/spikes/{SPIKE_A}/investigation").json()["investigation_state"]
    assert still_a["status"]["simulation"] == "completed"
    assert still_a["proposal"]["spike_id"] == SPIKE_A


def test_synthetic_url_refresh_returns_same_state() -> None:
    action_id = _complete(SPIKE_A)
    first = client.get(f"/api/spikes/{SPIKE_A}/investigation").json()["investigation_state"]
    second = client.get(f"/api/spikes/{SPIKE_A}/investigation").json()["investigation_state"]
    assert first["proposal"]["action_id"] == action_id
    assert [event["event_type"] for event in second["audit"]] == [
        event["event_type"] for event in first["audit"]
    ]
    assert second["execution"]["simulated"] is True
