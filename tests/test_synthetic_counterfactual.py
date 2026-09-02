from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.actions.service import default_store
from agent.investigate import investigate_spike
from app.main import app
from evaluation.counterfactual import (
    LABEL,
    OUTCOME_LABEL,
    evaluate_synthetic_counterfactual,
    ieee_intervention_limitation,
)
from evaluation.paths import BASELINE_TRANSACTIONS_PATH
from evaluation.scorecard import CLUSTER_2_SPIKE_ID, FESTIVE_SPIKE_ID, IEEE_INTERVENTION_LIMITATION

client = TestClient(app)

COORD_SPIKE = CLUSTER_2_SPIKE_ID


def _file_digest() -> str:
    return hashlib.sha256(BASELINE_TRANSACTIONS_PATH.read_bytes()).hexdigest()


def _selected_coord_action() -> tuple[str, str]:
    report = investigate_spike(COORD_SPIKE)["report"]
    action = report["recommended_action"]
    return str(action["type"]), str(action["scope"])


def test_counterfactual_baseline_targets_and_before_after() -> None:
    action_type, scope = _selected_coord_action()
    first = evaluate_synthetic_counterfactual(
        spike_id=COORD_SPIKE,
        action_type=action_type,
        scope=scope,
        world="SYNTHETIC SCENARIO",
    )
    assert first["label"] == LABEL
    assert first["outcome_label"] == OUTCOME_LABEL
    assert first["not_production_performance"] is True
    assert first["not_money_saved"] is True
    assert first["does_not_choose_action"] is True
    assert first["selected_action"]["received_already_selected"] is True
    assert first["selected_action"]["evaluability"] == "evaluable"
    baseline = first["baseline"]
    targeted = first["targeted"]
    after = first["after"]
    assert baseline["transaction_count"] > 0
    assert baseline["fraud_count"] >= 0
    assert targeted["transaction_count"] >= targeted["fraud_transactions_targeted"]
    assert targeted["fraud_transactions_targeted"] + targeted["legitimate_transactions_targeted"] == targeted[
        "transaction_count"
    ]
    assert after["simulated_residual_fraud_count"] == baseline["fraud_count"] - targeted["fraud_transactions_targeted"]
    assert after["simulated_residual_transaction_count"] == baseline["transaction_count"] - targeted["transaction_count"]
    assert targeted["simulated_fraud_amount_targeted_protected"] == targeted["amount_exposure_targeted"]
    assert first["delta"]["fraud_count"] == after["simulated_residual_fraud_count"] - baseline["fraud_count"]
    assert "money_saved" not in first
    assert first["methodology"]["amount_field"] == "simulated_fraud_amount_targeted_protected"
    assert "money_saved" in first["methodology"]["amount_field_is_not"]


def test_counterfactual_is_deterministic_and_does_not_mutate_source() -> None:
    action_type, scope = _selected_coord_action()
    before = _file_digest()
    first = evaluate_synthetic_counterfactual(
        spike_id=COORD_SPIKE,
        action_type=action_type,
        scope=scope,
    )
    second = evaluate_synthetic_counterfactual(
        spike_id=COORD_SPIKE,
        action_type=action_type,
        scope=scope,
    )
    assert first == second
    assert _file_digest() == before
    assert first["does_not_mutate_source_dataset"] is True
    assert first["source_transaction_count_unchanged"] == first["source_transaction_count_unchanged"]


def test_counterfactual_does_not_call_razorpay_or_mutate_governance(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Razorpay must not be invoked by the counterfactual evaluator")

    monkeypatch.setattr("app.integrations.sandbox_payments.apply_after_approval", _boom)
    monkeypatch.setattr("app.integrations.razorpay_adapter.get_adapter", _boom)
    before_proposals = dict(default_store().proposals)
    action_type, scope = _selected_coord_action()
    evaluate_synthetic_counterfactual(
        spike_id=COORD_SPIKE,
        action_type=action_type,
        scope=scope,
    )
    assert default_store().proposals == before_proposals
    assert default_store().latest_proposal_for_spike(COORD_SPIKE) is None


def test_counterfactual_does_not_select_action_for_festive_monitor() -> None:
    report = investigate_spike(FESTIVE_SPIKE_ID)["report"]
    action = report["recommended_action"]
    result = evaluate_synthetic_counterfactual(
        spike_id=FESTIVE_SPIKE_ID,
        action_type=str(action["type"]),
        scope=str(action["scope"]),
    )
    assert result["selected_action"]["evaluability"] == "not_mechanically_evaluable"
    assert result["after"] is None
    assert result["does_not_choose_action"] is True


def test_ieee_cannot_receive_synthetic_counterfactual_metrics() -> None:
    action_type, scope = _selected_coord_action()
    with pytest.raises(ValueError, match="no post-intervention ledger exists"):
        evaluate_synthetic_counterfactual(
            spike_id=COORD_SPIKE,
            action_type=action_type,
            scope=scope,
            world="REAL PUBLIC DATA",
        )
    with pytest.raises(ValueError, match="no post-intervention ledger exists"):
        evaluate_synthetic_counterfactual(
            spike_id="rda-2227",
            action_type=action_type,
            scope=scope,
            world="SYNTHETIC SCENARIO",
        )
    limitation = ieee_intervention_limitation()
    assert limitation["available"] is False
    assert limitation["synthetic_counterfactual_metrics"] is None
    assert limitation["reason"] == IEEE_INTERVENTION_LIMITATION


def test_counterfactual_api_and_source_isolation() -> None:
    action_type, scope = _selected_coord_action()
    digest = _file_digest()
    response = client.post(
        "/api/evaluation/synthetic/counterfactual",
        json={
            "world": "SYNTHETIC SCENARIO",
            "spike_id": COORD_SPIKE,
            "action_type": action_type,
            "scope": scope,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["label"] == LABEL
    assert body["world"] == "SYNTHETIC SCENARIO"
    rejected = client.post(
        "/api/evaluation/synthetic/counterfactual",
        json={
            "world": "REAL PUBLIC DATA",
            "spike_id": "rda-2227",
            "action_type": action_type,
            "scope": scope,
        },
    )
    assert rejected.status_code == 400
    assert "no post-intervention ledger exists" in rejected.json()["detail"]
    assert hashlib.sha256(Path(BASELINE_TRANSACTIONS_PATH).read_bytes()).hexdigest() == digest
    assert "money_saved" not in body
    assert body["not_money_saved"] is True
