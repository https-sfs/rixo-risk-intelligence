"""January 2026 investigation governance: decide → approve → simulate → audit."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from evaluation.recent_data.governance import (
    FORBIDDEN_ACTION_TYPES,
    RecentGovernanceError,
    decide_from_investigation,
    propose_action,
    reset_store,
    simulate_action,
)
from evaluation.recent_data.investigate import (
    LLM_SYSTEM_PROMPT,
    build_llm_context,
    deterministic_analysis,
    investigate_recent_anomaly,
)
from models.ieee_fraud.copy import SCORED_REASONING
from evaluation.real_data.governance import default_store as ieee_store
from evaluation.real_data.governance import reset_store as reset_ieee


def _evidence() -> dict:
    return {
        "anomaly_id": "rct-20260104-20",
        "kind": "Amount concentration",
        "hour_start": "2026-01-04T20:00:00",
        "signals": ["elevated transaction amount"],
        "live_evidence": {
            "transaction_count": {"value": 70},
            "amount_usd": {"value": 157784.18},
        },
        "evaluation_overlay": {"fraud_rate": 0.01, "label": "DELAYED GROUND TRUTH"},
        "source_dataset_model_output": {"used": False},
    }


def test_recent_decision_ignores_source_model_and_labels() -> None:
    reset_store()
    anomaly = {
        "anomaly_id": "rct-20260104-20",
        "hour_start": "2026-01-04T20:00:00",
        "live_score": 8.2,
        "signals": ["elevated transaction amount"],
    }
    decision = decide_from_investigation(
        anomaly,
        _evidence(),
        {"summary": "amount spike", "provider": "deterministic"},
    )
    assert decision["delayed_ground_truth_used"] is False
    assert decision["source_model_used"] is False
    assert decision["ieee_model_used"] is False
    assert decision["human_approval_required"] is True
    assert decision["simulation_only"] is True
    assert decision["recommended_action"]["type"] == "flag_for_human_review"
    dumped = json.dumps(decision["live_inputs"])
    assert "fraud_probability" not in dumped
    assert "fraud_rate" not in dumped
    assert "is_fraud" not in dumped


def test_recent_human_approval_required_before_simulation() -> None:
    reset_store()
    decision = decide_from_investigation(
        {
            "anomaly_id": "rct-20260104-20",
            "hour_start": "2026-01-04T20:00:00",
            "signals": ["elevated transaction volume"],
        },
        _evidence(),
        {"summary": "s", "provider": "deterministic"},
    )
    proposal = propose_action(decision)
    with pytest.raises(RecentGovernanceError, match="not been explicitly approved"):
        simulate_action(proposal["action_id"])


def test_recent_forbidden_live_payment_and_ieee_actions() -> None:
    reset_store()
    decision = decide_from_investigation(
        {"anomaly_id": "rct-20260104-20", "signals": ["elevated transaction amount"]},
        _evidence(),
        {"summary": "s", "provider": "deterministic"},
    )
    decision["recommended_action"]["type"] = "block_payment"
    with pytest.raises(RecentGovernanceError, match="Forbidden"):
        propose_action(decision)
    decision["recommended_action"]["type"] = "flag_high_risk_transactions"
    assert "flag_high_risk_transactions" in FORBIDDEN_ACTION_TYPES
    with pytest.raises(RecentGovernanceError, match="Forbidden"):
        propose_action(decision)


def test_january_reasoning_uses_classifier_state_not_stale_ieee_claim() -> None:
    from models.ieee_fraud.copy import UNSCORED_REASONING, sanitize_reasoning_text

    evidence = _evidence()
    evidence["classifier"] = {
        "status": "scored",
        "fraud_risk_score": 0.6,
        "classification": "High risk",
        "model": "ieee_hgb",
        "model_version": 2,
    }
    report = investigate_recent_anomaly(evidence, provider="deterministic")
    assert SCORED_REASONING not in report["summary"]
    assert report["classifier"]["status"] == "scored"
    assert "classifier was not applied" not in report["summary"].lower()
    assert "IEEE-CIS" not in report["summary"]
    stale = sanitize_reasoning_text(
        "January 2026 window. The IEEE-CIS classifier was not applied.",
        evidence["classifier"],
    )
    assert "classifier was not applied" not in stale.lower()
    assert SCORED_REASONING not in stale
    assert stale == "January 2026 window."
    missing = deterministic_analysis({**evidence, "classifier": {"status": "not_scored"}})
    assert UNSCORED_REASONING not in missing["summary"]
    assert missing["classifier"]["status"] == "not_scored"
    assert "IEEE-CIS" not in missing["summary"]


def test_recent_llm_context_excludes_ieee_and_source_scores() -> None:
    context = build_llm_context(_evidence())
    dumped = json.dumps(context)
    assert "live_evidence" in dumped
    assert "fraud_probability" not in dumped
    assert "model_prediction" not in dumped
    assert "Never say the classifier was not applied" in LLM_SYSTEM_PROMPT
    assert "Do not invent" in LLM_SYSTEM_PROMPT


def test_recent_and_ieee_governance_stores_are_isolated() -> None:
    reset_store()
    reset_ieee()
    decision = decide_from_investigation(
        {"anomaly_id": "rct-20260104-20", "signals": ["elevated transaction amount"]},
        _evidence(),
        {"summary": "s", "provider": "deterministic"},
    )
    propose_action(decision)
    from evaluation.recent_data.governance import default_store

    assert default_store().proposals
    assert ieee_store().proposals == {}


def test_recent_governed_api_flow_when_artifacts_present() -> None:
    reset_store()
    from app.main import app

    client = TestClient(app)
    listed = client.get("/api/recent/anomalies")
    if listed.status_code != 200:
        pytest.skip("January 2026 derived artifacts are not available.")
    anomaly_id = listed.json()["anomalies"][0]["anomaly_id"]
    investigation = client.get(f"/api/recent/anomalies/{anomaly_id}/investigation")
    assert investigation.status_code == 200
    assert investigation.json()["ieee_model_used"] is False
    propose = client.post("/api/recent/actions/propose", json={"anomaly_id": anomaly_id})
    assert propose.status_code == 200
    body = propose.json()
    assert body["simulation_only"] is True
    assert body["ieee_model_used"] is False
    assert body["delayed_ground_truth_used"] is False
    assert body["action_type"] in {
        "review_transactions",
        "review_time_window",
        "monitor_only",
        "flag_for_human_review",
    }
    action_id = body["action_id"]
    blocked = client.post(f"/api/recent/actions/{action_id}/simulate")
    assert blocked.status_code == 409
    approved = client.post(
        f"/api/recent/actions/{action_id}/approve",
        json={"approved_by": "analyst"},
    )
    assert approved.status_code == 200
    simulated = client.post(f"/api/recent/actions/{action_id}/simulate")
    assert simulated.status_code == 200
    assert simulated.json()["simulated"] is True
    assert "Razorpay" in simulated.json()["result"]
    trail = client.get(f"/api/recent/audit?anomaly_id={anomaly_id}")
    kinds = {event["kind"] for event in trail.json()["events"]}
    assert "RECENT_ACTION_PROPOSED" in kinds
    assert "RECENT_ACTION_APPROVED" in kinds
    assert "RECENT_ACTION_SIMULATED" in kinds
    ieee_audit = client.get("/api/real/audit")
    if ieee_audit.status_code == 200:
        ieee_kinds = {event["kind"] for event in ieee_audit.json()["events"]}
        assert "RECENT_ACTION_SIMULATED" not in ieee_kinds


def test_january_anomaly_20_reopen_returns_same_investigation_state() -> None:
    reset_store()
    from app.main import app

    client = TestClient(app)
    anomaly_id = "rct-20260104-20"
    opened = client.get(f"/api/recent/anomalies/{anomaly_id}")
    if opened.status_code != 200:
        pytest.skip("January 2026 derived artifacts are not available.")
    assert opened.json()["anomaly"]["anomaly_id"] == anomaly_id
    assert opened.json()["evidence"]["anomaly_id"] == anomaly_id
    empty = opened.json()["investigation_state"]
    assert empty["status"]["decision"] == "not_recorded"
    assert empty["audit"] == []

    propose = client.post("/api/recent/actions/propose", json={"anomaly_id": anomaly_id})
    assert propose.json()["anomaly_id"] == anomaly_id
    action_id = propose.json()["action_id"]
    client.post(
        f"/api/recent/actions/{action_id}/approve",
        json={"approved_by": "analyst"},
    )
    client.post(f"/api/recent/actions/{action_id}/simulate")

    reopened = client.get(f"/api/recent/anomalies/{anomaly_id}")
    gov = reopened.json()["investigation_state"]
    assert gov["decision"]["anomaly_id"] == anomaly_id
    assert gov["proposal"]["anomaly_id"] == anomaly_id
    assert gov["approval"]["anomaly_id"] == anomaly_id
    assert gov["execution"]["anomaly_id"] == anomaly_id
    assert gov["status"]["decision"] == "recorded"
    assert gov["status"]["approval"] == "approved"
    assert gov["status"]["simulation"] == "completed"
    assert [event["kind"] for event in gov["audit"]] == [
        "RECENT_DECISION_RECORDED",
        "RECENT_ACTION_PROPOSED",
        "RECENT_ACTION_APPROVED",
        "RECENT_ACTION_SIMULATED",
    ]
    assert all(event["anomaly_id"] == anomaly_id for event in gov["audit"])

    again = client.get(f"/api/recent/anomalies/{anomaly_id}")
    assert [event["kind"] for event in again.json()["investigation_state"]["audit"]] == [
        event["kind"] for event in gov["audit"]
    ]

    other = "rct-20260115-14"
    other_resp = client.get(f"/api/recent/anomalies/{other}")
    if other_resp.status_code == 200:
        other_gov = other_resp.json()["investigation_state"]
        assert other_gov["status"]["decision"] == "not_recorded"
        assert other_gov["audit"] == []
        still_a = client.get(f"/api/recent/anomalies/{anomaly_id}")
        assert still_a.json()["investigation_state"]["status"]["simulation"] == "completed"


def test_january_high_risk_count_does_not_select_action() -> None:
    """January recommendations use amount/volume signals only, not classifier counts."""
    reset_store()
    anomaly = {
        "anomaly_id": "rct-20260104-20",
        "hour_start": "2026-01-04T20:00:00",
        "live_score": 8.2,
        "signals": ["elevated transaction amount"],
    }
    evidence = {
        **_evidence(),
        "model_prediction": {"high_risk_count": 91, "p95_score": 0.608},
        "classifier": {"status": "scored", "high_risk_count": 91},
    }
    decision = decide_from_investigation(anomaly, evidence, {"summary": "amount"})
    assert decision["recommended_action"]["type"] == "flag_for_human_review"
    dumped = json.dumps(decision["live_inputs"])
    assert "high_risk" not in dumped
    assert "model_high_risk_count" not in dumped
    volume_only = decide_from_investigation(
        {**anomaly, "signals": ["elevated transaction volume"]},
        evidence,
        {"summary": "volume"},
    )
    assert volume_only["recommended_action"]["type"] == "review_time_window"


def test_january_temporal_window_is_derived() -> None:
    from app.services.recent_world import apply_january_provenance

    payload = apply_january_provenance(
        {
            "live_evidence": {
                "temporal_window": {"value": "2026-01-04T20:00:00", "label": "OBSERVED", "source": "timestamp"},
                "transaction_count": {"value": 70, "label": "OBSERVED"},
            }
        }
    )
    window = payload["live_evidence"]["temporal_window"]
    assert window["label"] == "DERIVED"
    assert window["source"] == "floor(timestamp to hour)"
    assert payload["live_evidence"]["transaction_count"]["label"] == "OBSERVED"
