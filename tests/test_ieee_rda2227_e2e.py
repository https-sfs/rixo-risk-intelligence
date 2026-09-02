"""End-to-end IEEE governance verification for rda-2227. No new product behavior."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent.actions.service import reset_default_store
from app.main import app
from app.persistence import GovernanceDB
from evaluation.custom_data.governance import store_for as byod_store
from evaluation.real_data.governance import (
    RealActionStore,
    bind_store,
    decide_from_investigation,
    reset_store,
)
from evaluation.recent_data.governance import RecentActionStore, reset_store as reset_january
from models.ieee_fraud.overlay import IN_SAMPLE_OVERLAY

CASE = "rda-2227"
AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
client = TestClient(app)


def _require_case() -> dict:
    listed = client.get("/api/real/anomalies")
    if listed.status_code != 200:
        import pytest

        pytest.skip("IEEE derived artifacts are not available.")
    ids = {item["anomaly_id"] for item in listed.json().get("anomalies") or []}
    if CASE not in ids:
        import pytest

        pytest.skip("IEEE case rda-2227 is not in the derived anomaly list.")
    return client.get(f"/api/real/anomalies/{CASE}").json()


def test_rda2227_investigation_surfaces_required_contracts() -> None:
    reset_store()
    detail = _require_case()
    anomaly = detail["anomaly"]
    evidence = detail["evidence"]
    intel = detail["investigation_intelligence"]
    agent = detail["investigation_agent"]
    live = evidence["live_evidence"]
    overlay = evidence["evaluation_overlay"]
    model = evidence["model_prediction"]
    status = intel["classifier_status"]

    assert anomaly["anomaly_id"] == CASE
    assert anomaly["relative_hour_bucket"] == 2227
    assert anomaly["transactions"] == 748
    assert abs(float(anomaly["amount_usd"]) - 124518.75) < 0.02
    assert anomaly["product_top"] == "W"
    assert abs(float(anomaly["product_top_share"]) - 0.9358) < 0.001
    assert overlay["fraud_count"] == 7
    assert overlay["label"] == "DELAYED GROUND TRUTH"
    assert live["transaction_count"]["value"] == 748
    assert intel["world"] == "REAL PUBLIC DATA"
    assert status["status"] == "CONTEXTUAL"
    assert status["sample_scope"] == IN_SAMPLE_OVERLAY
    assert status["used_for_action_selection"] is False
    assert status["not_a_fraud_verdict"] is True
    assert "not held-out" in (status.get("detail") or "").lower()
    assert model.get("sample_scope") == IN_SAMPLE_OVERLAY
    assert model.get("high_risk_count") == 92
    assert abs(float(model.get("p95_score") or status.get("fraud_risk_score") or 0) - 0.68) < 0.02
    assert agent["planner"] == "deterministic_tool_plan"
    assert [step["tool"] for step in agent["trace"]] == [
        "inspect_case_metrics",
        "inspect_temporal_context",
        "inspect_entities",
        "inspect_historical_baseline",
        "inspect_classifier_evidence",
    ]
    assert agent["not_a_governance_decision"] is True
    assert agent["does_not_authorize_action"] is True
    blob = (str(agent.get("finding") or "") + " " + str(agent.get("uncertainty") or "")).lower()
    assert "classifier detected" not in blob
    assert "confirmed fraud" not in blob
    gov = detail["investigation_state"]
    assert gov["proposal"] is None
    assert gov["approval"] is None
    assert gov["execution"] is None


def test_investigator_modules_are_read_only() -> None:
    for name in ("investigator.py", "investigator_tools.py"):
        source = (AGENT_DIR / name).read_text(encoding="utf-8")
        assert "ActionStore" not in source
        assert "decide_from_investigation" not in source
        assert "approve_action" not in source
        assert "simulate_action" not in source
        assert "propose_action" not in source
        assert "apply_after_approval" not in source
        assert "razorpay" not in source.lower()
    reset_store()
    before = dict(RealActionStore().proposals) if False else {}
    _require_case()
    from evaluation.real_data.governance import default_store

    assert default_store().proposals == before
    assert default_store().approvals == {}
    assert default_store().executions == {}


def test_rda2227_full_governance_restart_and_idempotency(tmp_path: Path) -> None:
    reset_store()
    reset_january()
    reset_default_store()
    detail = _require_case()
    db = GovernanceDB(tmp_path / "governance.sqlite")
    bind_store(RealActionStore(db=db))

    blocked_approve = client.post("/api/real/actions/missing/approve", json={"approved_by": "analyst"})
    assert blocked_approve.status_code == 404
    blocked_sim = client.post("/api/real/actions/missing/simulate")
    assert blocked_sim.status_code == 404

    first = client.post(
        "/api/real/actions/propose",
        json={"anomaly_id": CASE, "idempotency_key": "e2e-2227"},
    )
    assert first.status_code == 200
    body = first.json()
    action_id = body["action_id"]
    assert body["status"] == "proposed"
    assert body["anomaly_id"] == CASE
    assert body["human_approval_required"] is True
    assert body["simulation_only"] is True
    assert body["not_a_live_payment_action"] is True
    assert body["action_type"] == "flag_high_risk_transactions"
    assert "was not used to select this action" in body["reason"]
    assert body["delayed_ground_truth_used"] is False

    replay = client.post(
        "/api/real/actions/propose",
        json={"anomaly_id": CASE, "idempotency_key": "e2e-2227"},
    )
    assert replay.status_code == 200
    assert replay.json()["action_id"] == action_id
    conflict = client.post(
        "/api/real/actions/propose",
        json={"anomaly_id": "rda-2226", "idempotency_key": "e2e-2227"},
    )
    assert conflict.status_code == 409

    gated = client.post(f"/api/real/actions/{action_id}/simulate")
    assert gated.status_code == 409

    approved = client.post(
        f"/api/real/actions/{action_id}/approve",
        json={"approved_by": "analyst"},
    )
    assert approved.status_code == 200
    assert approved.json()["approved"] is True
    assert "razorpay" not in str(approved.json()).lower()

    simulated = client.post(f"/api/real/actions/{action_id}/simulate")
    assert simulated.status_code == 200
    result = simulated.json()
    assert result["simulated"] is True
    assert result["not_a_live_payment_action"] is True
    dumped = str(result).lower()
    sandbox = result.get("razorpay_test") or {}
    assert result.get("not_a_live_payment_action") is True
    assert "no live payment" in dumped
    assert sandbox.get("environment") == "test"
    assert sandbox.get("not_a_live_payment") is True

    trail = client.get(f"/api/real/audit?anomaly_id={CASE}").json()["events"]
    kinds = [event["kind"] for event in trail]
    assert kinds.index("IEEE_DECISION_RECORDED") < kinds.index("IEEE_ACTION_PROPOSED")
    assert kinds.index("IEEE_ACTION_PROPOSED") < kinds.index("IEEE_ACTION_APPROVED")
    assert kinds.index("IEEE_ACTION_APPROVED") < kinds.index("IEEE_ACTION_SIMULATED")
    assert kinds.count("IEEE_ACTION_PROPOSED") == 1

    from evaluation.real_data.governance import default_store

    assert len(default_store().proposals) == 1
    january = RecentActionStore()
    assert action_id not in january.proposals
    assert byod_store("cxs-e2e").proposals == {}

    with patch_no_razorpay() as sandbox:
        bind_store(RealActionStore(db=GovernanceDB(db.path)))
        sandbox.assert_not_called()
    restored = client.get(f"/api/real/actions/{action_id}").json()
    assert restored["proposal"]["action_id"] == action_id
    assert restored["proposal"]["status"] == "simulated"
    assert restored["approval"]["approved"] is True
    assert restored["execution"]["simulated"] is True
    again = client.post(
        "/api/real/actions/propose",
        json={"anomaly_id": CASE, "idempotency_key": "e2e-2227"},
    )
    assert again.status_code == 200
    assert again.json()["action_id"] == action_id
    restored_audit = client.get(f"/api/real/audit?anomaly_id={CASE}").json()["events"]
    assert [event["kind"] for event in restored_audit].count("IEEE_ACTION_PROPOSED") == 1

    high = decide_from_investigation(
        detail["anomaly"],
        {**detail["evidence"], "model_prediction": {**model_block(detail), "high_risk_count": 9_999}},
        {"summary": "s", "provider": "deterministic"},
    )
    zero = decide_from_investigation(
        detail["anomaly"],
        {**detail["evidence"], "model_prediction": {**model_block(detail), "high_risk_count": 0}},
        {"summary": "s", "provider": "deterministic"},
    )
    assert high["recommended_action"]["type"] == zero["recommended_action"]["type"] == "flag_high_risk_transactions"
    assert high["supporting_classifier_evidence"]["used_for_action_selection"] is False


def model_block(detail: dict) -> dict:
    return dict(detail["evidence"].get("model_prediction") or {})


def patch_no_razorpay():
    from unittest.mock import patch

    return patch("app.integrations.sandbox_payments.apply_after_approval")
