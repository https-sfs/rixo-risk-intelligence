"""IEEE investigation governance: decide → approve → simulate → audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evaluation.real_data.governance import (
    FORBIDDEN_ACTION_TYPES,
    RealGovernanceError,
    decide_from_investigation,
    propose_action,
    reset_store,
    simulate_action,
)
from evaluation.real_data.investigate import LLM_SYSTEM_PROMPT, build_llm_context
from models.ieee_fraud.overlay import (
    IN_SAMPLE_OVERLAY,
    OUT_OF_SAMPLE_OVERLAY,
    aggregate_hour_scores,
    overlay_sample_scope,
)
from models.ieee_fraud.predict import IncompletePredictPayloadError, raw_frame_from_payload
import pandas as pd

from models.ieee_fraud import PROVENANCE


def _evidence(high_risk: int = 2, signals: list[str] | None = None) -> dict:
    return {
        "anomaly_id": "rda-24",
        "relative_hour_bucket": 24,
        "live_evidence": {
            "transaction_count": {"value": 10},
            "amount_usd": {"value": 100.0},
            "temporal_anomaly": {
                "value": {
                    "signals": list(signals)
                    if signals is not None
                    else ["elevated transaction volume"],
                    "live_score": 3.1,
                }
            },
        },
        "evaluation_overlay": {"fraud_rate": 0.4, "label": "DELAYED GROUND TRUTH"},
        "model_prediction": {
            "label": PROVENANCE,
            "high_risk_count": high_risk,
            "threshold": 0.5,
            "sample_scope": IN_SAMPLE_OVERLAY,
            "top_transactions": [
                {
                    "transaction_id": "1",
                    "fraud_risk_score": 0.9,
                    "provenance": PROVENANCE,
                    "delayed_ground_truth": 1,
                }
            ],
        },
    }


def test_decision_uses_anomaly_and_model_not_ground_truth() -> None:
    reset_store()
    anomaly = {
        "anomaly_id": "rda-24",
        "relative_hour_bucket": 24,
        "live_score": 3.1,
        "signals": ["elevated transaction volume"],
    }
    report = {"summary": "hour is anomalous", "provider": "deterministic"}
    decision = decide_from_investigation(anomaly, _evidence(), report)
    assert decision["delayed_ground_truth_used"] is False
    assert decision["human_approval_required"] is True
    assert decision["simulation_only"] is True
    assert "model_high_risk_count" not in decision["live_inputs"]
    assert "evaluation_overlay" not in decision["live_inputs"]
    assert "fraud_rate" not in json.dumps(decision["live_inputs"])
    assert decision["recommended_action"]["type"] == "review_hour"
    assert decision["supporting_classifier_evidence"]["provenance"] == PROVENANCE
    assert decision["supporting_classifier_evidence"]["used_for_action_selection"] is False
    assert "classifier" not in decision["recommended_action"]["reason"].lower() or "supporting" in decision["recommended_action"]["reason"]


def test_human_approval_required_before_simulation() -> None:
    reset_store()
    decision = decide_from_investigation(
        {"anomaly_id": "rda-24", "relative_hour_bucket": 24, "live_score": 3.1, "signals": ["x"]},
        _evidence(),
        {"summary": "s", "provider": "deterministic"},
    )
    proposal = propose_action(decision)
    with pytest.raises(RealGovernanceError, match="not been explicitly approved"):
        simulate_action(proposal["action_id"])


def test_forbidden_live_payment_actions_rejected() -> None:
    reset_store()
    decision = decide_from_investigation(
        {"anomaly_id": "rda-24", "relative_hour_bucket": 24, "signals": ["x"]},
        _evidence(),
        {"summary": "s", "provider": "deterministic"},
    )
    decision["recommended_action"]["type"] = "block_payment"
    assert "block_payment" in FORBIDDEN_ACTION_TYPES
    with pytest.raises(RealGovernanceError, match="Forbidden"):
        propose_action(decision)


def test_llm_context_supplies_model_prediction_and_forbids_score_generation() -> None:
    context = build_llm_context(_evidence())
    assert context["model_prediction_evidence"]["provenance"] == PROVENANCE
    assert context["model_prediction_evidence"]["high_risk_count"] == 2
    assert context["live_evidence"] is not None
    dumped = json.dumps(context)
    assert "delayed_ground_truth" not in dumped
    assert "Do not calculate" in LLM_SYSTEM_PROMPT
    assert "sole source of fraud_risk_score" in LLM_SYSTEM_PROMPT


def test_overlay_sample_scope_uses_train_cutoff() -> None:
    assert overlay_sample_scope(2227, 10_437_996.0) == IN_SAMPLE_OVERLAY
    assert overlay_sample_scope(4000, 10_437_996.0) == OUT_OF_SAMPLE_OVERLAY
    scored = pd.DataFrame(
        {
            "transaction_id": [1, 2],
            "relative_hour_bucket": [10, 4000],
            "fraud_risk_score": [0.9, 0.2],
            "amount_usd": [4.0, 5.0],
        }
    )
    overlay = aggregate_hour_scores(scored, threshold=0.5, train_cutoff_elapsed=10_437_996.0)
    assert overlay["hours"]["10"]["sample_scope"] == IN_SAMPLE_OVERLAY
    assert overlay["hours"]["10"]["not_a_test_metric"] is True
    assert overlay["hours"]["4000"]["sample_scope"] == OUT_OF_SAMPLE_OVERLAY


def test_incomplete_predict_payload_is_rejected() -> None:
    with pytest.raises(IncompletePredictPayloadError, match="enough identifiable"):
        raw_frame_from_payload({"TransactionAmt": 50.0})
    raw = raw_frame_from_payload({"TransactionAmt": 50.0, "ProductCD": "W", "TransactionDT": 1000})
    assert "TransactionAmt" in raw.columns


def test_evaluation_metrics_artifact_unchanged() -> None:
    path = Path(__file__).resolve().parent.parent / "data" / "real" / "model" / "model_evaluation.json"
    evaluation = json.loads(path.read_text(encoding="utf-8"))
    assert evaluation["split"]["train_fraction"] == 0.7
    assert evaluation["test"]["untouched"] is True
    assert evaluation["test"]["threshold_source"] == "validation_frozen"
    assert evaluation["ranking"]["pr_auc"] == 0.461861
    assert evaluation["ranking"]["roc_auc"] == 0.88697
    assert evaluation["operating_point"]["f1"] == 0.283946
    assert evaluation["operating_point"]["threshold"] == 0.5


def test_ieee_action_api_and_2026_excluded() -> None:
    reset_store()
    from app.main import app

    client = TestClient(app)
    recent = client.get("/api/recent/status")
    assert recent.status_code == 200
    assert "model" not in recent.json().get("artifacts", {})
    missing = client.post("/api/real/actions/propose", json={})
    assert missing.status_code == 400
    spikes = client.get("/api/spikes")
    assert spikes.status_code == 200
    assert spikes.json()["count"] >= 1


def test_ieee_governed_flow_when_real_artifacts_present() -> None:
    reset_store()
    from app.main import app

    client = TestClient(app)
    listed = client.get("/api/real/anomalies")
    if listed.status_code != 200:
        pytest.skip("IEEE derived artifacts are not available.")
    anomaly_id = listed.json()["anomalies"][0]["anomaly_id"]
    evidence = client.get(f"/api/real/anomalies/{anomaly_id}")
    assert evidence.status_code == 200
    model = evidence.json()["evidence"].get("model_prediction") or {}
    if model:
        assert model.get("sample_scope") in {IN_SAMPLE_OVERLAY, OUT_OF_SAMPLE_OVERLAY}
        assert model.get("label") == PROVENANCE
    propose = client.post("/api/real/actions/propose", json={"anomaly_id": anomaly_id})
    assert propose.status_code == 200
    body = propose.json()
    assert body["simulation_only"] is True
    assert body["delayed_ground_truth_used"] is False
    assert body["action_type"] not in FORBIDDEN_ACTION_TYPES
    action_id = body["action_id"]
    blocked = client.post(f"/api/real/actions/{action_id}/simulate")
    assert blocked.status_code == 409
    approved = client.post(
        f"/api/real/actions/{action_id}/approve",
        json={"approved_by": "analyst"},
    )
    assert approved.status_code == 200
    simulated = client.post(f"/api/real/actions/{action_id}/simulate")
    assert simulated.status_code == 200
    assert simulated.json()["simulated"] is True
    assert "Razorpay" in simulated.json()["result"]
    trail = client.get(f"/api/real/audit?anomaly_id={anomaly_id}")
    kinds = {event["kind"] for event in trail.json()["events"]}
    assert "IEEE_ACTION_PROPOSED" in kinds
    assert "IEEE_ACTION_APPROVED" in kinds
    assert "IEEE_ACTION_SIMULATED" in kinds


def test_ieee_high_risk_count_does_not_select_action() -> None:
    """Classifier overlay cannot independently change the IEEE recommended action."""
    reset_store()
    volume = {
        "anomaly_id": "rda-24",
        "relative_hour_bucket": 24,
        "live_score": 3.1,
        "signals": ["elevated transaction volume"],
    }
    high = decide_from_investigation(volume, _evidence(high_risk=2), {"summary": "s"})
    zero = decide_from_investigation(volume, _evidence(high_risk=0), {"summary": "s"})
    assert high["recommended_action"]["type"] == zero["recommended_action"]["type"] == "review_hour"
    assert "model_high_risk_count" not in high["live_inputs"]
    assert high["supporting_classifier_evidence"]["high_risk_count"] == 2
    assert high["supporting_classifier_evidence"]["used_for_action_selection"] is False
    assert "was not used to select this action" in high["recommended_action"]["reason"]
    amount = {
        "anomaly_id": "rda-24",
        "relative_hour_bucket": 24,
        "live_score": 4.2,
        "signals": ["elevated transaction amount"],
    }
    amount_high = decide_from_investigation(
        amount, _evidence(high_risk=9, signals=["elevated transaction amount"]), {"summary": "s"}
    )
    amount_zero = decide_from_investigation(
        amount, _evidence(high_risk=0, signals=["elevated transaction amount"]), {"summary": "s"}
    )
    assert (
        amount_high["recommended_action"]["type"]
        == amount_zero["recommended_action"]["type"]
        == "flag_high_risk_transactions"
    )
    quiet_high = decide_from_investigation(
        {"anomaly_id": "rda-24", "relative_hour_bucket": 24, "signals": []},
        _evidence(high_risk=7, signals=[]),
        {"summary": "s"},
    )
    quiet_zero = decide_from_investigation(
        {"anomaly_id": "rda-24", "relative_hour_bucket": 24, "signals": []},
        _evidence(high_risk=0, signals=[]),
        {"summary": "s"},
    )
    assert (
        quiet_high["recommended_action"]["type"]
        == quiet_zero["recommended_action"]["type"]
        == "take_no_simulated_action"
    )


def test_ieee_product_concentration_and_hour_score_are_derived() -> None:
    from app.services.real_world import apply_ieee_provenance
    from evaluation.real_data.evidence import DERIVED

    payload = apply_ieee_provenance(
        {
            "live_evidence": {
                "product_concentration": {"value": {"value": "W", "share": 0.9}, "label": "OBSERVED FROM IEEE-CIS"},
                "temporal_anomaly": {"value": {"live_score": 2.1}, "label": "OBSERVED FROM IEEE-CIS"},
                "transaction_count": {"value": 3, "label": "OBSERVED FROM IEEE-CIS"},
            }
        }
    )
    live = payload["live_evidence"]
    assert live["product_concentration"]["label"] == DERIVED
    assert live["temporal_anomaly"]["label"] == DERIVED
    assert live["transaction_count"]["label"] == "OBSERVED FROM IEEE-CIS"


def test_ieee_in_sample_overlay_is_not_a_test_metric() -> None:
    from models.ieee_fraud.overlay import IN_SAMPLE_OVERLAY, overlay_sample_scope

    assert overlay_sample_scope(2227, 10_437_996.0) == IN_SAMPLE_OVERLAY
    scored = _evidence()["model_prediction"]
    assert scored["sample_scope"] == IN_SAMPLE_OVERLAY
    assert "not_a_test_metric" not in scored or scored.get("not_a_test_metric") in {True, None}
