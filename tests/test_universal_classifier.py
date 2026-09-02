"""Prove the shared classifier is invoked on all four world execution paths."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from models.ieee_fraud import BUNDLE_VERSION, JOBLIB_NAME, MODEL_DIR
from models.ieee_fraud.adapt import adapt_custom, adapt_recent
from models.ieee_fraud.infer import (
    MODEL_NAME,
    reset_inference_state,
    score_canonical_frame,
)
from models.ieee_fraud.predict import load_model

REPO = Path(__file__).resolve().parent.parent
SPIKE_ID = "spk-coord-20260108-13"


def _require_artifact() -> None:
    if not (MODEL_DIR / JOBLIB_NAME).is_file():
        pytest.skip("Persisted ieee_hgb.joblib is not present.")


def test_shared_infer_uses_the_existing_ieee_hgb_artifact() -> None:
    _require_artifact()
    from models.ieee_fraud.infer import load_shared_artifact

    assert MODEL_NAME == "ieee_hgb"
    assert BUNDLE_VERSION == 2
    shared = load_shared_artifact()
    persisted = load_model(MODEL_DIR / JOBLIB_NAME)
    assert shared.threshold == persisted.threshold
    assert list(shared.estimator.feature_names_in_) == list(persisted.estimator.feature_names_in_)


def test_unavailable_features_are_not_scored_or_fabricated() -> None:
    reset_inference_state()
    adapted = adapt_custom(pd.DataFrame({"merchant": ["m1", "m2"]}), world="BRING YOUR DATA")
    assert adapted.can_score is False
    assert "TransactionAmt" in adapted.missing_required
    scored = score_canonical_frame(
        adapted.frame,
        world="BRING YOUR DATA",
        anomaly_id="cda-missing",
        features_used=adapted.features_used,
        features_unavailable=adapted.missing_required,
    )
    assert scored.get("scored") is False
    assert scored["status"] == "not_scored"
    assert scored["fraud_risk_score"] is None if "fraud_risk_score" in scored else True
    assert "TransactionAmt" in (scored.get("missing_features") or scored.get("features_unavailable") or [])


def test_january_pca_is_not_mapped_onto_ieee_v_columns() -> None:
    adapted = adapt_recent(
        pd.DataFrame(
            {
                "transaction_id": ["t1"],
                "amount_usd": [12.0],
                "event_timestamp": pd.to_datetime(["2026-01-04T20:00:00"]),
                "v1": [9.9],
                "v28": [-1.2],
            }
        )
    )
    assert "V1" not in adapted.frame.columns
    assert "v1" not in adapted.frame.columns
    assert "TransactionAmt" in adapted.features_used
    assert "TransactionDT" in adapted.features_used


def test_january_get_evidence_invokes_shared_infer_and_caches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _require_artifact()
    from app.services import recent_world
    from evaluation.recent_data import classifier as recent_clf
    from models.ieee_fraud import infer

    reset_inference_state()
    recent_clf.reset_recent_classifier_state()
    monkeypatch.setattr(recent_clf, "PERSIST_OVERLAY", False)
    monkeypatch.setattr(recent_clf, "overlay_path", lambda data_dir=None: tmp_path / "classifier_overlay.json")
    mapped = pd.DataFrame(
        {
            "transaction_id": ["t-a", "t-b"],
            "amount_usd": [100.0, 250.0],
            "event_timestamp": pd.to_datetime(["2026-01-15T11:01:00", "2026-01-15T11:15:00"]),
            "hour_start": pd.to_datetime(["2026-01-15T11:00:00", "2026-01-15T11:00:00"]),
        }
    )
    monkeypatch.setattr(recent_clf, "_january_mapped_lite", lambda: mapped)
    store = {
        "rct-test-20": {
            "anomaly_id": "rct-test-20",
            "hour_start": "2026-01-15T11:00:00",
            "kind": "Amount concentration",
            "live_evidence": {"transaction_count": {"value": 2}},
        },
        "rct-test-21": {
            "anomaly_id": "rct-test-21",
            "hour_start": "2026-01-15T12:00:00",
            "kind": "Temporal anomaly",
            "live_evidence": {"transaction_count": {"value": 0}},
        },
    }
    monkeypatch.setattr(recent_world, "load_artifact", lambda name: store if name == "evidence" else {})

    calls: list[str | None] = []
    real = recent_clf.score_canonical_frame

    def _spy(frame, *, world, anomaly_id=None, **kwargs):
        calls.append(anomaly_id)
        return real(frame, world=world, anomaly_id=anomaly_id, **kwargs)

    monkeypatch.setattr(recent_clf, "score_canonical_frame", _spy)

    first = recent_world.get_evidence("rct-test-20")
    assert first["classifier"]["status"] == "scored"
    assert first["classifier"]["anomaly_id"] == "rct-test-20"
    assert first["classifier"]["model"] == "ieee_hgb"
    assert first["classifier"]["model_version"] == 2
    assert first["classifier"]["classification"] in {"High risk", "Low risk"}
    assert calls == ["rct-test-20"]

    second = recent_world.get_evidence("rct-test-20")
    assert second["classifier"]["fraud_risk_score"] == first["classifier"]["fraud_risk_score"]
    assert calls == ["rct-test-20"]

    kinds = [item["kind"] for item in infer.INVOCATION_LOG if item.get("anomaly_id") == "rct-test-20"]
    assert "score_canonical_frame" in kinds
    assert "cache" in kinds


def test_ieee_get_evidence_uses_shared_classifier_path() -> None:
    _require_artifact()
    from app.services.real_world import get_evidence, list_anomalies
    from models.ieee_fraud import infer

    try:
        listed = list_anomalies()
    except Exception:
        pytest.skip("IEEE-CIS derived artifacts are not available.")
    anomalies = listed.get("anomalies") or []
    if len(anomalies) < 2:
        pytest.skip("Need at least two IEEE anomalies.")
    first_id = str(anomalies[0]["anomaly_id"])
    second_id = str(anomalies[1]["anomaly_id"])
    reset_inference_state()
    first = get_evidence(first_id)
    assert first["classifier"]["status"] == "scored"
    assert first["classifier"]["anomaly_id"] == first_id
    assert first["classifier"]["model"] == "ieee_hgb"
    assert first["classifier"]["source"] == "persisted_overlay"
    second = get_evidence(second_id)
    assert second["classifier"]["anomaly_id"] == second_id
    assert first["classifier"]["anomaly_id"] != second["classifier"]["anomaly_id"]
    again = get_evidence(first_id)
    assert again["classifier"]["fraud_risk_score"] == first["classifier"]["fraud_risk_score"]
    worlds = {item["world"] for item in infer.INVOCATION_LOG}
    assert "REAL PUBLIC DATA" in worlds
    kinds = [item["kind"] for item in infer.INVOCATION_LOG if item.get("anomaly_id") == first_id]
    assert "scored" in kinds
    assert "cache" in kinds


def test_bring_your_data_analyze_invokes_shared_infer() -> None:
    _require_artifact()
    from app.services.custom_world import (
        analyze_session,
        confirm_mapping,
        create_session,
        get_anomaly,
        reset_sessions,
    )
    from evaluation.custom_data import score as score_mod
    from models.ieee_fraud import infer

    reset_sessions()
    reset_inference_state()
    rows = ["transaction_id,amount,timestamp,account_id"]
    for hour in range(8):
        count = 40 if hour == 4 else 16
        amount = 300 if hour == 4 else 18
        for index in range(count):
            rows.append(f"txn-{hour}-{index},{amount},2026-03-02 {hour:02d}:10:00,acct-{index % 4}")
    payload = create_session("byd-generic.csv", ("\n".join(rows) + "\n").encode("utf-8"))
    confirm_mapping(
        payload["session_id"],
        {
            "transaction_id": "transaction_id",
            "amount": "amount",
            "timestamp": "timestamp",
            "account_id": "account_id",
        },
    )
    calls: list[str] = []
    real = score_mod.score_canonical_frame

    def _spy(frame, *, world, anomaly_id=None, **kwargs):
        calls.append(world)
        return real(frame, world=world, anomaly_id=anomaly_id, **kwargs)

    score_mod.score_canonical_frame = _spy  # type: ignore[method-assign]
    try:
        analyzed = analyze_session(payload["session_id"])
    finally:
        score_mod.score_canonical_frame = real  # type: ignore[method-assign]
    assert analyzed["compatibility"]["may_score_classifier"] is True
    assert analyzed["summary"]["supervised_scores"] is True
    assert calls, "Bring Your Data analyze must call score_canonical_frame"
    assert all(world == "BRING YOUR DATA" for world in calls)
    anomaly_id = analyzed["anomalies"][0]["anomaly_id"]
    detail = get_anomaly(payload["session_id"], anomaly_id)
    classifier = detail["evidence"]["classifier"]
    assert classifier["status"] == "scored"
    assert classifier["anomaly_id"] == anomaly_id
    assert classifier["model"] == "ieee_hgb"
    score_after_analyze = len(calls)
    reopened = get_anomaly(payload["session_id"], anomaly_id)
    assert reopened["evidence"]["classifier"]["fraud_risk_score"] == classifier["fraud_risk_score"]
    assert len(calls) == score_after_analyze
    if len(analyzed["anomalies"]) > 1:
        other_id = analyzed["anomalies"][1]["anomaly_id"]
        other = get_anomaly(payload["session_id"], other_id)
        assert other["evidence"]["classifier"]["anomaly_id"] == other_id
    kinds = [item["kind"] for item in infer.INVOCATION_LOG]
    assert "score_canonical_frame" in kinds
    reset_sessions()


def test_synthetic_evidence_invokes_shared_infer_and_does_not_rescore() -> None:
    _require_artifact()
    from agent.investigate import investigate_spike
    from models.ieee_fraud import infer
    from tools import evidence as evidence_mod

    reset_inference_state()
    calls: list[str | None] = []
    real = evidence_mod.score_canonical_frame

    def _spy(frame, *, world, anomaly_id=None, **kwargs):
        calls.append(anomaly_id)
        return real(frame, world=world, anomaly_id=anomaly_id, **kwargs)

    evidence_mod.score_canonical_frame = _spy  # type: ignore[method-assign]
    try:
        first = evidence_mod.build_investigation_evidence(SPIKE_ID)
        second = evidence_mod.build_investigation_evidence(SPIKE_ID)
        investigated = investigate_spike(SPIKE_ID)
    finally:
        evidence_mod.score_canonical_frame = real  # type: ignore[method-assign]
    assert first["classifier"]["status"] == "scored"
    assert first["classifier"]["anomaly_id"] == SPIKE_ID
    assert first["classifier"]["model"] == "ieee_hgb"
    assert first["classifier"]["classification"] in {"High risk", "Low risk"}
    assert second["classifier"]["fraud_risk_score"] == first["classifier"]["fraud_risk_score"]
    assert calls == [SPIKE_ID]
    assert investigated["classifier"]["anomaly_id"] == SPIKE_ID
    assert investigated["classifier"]["fraud_risk_score"] == first["classifier"]["fraud_risk_score"]
    kinds = [item["kind"] for item in infer.INVOCATION_LOG if item.get("anomaly_id") == SPIKE_ID]
    assert "score_canonical_frame" in kinds
    assert "cache" in kinds
