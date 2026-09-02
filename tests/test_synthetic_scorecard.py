from __future__ import annotations

import json

from fastapi.testclient import TestClient

from agent.actions.service import default_store
from app.main import app
from data.scenarios import ATTACKS, FESTIVE_END, FESTIVE_START
from evaluation.detection import load_labelled_windows
from evaluation.labels import LABEL_BACKGROUND, LABEL_COORDINATED, LABEL_FESTIVE, label_hour
from evaluation.metrics import binary_counts, binary_scores, json_number
from evaluation.paths import BASELINE_WINDOWS_PATH
from evaluation.scorecard import (
    CLUSTER_1_SPIKE_ID,
    CLUSTER_2_SPIKE_ID,
    DETERMINISTIC_AGENT_TRADEOFF,
    FESTIVE_SPIKE_ID,
    IEEE_INTERVENTION_LIMITATION,
    build_synthetic_scorecard,
    synthetic_scorecard,
)

client = TestClient(app)

FORBIDDEN_KEYS = frozenset(
    {
        "ai_accuracy",
        "money_saved",
        "production_performance",
        "production_accuracy",
        "roi",
    }
)


def _keys(payload: object) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.add(str(key))
            found.update(_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            found.update(_keys(item))
    return found


def _independent_any_scores() -> dict[str, object]:
    labelled = load_labelled_windows(BASELINE_WINDOWS_PATH)
    truths = ["scenario" if truth != LABEL_BACKGROUND else "background" for truth in labelled["truth"]]
    preds = ["scenario" if pred != LABEL_BACKGROUND else "background" for pred in labelled["prediction"]]
    counts = binary_counts(truths, preds, "scenario")
    return {**counts, **binary_scores(counts)}


def test_scorecard_uses_seed_42_demo_world() -> None:
    body = synthetic_scorecard()["evaluation"]
    assert body["scope"] == "synthetic_spike_level_detection"
    assert body["world"] == "SYNTHETIC SCENARIO"
    assert body["dataset"]["seed"] == 42
    assert body["dataset"]["n_transactions"] == 10226
    assert body["dataset"]["in_sample_demo"] is True
    assert body["dataset"]["not_heldout_seed_2027"] is True
    assert body["methodology"]["in_sample_note"]
    assert body["heldout_reference"]["seed"] == 2027
    assert body["heldout_reference"]["not_the_same_dataset"] is True


def test_scorecard_precision_recall_f1_match_independent_calculation() -> None:
    expected = _independent_any_scores()
    detection = synthetic_scorecard()["evaluation"]["detection"]
    any_vs = detection["any_injected_scenario_vs_any_spike"]
    assert any_vs["precision"]["value"] == json_number(expected["precision"])
    assert any_vs["recall"]["value"] == json_number(expected["recall"])
    assert any_vs["f1"]["value"] == json_number(expected["f1"])
    assert any_vs["true_positive_windows"]["value"] == expected["tp"]
    assert any_vs["false_positive_windows"]["value"] == expected["fp"]
    assert any_vs["false_negative_windows"]["value"] == expected["fn"]
    for metric in ("precision", "recall", "f1"):
        assert any_vs[metric]["methodology"]
        assert any_vs[metric]["source"]
        assert any_vs[metric]["provenance"] == "EVALUATION"


def test_scorecard_known_synthetic_windows_and_clusters() -> None:
    labelled = load_labelled_windows(BASELINE_WINDOWS_PATH)
    starts = labelled["window_start"].map(str)
    festive_hours = labelled.loc[labelled["truth"] == LABEL_FESTIVE]
    festive_as_coord = int(
        ((labelled["truth"] == LABEL_FESTIVE) & (labelled["prediction"] == LABEL_COORDINATED)).sum()
    )
    assert label_hour(FESTIVE_START.isoformat(timespec="seconds")) == LABEL_FESTIVE
    assert (festive_hours["prediction"] == LABEL_FESTIVE).any()

    cluster_1 = labelled.loc[
        (starts >= ATTACKS[0].start.isoformat(sep=" ")) & (starts < ATTACKS[0].end.isoformat(sep=" "))
    ]
    if cluster_1.empty:
        cluster_1 = labelled.loc[
            (starts >= ATTACKS[0].start.isoformat()) & (starts < ATTACKS[0].end.isoformat())
        ]
    cluster_2 = labelled.loc[
        (starts >= ATTACKS[1].start.isoformat(sep=" ")) & (starts < ATTACKS[1].end.isoformat(sep=" "))
    ]
    if cluster_2.empty:
        cluster_2 = labelled.loc[
            (starts >= ATTACKS[1].start.isoformat()) & (starts < ATTACKS[1].end.isoformat())
        ]
    assert (cluster_1["prediction"] == LABEL_COORDINATED).any()
    assert (cluster_2["prediction"] == LABEL_COORDINATED).any()

    scenario = synthetic_scorecard()["evaluation"]["scenario_separation"]
    assert scenario["legitimate_festive_spike_detected"]["value"] is True
    assert scenario["coordinated_abuse_cluster_1_detected"]["value"] is True
    assert scenario["coordinated_abuse_cluster_2_detected"]["value"] is True
    assert scenario["festive_representative_spike_id"] == FESTIVE_SPIKE_ID
    assert scenario["clusters"][0]["representative_spike_id"] == CLUSTER_1_SPIKE_ID
    assert scenario["clusters"][1]["representative_spike_id"] == CLUSTER_2_SPIKE_ID
    assert scenario["festive_hours_predicted_as_coordinated_abuse"]["value"] == festive_as_coord
    assert scenario["legitimate_festive_treated_as_coordinated_abuse"]["value"] is (festive_as_coord > 0)
    assert FESTIVE_END > FESTIVE_START


def test_scorecard_investigation_is_calendar_agreement_not_ai_accuracy() -> None:
    investigation = synthetic_scorecard()["evaluation"]["investigation"]
    assert investigation["not_an_ai_accuracy_metric"] is True
    assert "ai_accuracy" not in _keys(investigation)
    cases = {case["spike_id"]: case for case in investigation["cases"]}
    assert cases[FESTIVE_SPIKE_ID]["calendar_expected"] == "likely_festive"
    assert cases[CLUSTER_1_SPIKE_ID]["calendar_expected"] == "coordinated_abuse"
    assert cases[CLUSTER_2_SPIKE_ID]["calendar_expected"] == "coordinated_abuse"
    assert cases[FESTIVE_SPIKE_ID]["agrees_with_known_scenario"] is True
    assert cases[CLUSTER_1_SPIKE_ID]["agrees_with_known_scenario"] is True
    assert cases[CLUSTER_2_SPIKE_ID]["agrees_with_known_scenario"] is True
    for case in investigation["cases"]:
        completeness = case["evidence_completeness"]
        assert isinstance(completeness["supporting_evidence_count"], int)
        assert completeness["supporting_evidence_count"] >= 0
        assert isinstance(completeness["contradicting_evidence_count"], int)
        assert completeness["contradicting_evidence_count"] >= 0
        assert completeness["supporting_present"] is (completeness["supporting_evidence_count"] > 0)


def test_scorecard_governance_process_checks_and_no_store_mutation() -> None:
    before = default_store().latest_proposal_for_spike("spk-governance-check")
    governance = synthetic_scorecard()["evaluation"]["governance"]
    assert governance["not_ml_accuracy"] is True
    for key in (
        "decision_requires_investigation_evidence",
        "approval_required",
        "simulation_blocked_before_approval",
        "simulation_is_test_only",
        "audit_events_are_ordered",
        "investigator_cannot_authorize_action",
        "classifier_evidence_cannot_independently_select_action",
    ):
        assert governance[key]["value"] is True
        assert governance[key]["methodology"]
    assert governance["live_action_store_unchanged"] is True
    assert governance["razorpay_not_invoked"] is True
    assert default_store().latest_proposal_for_spike("spk-governance-check") is before


def test_scorecard_keeps_classifier_metrics_separate() -> None:
    classifier = synthetic_scorecard()["evaluation"]["classifier"]
    assert classifier["included_in_spike_detection"] is False
    assert classifier["not_recomputed_as_synthetic_spike_metrics"] is True
    assert classifier["ieee_historical_reference"]["world"] == "REAL PUBLIC DATA"
    assert classifier["ieee_historical_reference"]["not_production_accuracy"] is True
    detection = json.dumps(synthetic_scorecard()["evaluation"]["detection"])
    assert "pr_auc" not in detection
    assert "0.461861" not in detection


def test_scorecard_has_no_fabricated_or_cross_world_claims() -> None:
    payload = synthetic_scorecard()
    dumped = json.dumps(payload)
    assert not FORBIDDEN_KEYS.intersection(_keys(payload))
    assert IEEE_INTERVENTION_LIMITATION in dumped
    assert DETERMINISTIC_AGENT_TRADEOFF in dumped
    assert "SYNTHETIC SCENARIO" in dumped


def test_scorecard_api_and_cached_builder_match() -> None:
    response = client.get("/api/evaluation/synthetic")
    assert response.status_code == 200
    body = response.json()
    assert body == synthetic_scorecard()
    assert body["evaluation"]["world"] == "SYNTHETIC SCENARIO"
    build_synthetic_scorecard.cache_info()


def test_ieee_intervention_outcome_api_is_limitation_only() -> None:
    response = client.get("/api/evaluation/ieee/intervention-outcome")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["genuine_before_after"] is False
    assert body["synthetic_counterfactual_metrics"] is None
    assert body["reason"] == IEEE_INTERVENTION_LIMITATION
    assert "money_saved" not in _keys(body)
