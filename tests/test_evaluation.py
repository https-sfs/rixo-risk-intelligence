from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from agent.errors import LLMOutputError, LLMProviderError
from agent.investigate import investigate_spike
from agent.providers.deterministic import DeterministicReasoner

from data.generate_dataset import generate_transactions
from data.schema import TRANSACTION_COLUMNS
from evaluation.detection import evaluate_heldout_detection
from evaluation.intervention import (
    classify_recommendation,
    evaluate_heldout_intervention,
    match_scope_mask,
    parse_bounded_scope,
)
from evaluation.exposure import (
    assign_transaction_ground_truth,
    evaluate_heldout_exposure,
    half_open_mask,
    json_amount,
    label_transaction_hours,
    load_exposure_spikes,
    load_exposure_transactions,
    overlapping_window_pairs,
    union_window_mask,
)
from evaluation.heldout import generate_heldout_artifacts
from evaluation.heldout_evidence import (
    build_heldout_evidence,
    load_heldout_hourly_windows,
    load_heldout_spikes,
    load_heldout_transactions,
    spike_record_from_row,
)
from evaluation.investigation import (
    evaluate_heldout_investigations,
    expected_investigation_verdict,
)
from evaluation.llm import (
    build_heldout_llm_prompt,
    classify_llm_failure,
    evaluate_heldout_llm,
    percentile,
    score_valid_verdict,
)
from evaluation.labels import (
    LABEL_BACKGROUND,
    LABEL_COORDINATED,
    LABEL_FESTIVE,
    label_hour,
    label_windows,
    map_detector_prediction,
)
from evaluation.metrics import binary_counts, binary_scores, confusion_matrix, f1_score, json_number, safe_divide
from evaluation.paths import (
    BASELINE_SPIKES_CSV_PATH,
    BASELINE_SPIKES_JSON_PATH,
    BASELINE_TRANSACTIONS_PATH,
    BASELINE_WINDOWS_PATH,
    EVALUATION_SEED,
    HELDOUT_EXPOSURE_PATH,
    HELDOUT_INTERVENTION_PATH,
    HELDOUT_LLM_PATH,
    HELDOUT_META_PATH,
    HELDOUT_SPIKES_CSV_PATH,
    HELDOUT_SPIKES_JSON_PATH,
    HELDOUT_TRANSACTIONS_PATH,
    HELDOUT_WINDOWS_PATH,
)

REQUIRED_HELDOUT = (
    HELDOUT_TRANSACTIONS_PATH,
    HELDOUT_META_PATH,
    HELDOUT_SPIKES_CSV_PATH,
    HELDOUT_SPIKES_JSON_PATH,
    HELDOUT_WINDOWS_PATH,
)

BASELINE_ARTIFACTS = (
    BASELINE_TRANSACTIONS_PATH,
    BASELINE_SPIKES_CSV_PATH,
    BASELINE_SPIKES_JSON_PATH,
    BASELINE_WINDOWS_PATH,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_heldout_generation_is_reproducible_for_evaluation_seed() -> None:
    first = generate_transactions(seed=EVALUATION_SEED)
    second = generate_transactions(seed=EVALUATION_SEED)
    pd.testing.assert_frame_equal(first, second)


def test_heldout_artifacts_exist() -> None:
    for path in REQUIRED_HELDOUT:
        assert path.is_file(), path


def test_heldout_transactions_are_not_identical_to_seed_42() -> None:
    heldout = pd.read_csv(HELDOUT_TRANSACTIONS_PATH)
    baseline = pd.read_csv(BASELINE_TRANSACTIONS_PATH)
    assert not heldout.equals(baseline)
    assert json.loads(HELDOUT_META_PATH.read_text(encoding="utf-8"))["seed"] == EVALUATION_SEED


def test_heldout_schema_matches_locked_contract() -> None:
    heldout = pd.read_csv(HELDOUT_TRANSACTIONS_PATH)
    assert list(heldout.columns) == list(TRANSACTION_COLUMNS)
    baseline = pd.read_csv(BASELINE_TRANSACTIONS_PATH)
    assert list(baseline.columns) == list(TRANSACTION_COLUMNS)


def test_baseline_transactions_remain_seed_42() -> None:
    meta = json.loads((BASELINE_TRANSACTIONS_PATH.parent / "dataset_meta.json").read_text(encoding="utf-8"))
    assert meta["seed"] == 42
    assert BASELINE_TRANSACTIONS_PATH.is_file()


def test_heldout_generation_does_not_overwrite_baseline(tmp_path: Path) -> None:
    before = {path: _sha256(path) for path in BASELINE_ARTIFACTS}
    generate_heldout_artifacts(output_dir=tmp_path, seed=EVALUATION_SEED)
    after = {path: _sha256(path) for path in BASELINE_ARTIFACTS}
    assert before == after
    assert (tmp_path / "transactions.csv").is_file()
    assert (tmp_path / "detected_spikes.csv").is_file()
    assert tmp_path.resolve() != BASELINE_TRANSACTIONS_PATH.parent.resolve()


def test_ground_truth_labels_are_deterministic() -> None:
    starts = [
        "2026-01-08T13:00:00",
        "2026-01-14T18:00:00",
        "2026-01-06T09:00:00",
    ]
    assert label_windows(starts) == label_windows(starts)
    assert label_hour("2026-01-08T13:00:00") == LABEL_COORDINATED
    assert label_hour("2026-01-14T18:00:00") == LABEL_FESTIVE
    assert label_hour("2026-01-06T09:00:00") == LABEL_BACKGROUND


def test_ground_truth_is_independent_from_detector_predictions() -> None:
    hour = "2026-01-14T18:00:00"
    assert label_hour(hour) == LABEL_FESTIVE
    assert map_detector_prediction("suspicious_coordinated_spike") == LABEL_COORDINATED
    assert label_hour(hour) == LABEL_FESTIVE


def test_event_type_is_not_used_for_hour_labels() -> None:
    labels_source = Path("evaluation/labels.py").read_text(encoding="utf-8")
    detection_source = Path("evaluation/detection.py").read_text(encoding="utf-8")
    assert "event_type" not in labels_source
    assert "fraud_label" not in labels_source
    assert "detect_spikes" not in labels_source
    assert "event_type" not in detection_source.split("not_used")[0]


def test_fraud_label_is_not_spike_ground_truth() -> None:
    report = evaluate_heldout_detection()
    assert "fraud_label" in report["ground_truth"]["not_used"]
    assert "detector spike_type" in report["ground_truth"]["not_used"]


def test_precision_recall_f1_and_confusion_on_known_pairs() -> None:
    truths = [LABEL_COORDINATED, LABEL_COORDINATED, LABEL_FESTIVE, LABEL_BACKGROUND]
    predictions = [LABEL_COORDINATED, LABEL_FESTIVE, LABEL_FESTIVE, LABEL_BACKGROUND]
    counts = binary_counts(truths, predictions, LABEL_COORDINATED)
    assert counts == {"tp": 1, "fp": 0, "tn": 2, "fn": 1}
    scores = binary_scores(counts)
    assert scores["precision"] == 1.0
    assert scores["recall"] == 0.5
    assert scores["f1"] == 2 * 1.0 * 0.5 / (1.0 + 0.5)
    matrix = confusion_matrix(truths, predictions, (LABEL_COORDINATED, LABEL_FESTIVE, LABEL_BACKGROUND))
    assert matrix[LABEL_COORDINATED][LABEL_COORDINATED] == 1
    assert matrix[LABEL_COORDINATED][LABEL_FESTIVE] == 1
    assert matrix[LABEL_FESTIVE][LABEL_FESTIVE] == 1
    assert matrix[LABEL_BACKGROUND][LABEL_BACKGROUND] == 1


def test_zero_prediction_class_does_not_divide_by_zero() -> None:
    truths = [LABEL_COORDINATED, LABEL_BACKGROUND]
    predictions = [LABEL_BACKGROUND, LABEL_BACKGROUND]
    scores = binary_scores(binary_counts(truths, predictions, LABEL_COORDINATED))
    assert scores["precision"] is None
    assert scores["recall"] == 0.0
    assert scores["f1"] is None
    assert safe_divide(1, 0) is None
    assert f1_score(None, 1.0) is None


def test_heldout_detection_uses_seed_2027_and_is_json_serializable() -> None:
    report = evaluate_heldout_detection()
    assert report["seed"] == EVALUATION_SEED
    encoded = json.dumps(report)
    assert "coordinated_abuse" in encoded
    assert "legitimate_festive" in encoded


def test_festive_and_coordinated_remain_distinguishable() -> None:
    report = evaluate_heldout_detection()
    assert LABEL_COORDINATED != LABEL_FESTIVE
    assert LABEL_COORDINATED in report["confusion_matrix"]
    assert LABEL_FESTIVE in report["confusion_matrix"]
    assert report["per_class"][LABEL_COORDINATED]["tp"] != report["per_class"][LABEL_FESTIVE]["tp"] or (
        report["truth_counts"].get(LABEL_COORDINATED, 0) != report["truth_counts"].get(LABEL_FESTIVE, 0)
    )
    assert "festive_hours_predicted_as_coordinated_abuse" in report["product_checks"]


def test_detection_evaluation_does_not_touch_baseline_artifacts() -> None:
    before = {path: _sha256(path) for path in BASELINE_ARTIFACTS}
    evaluate_heldout_detection()
    after = {path: _sha256(path) for path in BASELINE_ARTIFACTS}
    assert before == after


_INV_REPORT: dict | None = None


def _investigation_report() -> dict:
    global _INV_REPORT
    if _INV_REPORT is None:
        _INV_REPORT = evaluate_heldout_investigations()
    return _INV_REPORT


def test_expected_verdict_is_independent_of_detector_type() -> None:
    expected = expected_investigation_verdict("2026-01-14T18:00:00", "2026-01-14T19:00:00")
    assert expected == "likely_festive"
    assert expected_investigation_verdict("2026-01-08T13:00:00", "2026-01-08T14:00:00") == "coordinated_abuse"
    assert expected_investigation_verdict("2026-01-06T09:00:00", "2026-01-06T10:00:00") == "inconclusive"
    report = _investigation_report()
    for case in report["cases"]:
        recomputed = expected_investigation_verdict(case["window_start"], case["window_end"])
        assert recomputed == case["expected_verdict"]
        assert case["expected_verdict"] != case["detector_type"]
        assert "spike_type" not in case["expected_verdict"]


def test_ambiguous_mixed_window_is_not_forced() -> None:
    assert (
        expected_investigation_verdict("2026-01-08T13:00:00", "2026-01-14T19:00:00")
        == "ambiguous"
    )


def test_heldout_evidence_excludes_event_type_and_marks_delayed_labels() -> None:
    spikes = load_heldout_spikes()
    transactions = load_heldout_transactions()
    hourly = load_heldout_hourly_windows()
    spike = spike_record_from_row(spikes.iloc[0])
    evidence = build_heldout_evidence(spike, transactions, hourly)
    dumped = json.dumps(evidence)
    assert "event_type" not in dumped
    assert "event_type" not in transactions.columns
    assert "delayed" in evidence["window"]["fraud_label_rate"]["interpretation"]


def test_heldout_investigation_evaluation_is_deterministic_and_uses_seed_2027() -> None:
    first = _investigation_report()
    second = evaluate_heldout_investigations()
    assert first["seed"] == EVALUATION_SEED
    assert first["n_correct"] == second["n_correct"]
    assert first["n_incorrect"] == second["n_incorrect"]
    assert first["n_ambiguous"] == second["n_ambiguous"]
    assert first["accuracy"] == second["accuracy"]


def test_investigation_correct_incorrect_and_accuracy() -> None:
    report = _investigation_report()
    assert report["n_detected_spikes"] >= 1
    assert report["n_evaluable"] == report["n_correct"] + report["n_incorrect"]
    assert report["n_correct"] + report["n_incorrect"] + report["n_ambiguous"] == report["n_detected_spikes"]
    if report["n_evaluable"]:
        assert report["accuracy"] == round(report["n_correct"] / report["n_evaluable"], 6)


def test_investigation_per_class_metrics_and_undefined_nulls() -> None:
    report = _investigation_report()
    for scores in report["per_class"].values():
        for key in ("precision", "recall", "f1"):
            assert scores[key] is None or isinstance(scores[key], float)
    from evaluation.metrics import binary_scores

    empty = binary_scores({"tp": 0, "fp": 0, "tn": 1, "fn": 0})
    assert empty["precision"] is None


def test_investigation_evidence_citations_and_entities_are_grounded() -> None:
    report = _investigation_report()
    assert report["evidence_grounding"]["citations_valid"] == report["n_detected_spikes"]
    assert report["evidence_grounding"]["entities_grounded"] == report["n_detected_spikes"]
    assert report["evidence_grounding"]["event_type_absent"] == report["n_detected_spikes"]


def test_investigation_recommendations_obey_policy() -> None:
    report = _investigation_report()
    assert report["recommendation_policy"]["human_approval_required"] == report["n_detected_spikes"]
    assert report["recommendation_policy"]["forbidden_actions"] == 0
    assert report["recommendation_policy"]["festive_tighten_rule"] == 0
    festive = [
        case
        for case in report["cases"]
        if case["actual_verdict"] == "likely_festive"
    ]
    assert all(case["recommended_action"]["type"] != "tighten_rule" for case in festive)


def test_investigation_output_is_json_serializable() -> None:
    encoded = json.dumps(_investigation_report())
    assert "deterministic_reasoner" in encoded


def test_investigation_evaluation_does_not_touch_baseline_or_step3() -> None:
    step3 = Path("data/heldout/detection_metrics.json")
    before = {path: _sha256(path) for path in BASELINE_ARTIFACTS}
    before_step3 = _sha256(step3) if step3.is_file() else None
    evaluate_heldout_investigations()
    after = {path: _sha256(path) for path in BASELINE_ARTIFACTS}
    assert before == after
    if before_step3 is not None:
        assert _sha256(step3) == before_step3


_EXPOSURE_REPORT: dict | None = None
STEP3_METRICS = Path("data/heldout/detection_metrics.json")
STEP4_METRICS = Path("evaluation/investigation_metrics.json")


def _exposure_report() -> dict:
    global _EXPOSURE_REPORT
    if _EXPOSURE_REPORT is None:
        _EXPOSURE_REPORT = evaluate_heldout_exposure()
    return _EXPOSURE_REPORT


def test_exposure_uses_heldout_seed_2027() -> None:
    report = _exposure_report()
    meta = json.loads(HELDOUT_META_PATH.read_text(encoding="utf-8"))
    assert report["seed"] == EVALUATION_SEED
    assert meta["seed"] == EVALUATION_SEED
    assert meta["n_transactions"] == 10404
    assert report["detected_spikes"]["n_spikes"] == 40


def test_timestamp_assigns_hourly_ground_truth_not_event_type() -> None:
    assert assign_transaction_ground_truth("2026-01-08T13:30:00") == LABEL_COORDINATED
    assert assign_transaction_ground_truth("2026-01-14T18:15:00") == LABEL_FESTIVE
    assert assign_transaction_ground_truth("2026-01-06T09:00:00") == LABEL_BACKGROUND
    assert assign_transaction_ground_truth(pd.NaT) is None
    assert assign_transaction_ground_truth("2026-01-08T13:30:00") == label_hour("2026-01-08T13:00:00")
    source = Path("evaluation/exposure.py").read_text(encoding="utf-8")
    assert "event_type" in source
    assert "not_used" in source
    frame = load_exposure_transactions()
    assert "event_type" not in frame.columns
    assert "fraud_label" not in frame.columns


def test_half_open_spike_windows_exclude_end() -> None:
    stamps = pd.Series(pd.to_datetime(["2026-01-08T13:00:00", "2026-01-08T13:59:59", "2026-01-08T14:00:00"]))
    mask = half_open_mask(stamps, "2026-01-08T13:00:00", "2026-01-08T14:00:00")
    assert list(mask) == [True, True, False]


def test_overlapping_windows_do_not_double_count() -> None:
    stamps = pd.Series(pd.to_datetime(["2026-01-08T13:30:00", "2026-01-08T14:30:00"]))
    windows = [
        (pd.Timestamp("2026-01-08T13:00:00"), pd.Timestamp("2026-01-08T15:00:00")),
        (pd.Timestamp("2026-01-08T13:00:00"), pd.Timestamp("2026-01-08T14:00:00")),
    ]
    mask = union_window_mask(stamps, windows)
    assert int(mask.sum()) == 2
    overlaps = overlapping_window_pairs(
        [
            (windows[0][0], windows[0][1], "a"),
            (windows[1][0], windows[1][1], "b"),
        ]
    )
    assert overlaps == [{"left": "a", "right": "b"}]


def test_overall_and_category_exposure_shares() -> None:
    report = _exposure_report()
    txs = load_exposure_transactions()
    labels, unassigned = label_transaction_hours(txs["timestamp"])
    assert unassigned == 0
    assert report["overall"]["transaction_count"] == len(txs)
    assert report["overall"]["total_amount"] == round(float(txs["amount"].sum()), 2)
    assert report["overall"]["mean_amount"] == round(float(txs["amount"].mean()), 2)
    assert report["overall"]["median_amount"] == round(float(txs["amount"].median()), 2)
    assert report["overall"]["maximum_amount"] == round(float(txs["amount"].max()), 2)
    tx_shares = [report["by_category"][label]["transaction_share"] for label in (LABEL_COORDINATED, LABEL_FESTIVE, LABEL_BACKGROUND)]
    amt_shares = [report["by_category"][label]["amount_share"] for label in (LABEL_COORDINATED, LABEL_FESTIVE, LABEL_BACKGROUND)]
    assert all(share is not None for share in tx_shares + amt_shares)
    assert abs(sum(tx_shares) - 1.0) < 1e-5
    assert abs(sum(amt_shares) - 1.0) < 1e-5
    assert sum(report["by_category"][label]["transaction_count"] for label in (LABEL_COORDINATED, LABEL_FESTIVE, LABEL_BACKGROUND)) == len(txs)


def test_detected_spike_exposure_and_coverage() -> None:
    report = _exposure_report()
    assert report["detected_spikes"]["n_spikes"] == 40
    assert len(report["detected_spikes"]["per_spike"]) == 40
    first = report["detected_spikes"]["per_spike"][0]
    for key in (
        "spike_id",
        "transaction_count",
        "total_amount",
        "mean_amount",
        "maximum_amount",
        "success_amount",
        "failed_amount",
        "declined_amount",
        "unique_accounts",
        "unique_devices",
        "unique_ip_subnets",
        "unique_pincodes",
        "unique_skus",
    ):
        assert key in first
    coverage = report["detected_spike_coverage"]["inside_any_detected_spike"]
    assert coverage["transaction_count"] <= report["overall"]["transaction_count"]
    by_gt = report["detected_spike_coverage"]["inside_any_detected_spike_by_ground_truth"]
    assert LABEL_COORDINATED in by_gt
    assert LABEL_FESTIVE in by_gt
    assert LABEL_BACKGROUND in by_gt


def test_coordinated_transaction_and_amount_capture() -> None:
    report = _exposure_report()
    from detection.scoring import SPIKE_TYPE_COORDINATED

    txs = load_exposure_transactions()
    labels, _ = label_transaction_hours(txs["timestamp"])
    txs = txs.assign(ground_truth=labels)
    coordinated = txs.loc[txs["ground_truth"] == LABEL_COORDINATED]
    spikes = load_exposure_spikes()
    coord_spikes = spikes.loc[spikes["spike_type"] == SPIKE_TYPE_COORDINATED]
    windows = [
        (pd.Timestamp(row["window_start"]), pd.Timestamp(row["window_end"]))
        for _, row in coord_spikes.iterrows()
    ]
    captured = coordinated.loc[union_window_mask(coordinated["timestamp"], windows)]
    capture = report["coordinated_capture"]
    assert capture["total_coordinated_transactions"] == int(len(coordinated))
    assert capture["captured_transactions"] == int(len(captured))
    assert capture["transaction_capture_rate"] == json_number(safe_divide(len(captured), len(coordinated)))
    assert capture["amount_capture_rate"] == json_number(
        safe_divide(json_amount(captured["amount"].sum()), json_amount(coordinated["amount"].sum()))
    )


def test_non_coordinated_surfaced_exposure_breakdown() -> None:
    report = _exposure_report()
    surfaced = report["non_coordinated_surfaced_exposure"]
    festive = surfaced["by_category"][LABEL_FESTIVE]["transaction_count"]
    background = surfaced["by_category"][LABEL_BACKGROUND]["transaction_count"]
    assert surfaced["transaction_count"] == festive + background
    assert surfaced["transaction_count"] == (
        report["detected_spike_coverage"]["inside_any_detected_spike_by_ground_truth"][LABEL_FESTIVE]["transaction_count"]
        + report["detected_spike_coverage"]["inside_any_detected_spike_by_ground_truth"][LABEL_BACKGROUND]["transaction_count"]
    )


def test_entity_and_payment_outcome_exposure() -> None:
    report = _exposure_report()
    for label in (LABEL_COORDINATED, LABEL_FESTIVE, LABEL_BACKGROUND):
        entities = report["entity_impact"][label]
        for key in ("unique_accounts", "unique_devices", "unique_ip_subnets", "unique_pincodes", "unique_skus"):
            assert entities[key] >= 0
        outcomes = report["payment_outcomes"][label]
        assert set(outcomes) == {"success", "failed", "declined"}
        assert outcomes["success"]["transaction_count"] + outcomes["failed"]["transaction_count"] + outcomes["declined"]["transaction_count"] == report["by_category"][label]["transaction_count"]
    assert "not additive" in report["entity_impact"]["note"]


def test_investigation_verdict_join_is_descriptive() -> None:
    report = _exposure_report()
    comparison = report["investigation_comparison"]
    assert comparison["source"] == "evaluation/investigation_metrics.json"
    assert "not ground truth" in comparison["note"]
    assert set(comparison["by_verdict"]) == {"coordinated_abuse", "likely_festive", "inconclusive"}
    step4 = json.loads(STEP4_METRICS.read_text(encoding="utf-8"))
    for verdict, row in comparison["by_verdict"].items():
        expected_n = sum(1 for case in step4["cases"] if case["actual_verdict"] == verdict)
        assert row["n_spikes"] == expected_n


def test_exposure_json_serializable_and_has_no_money_saved_metric() -> None:
    report = _exposure_report()
    encoded = json.dumps(report)
    assert "observed_exposure_only" in encoded
    for token in ("money_saved", "money_prevented", "losses_avoided", "revenue_protected", "roi_of_blocking"):
        assert token not in encoded or token in json.dumps(report["not_calculated"])
    assert "not_calculated" in report
    assert safe_divide(1, 0) is None


def test_exposure_makes_no_external_api_or_llm_calls() -> None:
    source = Path("evaluation/exposure.py").read_text(encoding="utf-8")
    assert "import requests" not in source
    assert "import httpx" not in source
    assert "urllib" not in source
    assert "openai" not in source
    assert "LLMInvestigationProvider" not in source
    assert "investigate_spike" not in source


def test_exposure_does_not_touch_baseline_or_prior_eval_artifacts() -> None:
    before_baseline = {path: _sha256(path) for path in BASELINE_ARTIFACTS}
    before_step3 = _sha256(STEP3_METRICS)
    before_step4 = _sha256(STEP4_METRICS)
    evaluate_heldout_exposure()
    assert {path: _sha256(path) for path in BASELINE_ARTIFACTS} == before_baseline
    assert _sha256(STEP3_METRICS) == before_step3
    assert _sha256(STEP4_METRICS) == before_step4
    assert HELDOUT_EXPOSURE_PATH.name == "exposure_metrics.json"


_INTERVENTION_REPORT: dict | None = None
STEP5_METRICS = Path("data/heldout/exposure_metrics.json")


def _intervention_report() -> dict:
    global _INTERVENTION_REPORT
    if _INTERVENTION_REPORT is None:
        _INTERVENTION_REPORT = evaluate_heldout_intervention()
    return _INTERVENTION_REPORT


def test_intervention_uses_heldout_seed_2027() -> None:
    report = _intervention_report()
    meta = json.loads(HELDOUT_META_PATH.read_text(encoding="utf-8"))
    assert report["heldout_seed"] == EVALUATION_SEED
    assert meta["seed"] == EVALUATION_SEED
    assert meta["n_transactions"] == 10404
    assert report["data_quality"]["heldout_spikes"] == 40
    assert report["data_quality"]["heldout_hourly_windows"] == 494


def test_intervention_scope_and_matching_semantics_are_explicit() -> None:
    parsed = parse_bounded_scope("review device dev_5001, subnet 185.220.101.0/24, sku sku_1048")
    assert parsed == {"device": "dev_5001", "subnet": "185.220.101.0/24", "sku": "sku_1048"}
    assert classify_recommendation("tighten_rule", "review device dev_1") == "evaluable"
    assert classify_recommendation("review", "analyst review of this window only") == "not_mechanically_evaluable"
    assert classify_recommendation("monitor", "window-level volume only; no entity block") == "not_mechanically_evaluable"
    assert classify_recommendation("tighten_rule", "this spike window only") == "not_evaluable"
    frame = pd.DataFrame(
        {
            "device_id": ["dev_1", "dev_1", "dev_2"],
            "ip_subnet": ["10.0.0.0/24", "9.0.0.0/24", "10.0.0.0/24"],
            "sku_id": ["sku_a", "sku_a", "sku_a"],
        }
    )
    constraints = {"device": "dev_1", "subnet": "10.0.0.0/24", "sku": "sku_a"}
    assert list(match_scope_mask(frame, constraints, "and")) == [True, False, False]
    assert list(match_scope_mask(frame, constraints, "or")) == [True, True, True]
    report = _intervention_report()
    assert "AND" in report["counterfactual"]["matching_semantics"]
    assert "OR" in report["counterfactual"]["matching_semantics"]
    assert "window_start <= timestamp < window_end" in report["counterfactual"]["temporal_scope"]


def test_intervention_half_open_and_bounded_scope() -> None:
    stamps = pd.Series(pd.to_datetime(["2026-01-08T13:00:00", "2026-01-08T14:00:00"]))
    assert list(half_open_mask(stamps, "2026-01-08T13:00:00", "2026-01-08T14:00:00")) == [True, False]
    report = _intervention_report()
    for case in report["cases"]:
        if case["evaluability"] != "evaluable":
            continue
        assert case["parsed_scope"]
        assert case["hypothetically_affected_and"]["transaction_count"] <= case["window"]["transaction_count"]
        assert case["hypothetically_affected_and"]["transaction_count"] <= case["hypothetically_affected_or"]["transaction_count"]


def test_intervention_coverage_precision_and_collateral() -> None:
    report = _intervention_report()
    metrics = report["metrics"]
    for key in ("precision_tx", "precision_amount", "recall_tx", "recall_amount"):
        assert metrics[key] is None or isinstance(metrics[key], float)
    assert 0 <= (metrics["precision_tx"] or 0) <= 1 or metrics["precision_tx"] is None
    assert report["coordinated_abuse"]["hypothetically_affected"]["transaction_count"] <= report["coordinated_abuse"]["applicable_window"]["transaction_count"]
    assert "legitimate_festive" in report["collateral"]
    assert "background" in report["collateral"]
    festive = report["collateral"]["legitimate_festive"]["transaction_count"]
    assert festive < report["festive_safety"]["festive_transactions_in_heldout_world"]
    assert report["festive_safety"]["entire_festive_period_in_scope"] is False
    txs = load_exposure_transactions()
    labels, _ = label_transaction_hours(txs["timestamp"])
    txs = txs.assign(ground_truth=labels)
    affected_n = report["overall"]["transaction_count"]
    coord_n = report["coordinated_abuse"]["hypothetically_affected"]["transaction_count"]
    assert metrics["precision_tx"] == json_number(safe_divide(coord_n, affected_n))
    assert metrics["recall_tx"] == json_number(
        safe_divide(coord_n, report["coordinated_abuse"]["applicable_window"]["transaction_count"])
    )


def test_intervention_undefined_ratios_and_no_money_claims() -> None:
    assert safe_divide(1, 0) is None
    report = _intervention_report()
    encoded = json.dumps(report)
    assert report["label"] == "HYPOTHETICAL / SIMULATION ONLY"
    for token in ("money_saved", "loss_prevented", "losses_avoided", "revenue_protected"):
        assert token in json.dumps(report["not_calculated"])
        assert encoded.count(token) == json.dumps(report["not_calculated"]).count(token)


def test_intervention_makes_no_production_api_or_llm_calls() -> None:
    source = Path("evaluation/intervention.py").read_text(encoding="utf-8")
    assert "execute_action" not in source
    assert "approve_action" not in source
    assert "simulate_action" not in source
    assert "import requests" not in source
    assert "import httpx" not in source
    assert "openai" not in source
    assert "LLMInvestigationProvider" not in source
    assert "event_type" in source
    assert "fraud_label" in source
    frame = load_exposure_transactions()
    assert "event_type" not in frame.columns
    assert "fraud_label" not in frame.columns


def test_intervention_does_not_touch_baseline_or_prior_eval_artifacts() -> None:
    before_baseline = {path: _sha256(path) for path in BASELINE_ARTIFACTS}
    before_step3 = _sha256(STEP3_METRICS)
    before_step4 = _sha256(STEP4_METRICS)
    before_step5 = _sha256(STEP5_METRICS)
    evaluate_heldout_intervention()
    assert {path: _sha256(path) for path in BASELINE_ARTIFACTS} == before_baseline
    assert _sha256(STEP3_METRICS) == before_step3
    assert _sha256(STEP4_METRICS) == before_step4
    assert _sha256(STEP5_METRICS) == before_step5
    assert HELDOUT_INTERVENTION_PATH.name == "intervention_metrics.json"


STEP6_METRICS = Path("data/heldout/intervention_metrics.json")


class _FakeLLMClient:
    def __init__(self, body: object) -> None:
        self.body = body

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if isinstance(self.body, Exception):
            raise self.body
        if isinstance(self.body, str):
            return self.body
        return json.dumps(self.body)


def _heldout_llm_fixture(spike_id: str | None = None) -> tuple[str, dict, str, dict]:
    spikes = load_heldout_spikes()
    if spike_id is None:
        row = spikes.iloc[0]
    else:
        row = spikes.loc[spikes["spike_id"] == spike_id].iloc[0]
    spike = spike_record_from_row(row)
    evidence = build_heldout_evidence(
        spike,
        load_heldout_transactions(),
        load_heldout_hourly_windows(),
    )
    prompt, facts = build_heldout_llm_prompt(spike, evidence)
    return str(spike["spike_id"]), evidence, prompt, facts


def _valid_llm_payload(facts: dict, verdict: str) -> dict:
    subnet = facts["concentration"]["subnets"][0]
    return {
        "spike_id": facts["spike_id"],
        "verdict": verdict,
        "confidence": 0.7,
        "summary": "Structured test report from supplied facts only.",
        "supporting_evidence": [
            {
                "fact": f"Declined rate is {facts['window']['status_rates']['declined']}",
                "source": "window.status_rates",
            }
        ],
        "contradicting_evidence": [],
        "key_entities": [
            {
                "entity_type": "subnet",
                "entity_id": subnet["entity_id"],
                "reason": "Present in deterministic evidence",
            }
        ],
        "reasoning": "Uses only supplied Phase 2A facts.",
        "recommended_action": {
            "type": "review",
            "scope": f"subnet {subnet['entity_id']}",
            "reason": "Narrow analyst review.",
        },
        "human_approval_required": True,
        "limitations": ["labelled-fraud rate is delayed ground truth; unavailable at decision time"],
    }


def test_llm_eval_uses_heldout_not_seed_42() -> None:
    source = Path("evaluation/llm.py").read_text(encoding="utf-8")
    assert "build_heldout_evidence" in source
    assert "build_investigation_evidence" not in source
    assert "from tools.paths" not in source
    spike_id, _evidence, _prompt, facts = _heldout_llm_fixture()
    expected = expected_investigation_verdict(
        load_heldout_spikes().loc[load_heldout_spikes()["spike_id"] == spike_id].iloc[0]["window_start"],
        load_heldout_spikes().loc[load_heldout_spikes()["spike_id"] == spike_id].iloc[0]["window_end"],
    )
    report = evaluate_heldout_llm(
        client=_FakeLLMClient(_valid_llm_payload(facts, expected)),
        mode="mock",
        spike_ids=[spike_id],
    )
    assert report["heldout_seed"] == EVALUATION_SEED
    assert "heldout" in report["heldout_paths"]["transactions"].replace("\\", "/")
    assert report["source"] == "mock"
    assert report["real_llm_evaluated"] is False
    assert report["label"] == "MOCK"


def test_llm_prompt_excludes_ledger_event_type_and_live_labels() -> None:
    _spike_id, _evidence, prompt, facts = _heldout_llm_fixture()
    assert "event_type" not in prompt
    assert "transaction_id" not in prompt
    assert "transactions.csv" not in prompt
    assert "festive_purchase" not in prompt
    assert "legitimate_purchase" not in prompt
    assert "delayed" in facts["window"]["fraud_label_rate"]["interpretation"].lower()
    from agent.prompts import prepare_llm_facts

    prepared = prepare_llm_facts(facts)
    assert prepared["window"]["fraud_label_rate"]["live_signal"] is False
    assert "delayed" in prepared["window"]["fraud_label_rate"]["interpretation"].lower()


def test_llm_valid_and_incorrect_verdicts_are_scored() -> None:
    spike_id, _evidence, _prompt, facts = _heldout_llm_fixture("spk-coord-20260108-13")
    expected = expected_investigation_verdict("2026-01-08T13:00:00", "2026-01-08T14:00:00")
    assert expected == "coordinated_abuse"
    correct = evaluate_heldout_llm(
        client=_FakeLLMClient(_valid_llm_payload(facts, "coordinated_abuse")),
        mode="mock",
        spike_ids=[spike_id],
    )
    assert correct["n_correct"] == 1
    assert correct["n_incorrect"] == 0
    assert correct["cases"][0]["status"] == "valid_correct"
    assert correct["accuracy"] == 1.0
    wrong = evaluate_heldout_llm(
        client=_FakeLLMClient(_valid_llm_payload(facts, "likely_festive")),
        mode="mock",
        spike_ids=[spike_id],
    )
    assert wrong["n_correct"] == 0
    assert wrong["n_incorrect"] == 1
    assert wrong["cases"][0]["status"] == "valid_incorrect"
    assert wrong["accuracy"] == 0.0


def test_llm_malformed_and_validation_failures_are_not_scored() -> None:
    spike_id, _evidence, _prompt, facts = _heldout_llm_fixture("spk-coord-20260108-13")
    malformed = evaluate_heldout_llm(
        client=_FakeLLMClient("this is not json"),
        mode="mock",
        spike_ids=[spike_id],
    )
    assert malformed["failure_counts"]["malformed_response"] == 1
    assert malformed["n_valid"] == 0
    assert malformed["accuracy"] is None
    assert malformed["cases"][0]["actual_verdict"] is None
    bad_cite = _valid_llm_payload(facts, "coordinated_abuse")
    bad_cite["supporting_evidence"] = [{"fact": "Invented", "source": "window.imaginary_metric"}]
    invalid = evaluate_heldout_llm(
        client=_FakeLLMClient(bad_cite),
        mode="mock",
        spike_ids=[spike_id],
    )
    assert invalid["failure_counts"]["validation_failure"] == 1
    assert invalid["n_correct"] == 0
    assert invalid["n_incorrect"] == 0
    forbidden = _valid_llm_payload(facts, "coordinated_abuse")
    forbidden["recommended_action"]["type"] = "block"
    blocked = evaluate_heldout_llm(
        client=_FakeLLMClient(forbidden),
        mode="mock",
        spike_ids=[spike_id],
    )
    assert blocked["failure_counts"]["validation_failure"] == 1
    no_approval = _valid_llm_payload(facts, "coordinated_abuse")
    no_approval["human_approval_required"] = False
    approval = evaluate_heldout_llm(
        client=_FakeLLMClient(no_approval),
        mode="mock",
        spike_ids=[spike_id],
    )
    assert approval["failure_counts"]["validation_failure"] == 1


def test_llm_ambiguous_cases_are_excluded_from_accuracy() -> None:
    assert score_valid_verdict("ambiguous", "coordinated_abuse") == (None, "ambiguous_excluded")
    assert score_valid_verdict("coordinated_abuse", "coordinated_abuse")[1] == "valid_correct"
    assert expected_investigation_verdict("2026-01-08T13:00:00", "2026-01-14T19:00:00") == "ambiguous"


def test_llm_missing_key_does_not_fabricate_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    report = evaluate_heldout_llm(mode="real")
    assert report["real_llm_evaluated"] is False
    assert report["source"] == "not_produced"
    assert report["cases"] == []
    assert report["accuracy"] is None
    assert report["n_attempted"] == 0


def test_llm_metrics_are_json_serializable_and_latency_is_calculated() -> None:
    spike_id, _evidence, _prompt, facts = _heldout_llm_fixture("spk-coord-20260108-13")
    report = evaluate_heldout_llm(
        client=_FakeLLMClient(_valid_llm_payload(facts, "coordinated_abuse")),
        mode="mock",
        spike_ids=[spike_id],
    )
    encoded = json.dumps(report)
    assert "MOCK" in encoded
    latency = report["latency_benchmark"]
    assert latency["n"] == 1
    assert latency["mean_seconds"] is not None
    assert latency["median_seconds"] is not None
    assert latency["max_seconds"] is not None
    assert latency["p95_seconds"] is None
    assert percentile([0.1], 0.95) is None
    assert percentile([0.1, 0.2, 0.3, 1.0], 0.95) is not None
    assert classify_llm_failure(LLMOutputError("Model returned malformed JSON")) == "malformed_response"
    assert classify_llm_failure(LLMOutputError("Citation source does not exist")) == "validation_failure"
    assert classify_llm_failure(LLMProviderError("LLM_API_KEY")) == "provider_failure"


def test_llm_eval_does_not_change_deterministic_provider_or_prior_artifacts() -> None:
    before_baseline = {path: _sha256(path) for path in BASELINE_ARTIFACTS}
    before = {
        "step3": _sha256(STEP3_METRICS),
        "step4": _sha256(STEP4_METRICS),
        "step5": _sha256(STEP5_METRICS),
        "step6": _sha256(STEP6_METRICS),
    }
    seed42 = investigate_spike("spk-coord-20260118-02", provider=DeterministicReasoner())
    assert seed42["provider"] == "deterministic_reasoner"
    spike_id, _evidence, _prompt, facts = _heldout_llm_fixture("spk-coord-20260108-13")
    evaluate_heldout_llm(
        client=_FakeLLMClient(_valid_llm_payload(facts, "coordinated_abuse")),
        mode="mock",
        spike_ids=[spike_id],
    )
    assert {path: _sha256(path) for path in BASELINE_ARTIFACTS} == before_baseline
    assert _sha256(STEP3_METRICS) == before["step3"]
    assert _sha256(STEP4_METRICS) == before["step4"]
    assert _sha256(STEP5_METRICS) == before["step5"]
    assert _sha256(STEP6_METRICS) == before["step6"]
    assert HELDOUT_LLM_PATH.name == "llm_metrics.json"
    source = Path("evaluation/llm.py").read_text(encoding="utf-8")
    assert "execute_action" not in source
    assert "approve_action" not in source
    assert "razorpay" not in source.lower()





