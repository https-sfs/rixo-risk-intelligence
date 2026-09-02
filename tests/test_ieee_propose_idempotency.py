"""IEEE propose idempotency. IEEE-only. Does not approve, simulate, or cross worlds."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from agent.actions.service import default_store as synthetic_store
from agent.actions.service import reset_default_store
from evaluation.custom_data.governance import store_for as custom_store_for
from evaluation.real_data.governance import (
    RealGovernanceError,
    decide_from_investigation,
    default_store,
    propose_action,
    reset_store,
)
from evaluation.recent_data.governance import default_store as january_store
from evaluation.recent_data.governance import reset_store as reset_january
from models.ieee_fraud import PROVENANCE
from models.ieee_fraud.overlay import IN_SAMPLE_OVERLAY


def _decision(anomaly_id: str = "rda-24", signals: list[str] | None = None) -> dict:
    chosen = list(signals) if signals is not None else ["elevated transaction volume"]
    return decide_from_investigation(
        {
            "anomaly_id": anomaly_id,
            "relative_hour_bucket": 24,
            "live_score": 3.1,
            "signals": chosen,
        },
        {
            "anomaly_id": anomaly_id,
            "relative_hour_bucket": 24,
            "live_evidence": {
                "temporal_anomaly": {"value": {"signals": chosen, "live_score": 3.1}},
            },
            "model_prediction": {
                "label": PROVENANCE,
                "high_risk_count": 2,
                "threshold": 0.5,
                "sample_scope": IN_SAMPLE_OVERLAY,
            },
        },
        {"summary": "hour is anomalous", "provider": "deterministic"},
    )


def test_first_keyed_propose_creates_exactly_one_proposal() -> None:
    reset_store()
    proposal = propose_action(_decision(), idempotency_key="ieee-key-1")
    assert proposal["status"] == "proposed"
    assert proposal["human_approval_required"] is True
    assert proposal["simulation_only"] is True
    assert len(default_store().proposals) == 1
    assert default_store().approvals == {}
    assert default_store().executions == {}
    assert default_store().idempotency["ieee-key-1"]["action_id"] == proposal["action_id"]


def test_same_key_and_request_replays_without_a_second_proposal() -> None:
    reset_store()
    first = propose_action(_decision(), idempotency_key="ieee-key-1")
    second = propose_action(_decision(), idempotency_key="ieee-key-1")
    assert second["action_id"] == first["action_id"]
    assert second == first
    assert len(default_store().proposals) == 1
    proposed_events = [item for item in default_store().audit if item["kind"] == "IEEE_ACTION_PROPOSED"]
    assert len(proposed_events) == 1


def test_same_key_different_request_is_conflict_and_creates_nothing() -> None:
    reset_store()
    first = propose_action(_decision("rda-24"), idempotency_key="ieee-key-1")
    with pytest.raises(RealGovernanceError, match="idempotency-key conflict"):
        propose_action(_decision("rda-25"), idempotency_key="ieee-key-1")
    assert list(default_store().proposals) == [first["action_id"]]


def test_different_keys_create_separate_proposals() -> None:
    reset_store()
    first = propose_action(_decision(), idempotency_key="ieee-key-a")
    second = propose_action(_decision(), idempotency_key="ieee-key-b")
    assert first["action_id"] != second["action_id"]
    assert len(default_store().proposals) == 2


def test_missing_key_keeps_existing_create_behavior() -> None:
    reset_store()
    first = propose_action(_decision())
    second = propose_action(_decision())
    assert first["action_id"] != second["action_id"]
    assert len(default_store().proposals) == 2
    assert default_store().idempotency == {}


def test_ieee_key_cannot_resolve_another_world() -> None:
    reset_store()
    reset_january()
    reset_default_store()
    ieee = propose_action(_decision(), idempotency_key="shared-key")
    assert january_store().proposals == {}
    assert not hasattr(january_store(), "idempotency")
    assert synthetic_store().proposals == {}
    assert "shared-key" not in getattr(synthetic_store(), "idempotency", {})
    custom = custom_store_for("cxs-isolation")
    assert custom.proposals == {}
    assert default_store().idempotency["shared-key"]["world"] == "REAL PUBLIC DATA"
    assert ieee["world"] == "REAL PUBLIC DATA"


def test_replay_is_not_approval_or_simulation() -> None:
    reset_store()
    first = propose_action(_decision(), idempotency_key="ieee-key-1")
    replay = propose_action(_decision(), idempotency_key="ieee-key-1")
    assert replay["status"] == "proposed"
    assert replay["action_id"] == first["action_id"]
    assert default_store().approvals == {}
    assert default_store().executions == {}
    kinds = {item["kind"] for item in default_store().audit}
    assert "IEEE_ACTION_PROPOSED" in kinds
    assert "IEEE_ACTION_APPROVED" not in kinds
    assert "IEEE_ACTION_SIMULATED" not in kinds
    assert "IEEE_RAZORPAY_TEST_SIMULATED" not in kinds


def test_classifier_fields_cannot_turn_a_replay_into_an_action() -> None:
    reset_store()
    first = propose_action(_decision(signals=["elevated transaction volume"]), idempotency_key="ieee-key-1")
    louder = _decision(signals=["elevated transaction volume"])
    louder["supporting_classifier_evidence"]["high_risk_count"] = 99
    louder["supporting_classifier_evidence"]["fraud_risk_score"] = 0.99
    replay = propose_action(louder, idempotency_key="ieee-key-1")
    assert replay["action_id"] == first["action_id"]
    assert replay["status"] == "proposed"
    assert replay["action_type"] == first["action_type"]
    assert default_store().approvals == {}
    assert len(default_store().proposals) == 1


def test_concurrent_same_key_creates_one_proposal() -> None:
    reset_store()
    decision = _decision()

    def _propose() -> dict:
        return propose_action(decision, idempotency_key="ieee-race")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in (pool.submit(_propose), pool.submit(_propose))]
    assert results[0]["action_id"] == results[1]["action_id"]
    assert len(default_store().proposals) == 1


def test_http_replay_and_conflict_when_artifacts_present() -> None:
    reset_store()
    from app.main import app

    client = TestClient(app)
    listed = client.get("/api/real/anomalies")
    if listed.status_code != 200 or not listed.json().get("anomalies"):
        pytest.skip("IEEE derived artifacts are not available.")
    first_id = listed.json()["anomalies"][0]["anomaly_id"]
    second_id = next(
        (item["anomaly_id"] for item in listed.json()["anomalies"][1:]),
        None,
    )
    created = client.post(
        "/api/real/actions/propose",
        json={"anomaly_id": first_id, "idempotency_key": "http-ieee-1"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "proposed"
    replay = client.post(
        "/api/real/actions/propose",
        json={"anomaly_id": first_id, "idempotency_key": "http-ieee-1"},
    )
    assert replay.status_code == 200
    assert replay.json()["action_id"] == body["action_id"]
    if second_id:
        conflict = client.post(
            "/api/real/actions/propose",
            json={"anomaly_id": second_id, "idempotency_key": "http-ieee-1"},
        )
        assert conflict.status_code == 409
        assert "idempotency-key conflict" in conflict.json()["detail"]
        assert conflict.json()["world"] == "REAL PUBLIC DATA"
    january = client.post(
        "/api/recent/actions/propose",
        json={"anomaly_id": "rct-20260104-20", "idempotency_key": "http-ieee-1"},
    )
    if january.status_code == 200:
        assert january.json()["action_id"] != body["action_id"]
        assert january.json().get("world") != "REAL PUBLIC DATA" or january.json()["anomaly_id"] != first_id
    blocked = client.post(f"/api/real/actions/{body['action_id']}/simulate")
    assert blocked.status_code == 409
