"""Investigation intelligence: provenance, four-world contract, no fabricated claims."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from evaluation.intelligence import (
    CLASSIFIER_EVIDENCE_KIND,
    FEATURE_COVERAGE_LIMIT,
    IEEE_WORLD,
    JANUARY_WORLD,
    STATUS_CONTEXTUAL,
    STATUS_LIMITED,
    STATUS_SUPPORTED,
    STATUS_TRANSFERRED,
    STATUS_UNSUPPORTED,
    SYNTHETIC_WORLD,
    classifier_evidence_status,
    false_positive_impact,
    historical_baseline,
)
from evaluation.intelligence_worlds import for_custom, for_ieee, for_january, for_synthetic

REPO = Path(__file__).resolve().parent.parent
client = TestClient(app)

INTEL_KEYS = {
    "world",
    "case_id",
    "classifier_status",
    "brief",
    "temporal",
    "entities",
    "baseline",
    "case_metrics",
    "false_positive_impact",
    "not_money_saved",
    "classifier_is_not_detector",
    "classifier_is_not_action",
}
BRIEF_KEYS = {
    "why_flagged",
    "what_supports_risk",
    "observed",
    "derived",
    "uncertain",
    "next_checks",
    "not_an_llm_paragraph",
}


def _blob(value: object) -> str:
    return json.dumps(value, default=str).lower()


def _assert_no_fabricated_claims(payload: dict) -> None:
    blob = _blob(payload)
    assert "₹" not in blob
    assert "loss avoided" not in blob
    assert "is fraud confirmed" not in blob
    assert "fraud is confirmed" not in blob
    fp = payload.get("false_positive_impact") or {}
    assert fp.get("monetary_estimate") is None
    assert fp.get("not_money_saved") is True
    assert payload.get("classifier_is_not_detector") is True
    assert payload.get("classifier_is_not_action") is True
    supports = " ".join((payload.get("brief") or {}).get("what_supports_risk") or []).lower()
    flagged = " ".join((payload.get("brief") or {}).get("why_flagged") or []).lower()
    assert "classifier detected" not in flagged
    assert "autonomous" not in supports


def _assert_evidence_quality(block: dict) -> None:
    assert block["kind"] == CLASSIFIER_EVIDENCE_KIND
    assert block["not_a_fraud_verdict"] is True
    assert block["not_a_governance_authorization"] is True
    assert block["not_an_approval"] is True
    assert block["not_an_execution_permit"] is True
    assert block["used_for_action_selection"] is False
    assert block["coverage_not_upgraded_by_scored_rows"] is True
    assert block["not_fraud_confirmed"] is True
    assert block["not_the_anomaly_detector"] is True
    assert block["not_the_action_decision"] is True
    blob = _blob(block)
    assert "is fraud confirmed" not in blob
    assert "fraud is confirmed" not in blob


def test_classifier_status_reflects_existing_architecture() -> None:
    unavailable = classifier_evidence_status({"status": "not_scored"}, world=IEEE_WORLD)
    assert unavailable["status"] == STATUS_UNSUPPORTED
    assert unavailable["not_model_support"] is True
    assert "not model support" in unavailable["detail"].lower()
    limited = classifier_evidence_status(
        {
            "status": "scored",
            "feature_coverage": 0.0139,
            "fraud_risk_score": 0.608,
            "high_risk_count": 91,
            "scored_rows": 91,
        },
        world=SYNTHETIC_WORLD,
    )
    assert limited["status"] == STATUS_LIMITED
    assert limited["feature_coverage"] == 0.0139
    assert limited["high_risk_count"] == 91
    assert limited["scored_rows"] == 91
    assert limited["not_reliable_native_evidence"] is True
    assert limited["applied_outside_native_world"] is True
    assert "does not upgrade" in limited["detail"].lower()
    transferred = classifier_evidence_status(
        {"status": "scored", "feature_coverage": 1.0, "fraud_risk_score": 0.608},
        world=SYNTHETIC_WORLD,
    )
    assert transferred["status"] == STATUS_TRANSFERRED
    assert transferred["applied_outside_native_world"] is True
    assert "outside its native training" in transferred["detail"]
    contextual = classifier_evidence_status(
        {"status": "scored", "feature_coverage": 1.0, "sample_scope": "IN_SAMPLE_MODEL_OVERLAY"},
        world=IEEE_WORLD,
    )
    assert contextual["status"] == STATUS_CONTEXTUAL
    assert contextual["not_held_out_test_performance"] is True
    assert contextual["not_model_accuracy"] is True
    assert "not model accuracy" in contextual["detail"]
    supported = classifier_evidence_status(
        {"status": "scored", "feature_coverage": 0.9},
        world=IEEE_WORLD,
    )
    assert supported["status"] == STATUS_SUPPORTED
    assert supported.get("native_ieee") is True
    assert supported["applied_outside_native_world"] is False
    for block in (unavailable, limited, transferred, contextual, supported):
        _assert_evidence_quality(block)
    assert FEATURE_COVERAGE_LIMIT == 0.05


def test_false_positive_impact_is_operational_not_financial() -> None:
    payload = false_positive_impact(
        transaction_count=91,
        high_risk_count=91,
        recommended_action="monitor",
        labelled_fraud_count=0,
    )
    assert payload["monetary_estimate"] is None
    assert payload["kind"] == "operational_scenario"
    assert payload["provenance"] == "SCENARIO ASSUMPTION"
    blob = _blob(payload)
    assert "₹" not in blob
    assert "loss avoided" not in blob
    assert "unnecessary human review" in blob
    assert "customer friction" in blob


def test_historical_baseline_records_deviation_provenance() -> None:
    block = historical_baseline(
        current={"volume": 80, "label": "now"},
        baseline={"volume": 20, "label": "neighbors"},
        definition="same-world hourly artifact",
    )
    assert block["available"] is True
    assert block["deviation"]["ratio"] == 4.0
    assert block["deviation"]["provenance"] == "DERIVED"


def test_synthetic_list_surfaces_heldout_metrics_with_provenance() -> None:
    body = client.get("/api/spikes").json()
    detection = body["heldout_detection"]
    investigation = body["heldout_investigation"]
    assert detection["provenance"] == "EVALUATION"
    assert detection["source"] == "data/heldout/detection_metrics.json"
    assert "held-out" in detection["evaluation_status"]
    assert detection["not_production_accuracy"] is True
    assert investigation["source"] == "evaluation/investigation_metrics.json"
    assert "held-out" in investigation["evaluation_status"]


def test_synthetic_investigation_intelligence_contract() -> None:
    festive = client.get("/api/spikes/spk-fest-20260114-18/investigation").json()
    intel = festive["investigation_intelligence"]
    assert set(intel) >= INTEL_KEYS
    assert set(intel["brief"]) >= BRIEF_KEYS
    assert intel["world"] == "SYNTHETIC SCENARIO"
    assert intel["classifier_status"]["status"] == STATUS_LIMITED
    assert intel["classifier_status"]["status"] != STATUS_SUPPORTED
    assert intel["classifier_status"]["not_fraud_confirmed"] is True
    _assert_evidence_quality(intel["classifier_status"])
    _assert_no_fabricated_claims(intel)
    assert intel["temporal"]["available"] is True
    assert intel["entities"]["available"] is True
    assert intel["baseline"]["available"] is True
    for metric in intel["case_metrics"]:
        assert "provenance" in metric
        assert "source" in metric


def test_festive_case_18_stays_limited_despite_full_row_scores() -> None:
    body = client.get("/api/spikes/spk-fest-20260114-18/investigation").json()
    status = body["investigation_intelligence"]["classifier_status"]
    report = body["report"]
    assert status["status"] == STATUS_LIMITED
    assert status["headline"] == "MODEL EVIDENCE: LIMITED"
    assert status["feature_coverage"] is not None
    assert 0.01 < float(status["feature_coverage"]) < 0.02
    assert status["high_risk_count"] == 91
    assert status["scored_rows"] == 91
    assert float(status["fraud_risk_score"]) > 0.5
    assert status["kind"] == CLASSIFIER_EVIDENCE_KIND
    assert status["used_for_action_selection"] is False
    assert status["coverage_not_upgraded_by_scored_rows"] is True
    assert "does not upgrade" in status["detail"].lower()
    assert report["recommended_action"]["type"] == "monitor"
    assert report["human_approval_required"] is True
    dumped = _blob(status) + _blob(report["recommended_action"])
    assert "confirmed fraud" not in dumped
    assert "autonomous" not in dumped


def test_scored_row_count_cannot_upgrade_limited_coverage() -> None:
    limited = classifier_evidence_status(
        {
            "status": "scored",
            "feature_coverage": 0.0139,
            "scored_rows": 10_000,
            "high_risk_count": 10_000,
            "fraud_risk_score": 0.99,
            "classification": "High risk",
        },
        world=SYNTHETIC_WORLD,
    )
    assert limited["status"] == STATUS_LIMITED
    transferred = classifier_evidence_status(
        {
            "status": "scored",
            "feature_coverage": 0.2,
            "scored_rows": 1,
            "high_risk_count": 0,
            "fraud_risk_score": 0.1,
        },
        world=SYNTHETIC_WORLD,
    )
    assert transferred["status"] == STATUS_TRANSFERRED


def test_synthetic_intelligence_uses_evidence_not_llm_paragraph() -> None:
    body = client.get("/api/spikes/spk-coord-20260118-02/investigation").json()
    intel = body["investigation_intelligence"]
    assert intel["brief"]["not_an_llm_paragraph"] is True
    assert intel["brief"]["why_flagged"]
    evidence = for_synthetic(
        {
            "spike": {"spike_id": "spk-x", "window_start": "2026-01-18T02:00:00", "anomaly_reasons": []},
            "window": {"transaction_count": 10},
            "classifier": {"status": "not_scored"},
        }
    )
    assert evidence["classifier_status"]["status"] == STATUS_UNSUPPORTED
    assert evidence["temporal"]["available"] is True or evidence["temporal"].get("reason")


def test_january_missing_entities_are_explicit() -> None:
    intel = for_january(
        {"anomaly_id": "rct-x", "hour_start": "2026-01-04T20:00:00", "transactions": 10, "signals": []},
        {
            "live_evidence": {"transaction_count": {"value": 10}},
            "classifier": {"status": "scored", "feature_coverage": 0.004, "classification": "High risk"},
            "evaluation_overlay": {"fraud_count": 1},
        },
    )
    assert intel["entities"]["available"] is False
    assert "account" in intel["entities"]["missing"]
    assert intel["classifier_status"]["status"] == STATUS_LIMITED
    _assert_no_fabricated_claims(intel)


def test_ieee_in_sample_overlay_is_contextual() -> None:
    intel = for_ieee(
        {"anomaly_id": "rda-x", "relative_hour_bucket": 24, "transactions": 3, "signals": ["volume"]},
        {
            "live_evidence": {
                "transaction_count": {"value": 3},
                "product_concentration": {"value": {"value": "W", "share": 0.9, "count": 3}},
            },
            "classifier": {"status": "scored", "feature_coverage": 1.0, "fraud_risk_score": 0.6},
            "model_prediction": {"sample_scope": "IN_SAMPLE_MODEL_OVERLAY", "high_risk_count": 1, "p95_score": 0.6},
            "evaluation_overlay": {"fraud_count": 0},
        },
    )
    assert intel["classifier_status"]["status"] == STATUS_CONTEXTUAL
    assert intel["entities"]["available"] is True
    assert "true account identity" in intel["entities"]["missing"]
    _assert_no_fabricated_claims(intel)


def test_byod_missing_roles_and_hourly_neighbors() -> None:
    intel = for_custom(
        {"anomaly_id": "cda-x", "hour_start": "2026-03-02T04:00:00", "transactions": 80, "signals": []},
        {
            "live_evidence": {"transaction_count": {"value": 80}},
            "classifier": {"status": "not_scored"},
            "evaluation_overlay": {},
        },
        hourly=[
            {"hour_start": "2026-03-02T03:00:00", "transaction_count": 12},
            {"hour_start": "2026-03-02T04:00:00", "transaction_count": 80},
            {"hour_start": "2026-03-02T05:00:00", "transaction_count": 12},
        ],
        mapped_roles=["amount", "timestamp"],
    )
    assert intel["entities"]["available"] is False
    assert "account_id" in intel["entities"]["missing"]
    assert intel["temporal"]["available"] is True
    assert any(row.get("is_selected") for row in intel["temporal"]["neighbors"])
    _assert_no_fabricated_claims(intel)


def test_four_world_payloads_share_the_same_contract() -> None:
    worlds = [
        for_synthetic({"spike": {"spike_id": "s"}, "window": {}, "classifier": {}}),
        for_january({"anomaly_id": "j"}, {"live_evidence": {}, "classifier": {}}),
        for_ieee({"anomaly_id": "i", "relative_hour_bucket": 1}, {"live_evidence": {}, "classifier": {}}),
        for_custom({"anomaly_id": "c"}, {"live_evidence": {}, "classifier": {}}),
    ]
    for payload in worlds:
        assert set(payload) >= INTEL_KEYS
        assert set(payload["brief"]) >= BRIEF_KEYS
        _assert_no_fabricated_claims(payload)


def test_live_world_routes_attach_intelligence_when_artifacts_exist() -> None:
    recent = client.get("/api/recent/anomalies")
    if recent.status_code == 200 and recent.json().get("anomalies"):
        anomaly_id = recent.json()["anomalies"][0]["anomaly_id"]
        detail = client.get(f"/api/recent/anomalies/{anomaly_id}").json()
        assert set(detail["investigation_intelligence"]) >= INTEL_KEYS
        assert detail["investigation_intelligence"]["world"] == "RECENT PUBLIC DATA"
        _assert_no_fabricated_claims(detail["investigation_intelligence"])
        assert detail["investigation_intelligence"]["entities"]["available"] is False

    real = client.get("/api/real/anomalies")
    if real.status_code == 200 and real.json().get("anomalies"):
        anomaly_id = real.json()["anomalies"][0]["anomaly_id"]
        detail = client.get(f"/api/real/anomalies/{anomaly_id}").json()
        intel = detail["investigation_intelligence"]
        assert set(intel) >= INTEL_KEYS
        assert intel["world"] == "REAL PUBLIC DATA"
        _assert_no_fabricated_claims(intel)
        assert intel["classifier_status"]["status"] in {
            STATUS_CONTEXTUAL,
            STATUS_SUPPORTED,
            STATUS_LIMITED,
            STATUS_UNSUPPORTED,
        }


def test_byod_hourly_context_is_retained_without_rescanning_ledgers(tmp_path: Path) -> None:
    from evaluation.custom_data.detect import detect_from_path

    path = tmp_path / "hours.csv"
    rows = ["transaction_id,amount,timestamp"]
    for hour in range(3):
        count = 80 if hour == 1 else 12
        for index in range(count):
            rows.append(f"txn-{hour}-{index},{20 + hour},2026-03-02 {hour:02d}:15:00")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    _anomalies, summary, _labels = detect_from_path(
        path,
        {"transaction_id": "transaction_id", "amount": "amount", "timestamp": "timestamp"},
    )
    context = summary["hourly_context"]
    assert len(context) == 3
    assert {row["transaction_count"] for row in context} == {12, 80}


def test_intelligence_modules_do_not_scan_ledgers() -> None:
    intel = (REPO / "evaluation" / "intelligence.py").read_text(encoding="utf-8")
    worlds = (REPO / "evaluation" / "intelligence_worlds.py").read_text(encoding="utf-8")
    combined = intel + worlds
    assert "train_transaction.csv" not in combined
    assert "transactions.csv" not in combined
    assert "fraud_tests_export" not in combined
    assert "read_csv(path)" in intel
    assert "lru_cache" in intel
