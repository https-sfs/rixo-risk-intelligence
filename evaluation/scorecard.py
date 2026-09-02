"""Formal synthetic spike-level evaluation scorecard.

Uses the seed-42 SYNTHETIC SCENARIO demo artifacts and existing label helpers.
Does not invent ground truth, mix worlds, or claim production performance.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from data.scenarios import ATTACKS, FESTIVE_END, FESTIVE_NAME, FESTIVE_START
from evaluation.detection import load_labelled_windows
from evaluation.intelligence import (
    IEEE_WORLD,
    SYNTHETIC_WORLD,
    classifier_evidence_status,
    load_ieee_test_operating_point,
)
from evaluation.investigation import expected_investigation_verdict
from evaluation.labels import LABEL_BACKGROUND, LABEL_COORDINATED, LABEL_FESTIVE
from evaluation.metrics import binary_counts, binary_scores, class_breakdown, confusion_matrix, json_number
from evaluation.paths import (
    BASELINE_META_PATH,
    BASELINE_SEED,
    BASELINE_SPIKES_CSV_PATH,
    BASELINE_WINDOWS_PATH,
    EVALUATION_SEED,
)

EVAL_LABELS = (LABEL_COORDINATED, LABEL_FESTIVE, LABEL_BACKGROUND)

FESTIVE_SPIKE_ID = "spk-fest-20260114-18"
CLUSTER_1_SPIKE_ID = "spk-coord-20260108-13"
CLUSTER_2_SPIKE_ID = "spk-coord-20260118-02"

KNOWN_INVESTIGATION_CASES = (
    {
        "scenario_id": "legitimate_festive_spike",
        "spike_id": FESTIVE_SPIKE_ID,
        "calendar_expected": "likely_festive",
    },
    {
        "scenario_id": "coordinated_abuse_cluster_1",
        "spike_id": CLUSTER_1_SPIKE_ID,
        "calendar_expected": "coordinated_abuse",
    },
    {
        "scenario_id": "coordinated_abuse_cluster_2",
        "spike_id": CLUSTER_2_SPIKE_ID,
        "calendar_expected": "coordinated_abuse",
    },
)

FORBIDDEN_SCORECARD_KEYS = (
    "ai_accuracy",
    "money_saved",
    "money_prevented",
    "production_performance",
    "production_accuracy",
    "roi",
)

IEEE_INTERVENTION_LIMITATION = (
    "Intervention effectiveness is not measurable as genuine before/after "
    "production performance on IEEE-CIS because the dataset is historical "
    "and no post-intervention ledger exists."
)

DETERMINISTIC_AGENT_TRADEOFF = (
    "The investigator uses a deterministic fixed read-only tool plan rather "
    "than LLM tool calling. This preserves reproducibility, bounded behavior, "
    "four-world isolation, and governance separation. The investigator is not "
    "an autonomous decision-maker."
)


def _metric(value: Any, *, methodology: str, source: str, provenance: str = "EVALUATION") -> dict[str, Any]:
    return {
        "value": value,
        "methodology": methodology,
        "source": source,
        "provenance": provenance,
    }


def _require_demo_meta() -> dict[str, Any]:
    meta = json.loads(BASELINE_META_PATH.read_text(encoding="utf-8"))
    seed = int(meta["seed"])
    if seed != BASELINE_SEED:
        raise ValueError(f"Synthetic scorecard requires demo seed {BASELINE_SEED}, got {seed}")
    return meta


def _contains_forbidden_keys(payload: Any) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            if lowered in FORBIDDEN_SCORECARD_KEYS:
                found.append(str(key))
            found.extend(_contains_forbidden_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_contains_forbidden_keys(item))
    return found


def evaluate_synthetic_detection() -> dict[str, Any]:
    """Window-level detection scores on the seed-42 demo ledger."""
    _require_demo_meta()
    labelled = load_labelled_windows(BASELINE_WINDOWS_PATH)
    truths = labelled["truth"].tolist()
    predictions = labelled["prediction"].tolist()
    matrix = confusion_matrix(truths, predictions, EVAL_LABELS)
    per_class = class_breakdown(truths, predictions, EVAL_LABELS)
    any_counts = binary_counts(
        ["scenario" if truth != LABEL_BACKGROUND else "background" for truth in truths],
        ["scenario" if prediction != LABEL_BACKGROUND else "background" for prediction in predictions],
        "scenario",
    )
    any_scores = binary_scores(any_counts)
    methodology = (
        "Hourly detector spike_type mapped into evaluation labels and compared "
        "to scenario-calendar truth from data.scenarios. Evaluation unit is the "
        "hourly window. fraud_label and event_type are not live detector inputs."
    )
    source = "data/hourly_windows.csv + data/scenarios.py"
    return {
        "evaluation_unit": "hourly_window",
        "n_windows": int(len(labelled)),
        "truth_counts": labelled["truth"].value_counts().to_dict(),
        "prediction_counts": labelled["prediction"].value_counts().to_dict(),
        "confusion_matrix": matrix,
        "any_injected_scenario_vs_any_spike": {
            "precision": _metric(
                json_number(any_scores["precision"]),
                methodology=f"{methodology} Positive = festive or coordinated calendar hour.",
                source=source,
            ),
            "recall": _metric(
                json_number(any_scores["recall"]),
                methodology=f"{methodology} Positive = festive or coordinated calendar hour.",
                source=source,
            ),
            "f1": _metric(
                json_number(any_scores["f1"]),
                methodology=f"{methodology} Harmonic mean of precision and recall.",
                source=source,
            ),
            "true_positive_windows": _metric(
                any_counts["tp"],
                methodology="Calendar scenario hours predicted as any spike.",
                source=source,
            ),
            "false_positive_windows": _metric(
                any_counts["fp"],
                methodology="Background hours predicted as any spike.",
                source=source,
            ),
            "false_negative_windows": _metric(
                any_counts["fn"],
                methodology="Calendar scenario hours predicted as ordinary.",
                source=source,
            ),
            "true_negative_windows": _metric(
                any_counts["tn"],
                methodology="Background hours predicted as ordinary.",
                source=source,
            ),
        },
        "per_class": {
            label: {
                "precision": _metric(
                    json_number(per_class[label]["precision"]),
                    methodology=f"One-vs-rest precision for {label}.",
                    source=source,
                ),
                "recall": _metric(
                    json_number(per_class[label]["recall"]),
                    methodology=f"One-vs-rest recall for {label}.",
                    source=source,
                ),
                "f1": _metric(
                    json_number(per_class[label]["f1"]),
                    methodology=f"One-vs-rest F1 for {label}.",
                    source=source,
                ),
                "true_positive_windows": per_class[label]["tp"],
                "false_positive_windows": per_class[label]["fp"],
                "false_negative_windows": per_class[label]["fn"],
            }
            for label in EVAL_LABELS
        },
        "methodology": methodology,
        "source": source,
        "in_sample_demo": True,
        "not_heldout_seed_2027": True,
        "not_production_performance": True,
    }


def evaluate_scenario_separation(labelled: pd.DataFrame | None = None) -> dict[str, Any]:
    frame = labelled if labelled is not None else load_labelled_windows(BASELINE_WINDOWS_PATH)
    starts = pd.to_datetime(frame["window_start"])

    def _hours_in(start: object, end: object) -> pd.DataFrame:
        mask = (starts >= pd.Timestamp(start)) & (starts < pd.Timestamp(end))
        return frame.loc[mask]

    festive_hours = frame.loc[frame["truth"] == LABEL_FESTIVE]
    festive_detected = bool((festive_hours["prediction"] == LABEL_FESTIVE).any())
    festive_as_coordinated = int((festive_hours["prediction"] == LABEL_COORDINATED).sum())

    clusters: list[dict[str, Any]] = []
    for index, spec in enumerate(ATTACKS, start=1):
        hours = _hours_in(spec.start, spec.end)
        detected = bool((hours["prediction"] == LABEL_COORDINATED).any())
        clusters.append(
            {
                "cluster_index": index,
                "name": spec.name,
                "window_start": spec.start.isoformat(timespec="seconds"),
                "window_end": spec.end.isoformat(timespec="seconds"),
                "calendar_hours": int(len(hours)),
                "detected": detected,
                "detected_as_coordinated_hours": int((hours["prediction"] == LABEL_COORDINATED).sum()),
                "representative_spike_id": CLUSTER_1_SPIKE_ID if index == 1 else CLUSTER_2_SPIKE_ID,
            }
        )

    source = "data/hourly_windows.csv + data/scenarios.py AttackSpec / festive calendar"
    return {
        "legitimate_festive_spike_detected": _metric(
            festive_detected,
            methodology=(
                f"{FESTIVE_NAME} calendar hours ({FESTIVE_START.isoformat(timespec='seconds')} to "
                f"{FESTIVE_END.isoformat(timespec='seconds')}, excluding attack hours) predicted as "
                "legitimate_festive."
            ),
            source=source,
        ),
        "festive_representative_spike_id": FESTIVE_SPIKE_ID,
        "coordinated_abuse_cluster_1_detected": _metric(
            clusters[0]["detected"],
            methodology="At least one hour inside AttackSpec #1 predicted as coordinated_abuse.",
            source=source,
        ),
        "coordinated_abuse_cluster_2_detected": _metric(
            clusters[1]["detected"],
            methodology="At least one hour inside AttackSpec #2 predicted as coordinated_abuse.",
            source=source,
        ),
        "clusters": clusters,
        "legitimate_festive_treated_as_coordinated_abuse": _metric(
            festive_as_coordinated > 0,
            methodology="Any festive-calendar hour predicted as coordinated_abuse.",
            source=source,
        ),
        "festive_hours_predicted_as_coordinated_abuse": _metric(
            festive_as_coordinated,
            methodology="Count of festive-calendar hours predicted as coordinated_abuse.",
            source=source,
        ),
        "not_cross_world": True,
    }


def _investigate_known_case(spike_id: str) -> dict[str, Any]:
    from agent.investigate import investigate_spike
    from tools.load import load_detected_spike

    spike = load_detected_spike(spike_id)
    expected = expected_investigation_verdict(spike["window_start"], spike["window_end"])
    result = investigate_spike(spike_id)
    report = result["report"]
    verdict = str(report.get("verdict") or "")
    supporting = list(report.get("supporting_evidence") or [])
    contradicting = list(report.get("contradicting_evidence") or [])
    return {
        "spike_id": spike_id,
        "finding": {
            "verdict": verdict,
            "summary": report.get("summary"),
            "recommended_action_type": (report.get("recommended_action") or {}).get("type"),
        },
        "calendar_expected": expected,
        "agrees_with_known_scenario": verdict == expected,
        "evidence_completeness": {
            "supporting_evidence_count": len(supporting),
            "contradicting_evidence_count": len(contradicting),
            "supporting_present": len(supporting) > 0,
            "methodology": (
                "Counts already produced by the deterministic investigation report. "
                "Not an invented AI accuracy score."
            ),
            "source": "agent.investigate.investigate_spike report",
        },
        "human_approval_required": report.get("human_approval_required") is True,
        "provider": result.get("provider"),
    }


def evaluate_synthetic_investigation() -> dict[str, Any]:
    cases = []
    for spec in KNOWN_INVESTIGATION_CASES:
        case = _investigate_known_case(spec["spike_id"])
        case["scenario_id"] = spec["scenario_id"]
        cases.append(case)
    agreed = sum(1 for case in cases if case["agrees_with_known_scenario"])
    return {
        "evaluation_unit": "known_synthetic_scenario_spike",
        "n_known_scenarios": len(cases),
        "scenario_agreement_count": _metric(
            agreed,
            methodology=(
                "Deterministic investigation verdict compared to scenario-calendar "
                "expectation from evaluation.investigation.expected_investigation_verdict. "
                "This is calendar agreement, not an invented AI accuracy metric."
            ),
            source="investigate_spike + data/scenarios.py",
        ),
        "cases": cases,
        "not_an_ai_accuracy_metric": True,
        "not_production_performance": True,
    }


def evaluate_governance_correctness() -> dict[str, Any]:
    """Deterministic process checks. Not ML accuracy. Does not call Razorpay."""
    from agent.actions.errors import ActionError
    from agent.actions.gates import validate_proposal_inputs
    from agent.actions.service import default_store, execute_action, propose_from_report
    from agent.actions.store import ActionStore
    from agent.schema import EvidenceCitation, InvestigationReport, RecommendedAction

    isolated = ActionStore()
    if isolated is default_store():
        raise RuntimeError("Governance scorecard must not use the live ActionStore")

    decision_requires_evidence = False
    try:
        validate_proposal_inputs({"spike_id": "spk-governance-check"})
    except ActionError:
        decision_requires_evidence = True

    approval_gate = False
    try:
        validate_proposal_inputs(
            {
                "spike_id": "spk-governance-check",
                "verdict": "coordinated_abuse",
                "recommended_action": {
                    "type": "review",
                    "scope": "this spike window only",
                    "reason": "governance process check",
                },
                "human_approval_required": False,
            }
        )
    except ActionError:
        approval_gate = True

    report = InvestigationReport(
        spike_id="spk-governance-check",
        verdict="coordinated_abuse",
        confidence=0.7,
        summary="Isolated governance process check.",
        supporting_evidence=[EvidenceCitation(fact="process check", source="window.volume")],
        contradicting_evidence=[],
        key_entities=[],
        reasoning="Isolated process check. Not a live investigation.",
        recommended_action=RecommendedAction(
            type="review",
            scope="this spike window only",
            reason="Isolated governance process check.",
        ),
        human_approval_required=True,
    )
    proposal = propose_from_report(report, store=isolated)
    simulation_blocked = False
    try:
        execute_action(proposal.action_id, store=isolated)
    except ActionError as exc:
        simulation_blocked = "approved" in str(exc).lower()

    if default_store().latest_proposal_for_spike("spk-governance-check") is not None:
        raise RuntimeError("Governance scorecard mutated the live ActionStore")

    investigator_source = Path("agent/investigator.py").read_text(encoding="utf-8")
    investigator_cannot_authorize = all(
        token not in investigator_source
        for token in ("ActionStore", "approve_action", "execute_action", "Razorpay", "razorpay")
    ) and "deterministic_tool_plan" in investigator_source

    classifier_status = classifier_evidence_status(
        {"status": "scored", "feature_coverage": 0.9, "score": 0.8, "high_risk_count": 3},
        world=SYNTHETIC_WORLD,
    )
    classifier_cannot_select = classifier_status.get("used_for_action_selection") is False

    simulate_source = Path("agent/actions/simulate.py").read_text(encoding="utf-8")
    sandbox_source = Path("backend/app/integrations/sandbox_payments.py").read_text(encoding="utf-8")
    simulation_is_test_only = (
        "SIMULATED" in simulate_source
        and "No live payment was executed" in sandbox_source
        and "TEST" in sandbox_source.upper()
    )

    service_source = Path("agent/actions/service.py").read_text(encoding="utf-8")
    audit_ordered = (
        service_source.find("ACTION_PROPOSED")
        < service_source.find("ACTION_APPROVED")
        < service_source.find("ACTION_SIMULATED")
    )

    source = "agent.actions.gates / isolated ActionStore / classifier_evidence_status / source contracts"
    return {
        "kind": "governance_process_checks",
        "not_ml_accuracy": True,
        "decision_requires_investigation_evidence": _metric(
            decision_requires_evidence,
            methodology="validate_proposal_inputs rejects a payload without investigation verdict/action.",
            source=source,
        ),
        "approval_required": _metric(
            approval_gate,
            methodology="validate_proposal_inputs requires human_approval_required is true.",
            source=source,
        ),
        "simulation_blocked_before_approval": _metric(
            simulation_blocked,
            methodology="execute_action on an isolated store raises before explicit approval. Razorpay is not called.",
            source=source,
        ),
        "simulation_is_test_only": _metric(
            simulation_is_test_only,
            methodology="simulate.py and sandbox_payments.py remain SIMULATED / TEST / no live payment.",
            source=source,
        ),
        "audit_events_are_ordered": _metric(
            audit_ordered,
            methodology="ACTION_PROPOSED then ACTION_APPROVED then ACTION_SIMULATED in agent.actions.service.",
            source=source,
        ),
        "investigator_cannot_authorize_action": _metric(
            investigator_cannot_authorize,
            methodology="agent/investigator.py has no ActionStore, approval, execution, or Razorpay import.",
            source="agent/investigator.py",
        ),
        "classifier_evidence_cannot_independently_select_action": _metric(
            classifier_cannot_select,
            methodology="classifier_evidence_status() is the sole status path and sets used_for_action_selection false.",
            source="evaluation.intelligence.classifier_evidence_status",
        ),
        "live_action_store_unchanged": True,
        "razorpay_not_invoked": True,
    }


def _heldout_reference() -> dict[str, Any]:
    return {
        "world": SYNTHETIC_WORLD,
        "seed": EVALUATION_SEED,
        "note": (
            "Seed-2027 holdout metrics remain a separate evaluation artifact. "
            "They are not mixed into seed-42 demo detection scores."
        ),
        "detection_source": "data/heldout/detection_metrics.json",
        "investigation_source": "evaluation/investigation_metrics.json",
        "not_the_same_dataset": True,
    }


def _classifier_section() -> dict[str, Any]:
    return {
        "included_in_spike_detection": False,
        "not_recomputed_as_synthetic_spike_metrics": True,
        "note": (
            "IEEE-CIS classifier metrics are a separate historical evaluation. "
            "They are not relabelled as synthetic spike detection performance."
        ),
        "ieee_historical_reference": {
            "world": IEEE_WORLD,
            **(load_ieee_test_operating_point() or {"available": False}),
        },
    }


@lru_cache(maxsize=1)
def build_synthetic_scorecard() -> dict[str, Any]:
    meta = _require_demo_meta()
    detection = evaluate_synthetic_detection()
    labelled = load_labelled_windows(BASELINE_WINDOWS_PATH)
    scenario = evaluate_scenario_separation(labelled)
    investigation = evaluate_synthetic_investigation()
    governance = evaluate_governance_correctness()
    n_spikes = int(pd.read_csv(BASELINE_SPIKES_CSV_PATH).shape[0])
    payload = {
        "evaluation": {
            "scope": "synthetic_spike_level_detection",
            "world": SYNTHETIC_WORLD,
            "dataset": {
                "name": "seed-42 SYNTHETIC SCENARIO demo ledger",
                "seed": BASELINE_SEED,
                "n_transactions": int(meta["n_transactions"]),
                "n_detected_spikes": n_spikes,
                "n_hourly_windows": detection["n_windows"],
                "source": "data/dataset_meta.json + data/hourly_windows.csv + data/detected_spikes.csv",
                "in_sample_demo": True,
                "not_heldout_seed_2027": True,
                "not_production_traffic": True,
            },
            "methodology": {
                "detection_unit": "hourly_window",
                "ground_truth": {
                    "source": "data.scenarios festive calendar and AttackSpec windows",
                    "not_used_as_live_detector_input": ["fraud_label", "event_type", "isFraud"],
                    "labels": {
                        LABEL_COORDINATED: "hour overlaps an injected AttackSpec window",
                        LABEL_FESTIVE: "hour is inside the festive sale calendar and is not an attack hour",
                        LABEL_BACKGROUND: "hour is outside festive and attack calendars",
                    },
                },
                "prediction": {
                    "source": "data/hourly_windows.csv spike_type written by the existing detector",
                    "mapping": {
                        "suspicious_coordinated_spike": LABEL_COORDINATED,
                        "legitimate_festive_spike": LABEL_FESTIVE,
                        "ordinary": LABEL_BACKGROUND,
                    },
                },
                "in_sample_note": (
                    "This scorecard evaluates the seed-42 demo world the operator console uses. "
                    "It is a controlled in-sample scenario evaluation, not held-out seed 2027, "
                    "and not production performance."
                ),
                "deterministic_investigator": DETERMINISTIC_AGENT_TRADEOFF,
            },
            "detection": detection,
            "scenario_separation": scenario,
            "investigation": investigation,
            "governance": governance,
            "classifier": _classifier_section(),
            "heldout_reference": _heldout_reference(),
            "limitations": [
                "Controlled synthetic evaluation only. Not production performance.",
                "Seed-42 metrics are in-sample for the demo ledger and are not mixed with seed-2027 holdout scores.",
                "Worlds are never compared as if they were one dataset.",
                "fraud_label is delayed synthetic ground truth and is not a live detector input.",
                IEEE_INTERVENTION_LIMITATION,
                DETERMINISTIC_AGENT_TRADEOFF,
                "No money-saved, ROI, or live payment-execution claim is produced.",
            ],
        }
    }
    forbidden = _contains_forbidden_keys(payload)
    if forbidden:
        raise ValueError(f"Scorecard must not include fabricated or impact-claim keys: {forbidden}")
    return payload


def synthetic_scorecard() -> dict[str, Any]:
    return json.loads(json.dumps(build_synthetic_scorecard()))
