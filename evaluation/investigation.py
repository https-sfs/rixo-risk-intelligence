"""Held-out investigation evaluation. Deterministic provider only."""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path
from typing import Any

import pandas as pd

from agent.actions.errors import ActionError
from agent.actions.gates import validate_proposal_inputs
from agent.investigate import investigate_spike
from agent.providers.deterministic import DeterministicReasoner
from agent.schema import ALLOWED_ACTIONS, FORBIDDEN_ACTIONS
from agent.validation import resolve_source
from evaluation.heldout_evidence import (
    build_heldout_evidence,
    load_heldout_hourly_windows,
    load_heldout_spikes,
    load_heldout_transactions,
    spike_record_from_row,
)
from evaluation.labels import LABEL_COORDINATED, LABEL_FESTIVE, label_hour
from evaluation.metrics import class_breakdown, json_number, safe_divide
from evaluation.paths import EVALUATION_SEED, HELDOUT_META_PATH

VERDICTS = ("coordinated_abuse", "likely_festive", "inconclusive")
METRICS_PATH = Path(__file__).resolve().parent / "investigation_metrics.json"


def covered_hours(window_start: object, window_end: object) -> list[pd.Timestamp]:
    start = pd.Timestamp(window_start)
    end = pd.Timestamp(window_end)
    hours: list[pd.Timestamp] = []
    cursor = start.floor("h")
    while cursor < end:
        hours.append(cursor)
        cursor += pd.Timedelta(hours=1)
    return hours


def expected_investigation_verdict(window_start: object, window_end: object) -> str:
    """Scenario-calendar expectation. Independent of detector spike_type."""
    labels = {label_hour(hour) for hour in covered_hours(window_start, window_end)}
    if LABEL_COORDINATED in labels and LABEL_FESTIVE in labels:
        return "ambiguous"
    if LABEL_COORDINATED in labels:
        return "coordinated_abuse"
    if LABEL_FESTIVE in labels:
        return "likely_festive"
    return "inconclusive"


def _citation_sources_valid(report: dict[str, Any], facts: dict[str, Any]) -> bool:
    citations = list(report.get("supporting_evidence") or []) + list(
        report.get("contradicting_evidence") or []
    )
    for item in citations:
        try:
            resolve_source(facts, str(item.get("source") or ""))
        except Exception:
            return False
    return True


def _entities_grounded(report: dict[str, Any], evidence: dict[str, Any]) -> bool:
    dumped = json.dumps(evidence)
    for entity in report.get("key_entities") or []:
        entity_id = str(entity.get("entity_id") or "")
        if not entity_id or entity_id not in dumped:
            return False
    return True


def _recommendation_policy(report: dict[str, Any]) -> dict[str, Any]:
    action = report.get("recommended_action") or {}
    action_type = str(action.get("type") or "")
    forbidden = action_type in FORBIDDEN_ACTIONS
    allowed = action_type in ALLOWED_ACTIONS
    festive_tighten = report.get("verdict") == "likely_festive" and action_type == "tighten_rule"
    policy_ok = False
    policy_error = None
    try:
        validate_proposal_inputs(report)
        policy_ok = True
    except ActionError as exc:
        policy_error = str(exc)
    return {
        "allowed_action": allowed,
        "forbidden_action": forbidden,
        "human_approval_required": report.get("human_approval_required") is True,
        "festive_tighten_rule": festive_tighten,
        "proposal_policy_ok": policy_ok,
        "proposal_policy_error": policy_error,
    }


def evaluate_heldout_investigations() -> dict[str, Any]:
    started = time.perf_counter()
    meta = json.loads(HELDOUT_META_PATH.read_text(encoding="utf-8"))
    seed = int(meta["seed"])
    if seed != EVALUATION_SEED:
        raise ValueError(f"Investigation evaluation requires held-out seed {EVALUATION_SEED}, got {seed}")

    spikes = load_heldout_spikes()
    transactions = load_heldout_transactions()
    hourly = load_heldout_hourly_windows()
    if "event_type" in transactions.columns:
        raise ValueError("Held-out investigation evidence must not include event_type")

    cases: list[dict[str, Any]] = []
    latencies: list[float] = []
    reasoner = DeterministicReasoner()

    for _, row in spikes.iterrows():
        spike = spike_record_from_row(row)
        expected = expected_investigation_verdict(spike["window_start"], spike["window_end"])
        evidence = build_heldout_evidence(spike, transactions, hourly)
        evidence_dump = json.dumps(evidence)
        if "event_type" in evidence_dump:
            raise ValueError("event_type leaked into investigation evidence")

        t0 = time.perf_counter()
        result = investigate_spike(
            spike["spike_id"],
            provider=reasoner,
            evidence=evidence,
        )
        latency = time.perf_counter() - t0
        latencies.append(latency)

        report = result["report"]
        facts = result["facts_used"]
        verdict = str(report["verdict"])
        evaluable = expected != "ambiguous"
        correct = evaluable and verdict == expected
        citations_ok = _citation_sources_valid(report, facts)
        entities_ok = _entities_grounded(report, evidence)
        delayed_label = facts.get("window", {}).get("fraud_label_rate", {})
        delayed_ok = "delayed" in str(delayed_label.get("interpretation") or "").lower()
        missing_volume = evidence["baseline_comparison"]["hourly_baseline"]["baseline_volume"]["status"] == "unavailable"
        missing_ack = (not missing_volume) or any(
            "unavailable" in str(item).lower() for item in (report.get("limitations") or [])
        ) or evidence["baseline_comparison"]["hourly_baseline"]["baseline_volume"]["status"] == "unavailable"
        policy = _recommendation_policy(report)
        cases.append(
            {
                "spike_id": spike["spike_id"],
                "window_start": spike["window_start"].strftime("%Y-%m-%dT%H:%M:%S"),
                "window_end": spike["window_end"].strftime("%Y-%m-%dT%H:%M:%S"),
                "detector_type": spike["spike_type"],
                "expected_verdict": expected,
                "actual_verdict": verdict,
                "evaluable": evaluable,
                "correct": correct,
                "supporting_evidence_count": len(report.get("supporting_evidence") or []),
                "contradicting_evidence_count": len(report.get("contradicting_evidence") or []),
                "citations_valid": citations_ok,
                "entities_grounded": entities_ok,
                "event_type_absent": "event_type" not in json.dumps(facts) and "event_type" not in json.dumps(report),
                "fraud_label_marked_delayed": delayed_ok,
                "missing_baseline_acknowledged": missing_ack,
                "human_approval_required": report.get("human_approval_required") is True,
                "recommended_action": report.get("recommended_action"),
                "policy": policy,
                "latency_seconds": round(latency, 6),
                "provider": result["provider"],
            }
        )

    evaluable_cases = [case for case in cases if case["evaluable"]]
    correct_n = sum(1 for case in evaluable_cases if case["correct"])
    incorrect_n = sum(1 for case in evaluable_cases if not case["correct"])
    ambiguous_n = sum(1 for case in cases if not case["evaluable"])
    truths = [case["expected_verdict"] for case in evaluable_cases]
    preds = [case["actual_verdict"] for case in evaluable_cases]
    per_class = class_breakdown(truths, preds, VERDICTS) if evaluable_cases else {}
    elapsed = time.perf_counter() - started

    return {
        "seed": seed,
        "provider": "deterministic_reasoner",
        "evaluation_unit": "detected_spike",
        "ground_truth": {
            "source": "Step 3 scenario calendars via covered hours of each detected spike",
            "not_used": ["detector spike_type", "fraud_label as live score", "event_type as evidence"],
            "mapping": {
                "coordinated_abuse hour": "expected verdict coordinated_abuse",
                "festive hour only": "expected verdict likely_festive",
                "background hours only": "expected verdict inconclusive",
                "coordinated and festive hours": "ambiguous / not scored",
            },
        },
        "n_detected_spikes": len(cases),
        "n_evaluable": len(evaluable_cases),
        "n_correct": correct_n,
        "n_incorrect": incorrect_n,
        "n_ambiguous": ambiguous_n,
        "accuracy": json_number(safe_divide(correct_n, len(evaluable_cases))),
        "per_class": {
            label: {
                **{key: per_class[label][key] for key in ("tp", "fp", "tn", "fn")},
                "precision": json_number(per_class[label]["precision"]),
                "recall": json_number(per_class[label]["recall"]),
                "f1": json_number(per_class[label]["f1"]),
            }
            for label in VERDICTS
        }
        if per_class
        else {},
        "evidence_grounding": {
            "citations_valid": sum(1 for case in cases if case["citations_valid"]),
            "entities_grounded": sum(1 for case in cases if case["entities_grounded"]),
            "event_type_absent": sum(1 for case in cases if case["event_type_absent"]),
            "fraud_label_marked_delayed": sum(1 for case in cases if case["fraud_label_marked_delayed"]),
            "supporting_present": sum(1 for case in cases if case["supporting_evidence_count"] > 0),
            "contradicting_present": sum(1 for case in cases if case["contradicting_evidence_count"] > 0),
        },
        "recommendation_policy": {
            "human_approval_required": sum(1 for case in cases if case["human_approval_required"]),
            "allowed_actions": sum(1 for case in cases if case["policy"]["allowed_action"]),
            "forbidden_actions": sum(1 for case in cases if case["policy"]["forbidden_action"]),
            "festive_tighten_rule": sum(1 for case in cases if case["policy"]["festive_tighten_rule"]),
            "proposal_policy_ok": sum(1 for case in cases if case["policy"]["proposal_policy_ok"]),
        },
        "latency_benchmark": {
            "label": "engineering benchmark, not model accuracy",
            "n": len(latencies),
            "total_evaluation_seconds": json_number(elapsed),
            "mean_seconds": json_number(statistics.mean(latencies) if latencies else None),
            "median_seconds": json_number(statistics.median(latencies) if latencies else None),
            "max_seconds": json_number(max(latencies) if latencies else None),
        },
        "cases": cases,
    }


def write_investigation_report(
    report: dict[str, Any] | None = None,
    output_path: Path | None = None,
) -> Path:
    payload = report if report is not None else evaluate_heldout_investigations()
    dest = output_path or METRICS_PATH
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def write_investigation_markdown(report: dict[str, Any], output_path: Path) -> Path:
    per_class = report["per_class"]
    lines = [
        "# Phase 7 Step 4 — Investigation evaluation",
        "",
        "Held-out seed **2027** only. Existing deterministic reasoner. This step measures the investigator; it does not change it.",
        "",
        "## Evaluation unit",
        "",
        "One **detected spike** from `data/heldout/detected_spikes.csv`.",
        "A spike may cover one or more clock hours. Expected verdict is derived from those covered hours, not from the detector `spike_type`.",
        "",
        "## Ground truth",
        "",
        "Reuse Step 3 scenario calendars (`evaluation/labels.py`):",
        "",
        "- any coordinated-abuse hour → expected `coordinated_abuse`",
        "- else any festive-sale hour → expected `likely_festive`",
        "- else background hours only → expected `inconclusive`",
        "- coordinated and festive hours in the same spike → `ambiguous` (not scored)",
        "",
        "`event_type` and delayed `fraud_label` are not investigation evidence. `event_type` is hidden evaluation metadata only.",
        "",
        f"- Detected spikes evaluated: {report['n_detected_spikes']}",
        f"- Objectively evaluable: {report['n_evaluable']}",
        f"- Correct / incorrect / ambiguous: {report['n_correct']} / {report['n_incorrect']} / {report['n_ambiguous']}",
        f"- Accuracy (evaluable cases): {report['accuracy']}",
        "",
        "| Class | Precision | Recall | F1 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, scores in per_class.items():
        lines.append(
            f"| {label} | {scores['precision']} | {scores['recall']} | {scores['f1']} |"
        )
    grounding = report["evidence_grounding"]
    policy = report["recommendation_policy"]
    latency = report["latency_benchmark"]
    mismatches = [
        case
        for case in report.get("cases") or []
        if case.get("evaluable") and not case.get("correct")
    ]
    if mismatches:
        lines.extend(["", "Incorrect evaluable cases:", ""])
        for case in mismatches:
            lines.append(
                f"- `{case['spike_id']}` expected `{case['expected_verdict']}`, "
                f"actual `{case['actual_verdict']}` (detector `{case['detector_type']}`)"
            )
    lines.extend(
        [
            "",
            "## Evidence grounding",
            "",
            f"- Citations valid: {grounding['citations_valid']} / {report['n_detected_spikes']}",
            f"- Entities grounded: {grounding['entities_grounded']} / {report['n_detected_spikes']}",
            f"- event_type absent: {grounding['event_type_absent']} / {report['n_detected_spikes']}",
            f"- fraud_label marked delayed: {grounding['fraud_label_marked_delayed']} / {report['n_detected_spikes']}",
            f"- Reports with supporting evidence: {grounding['supporting_present']}",
            f"- Reports with contradicting evidence: {grounding['contradicting_present']}",
            "",
            "## Recommendation policy",
            "",
            f"- Human approval required: {policy['human_approval_required']}",
            f"- Allowed actions: {policy['allowed_actions']}",
            f"- Forbidden actions: {policy['forbidden_actions']}",
            f"- Festive tighten_rule: {policy['festive_tighten_rule']}",
            f"- Proposal policy ok: {policy['proposal_policy_ok']}",
            "",
            "## Latency (engineering benchmark, not model accuracy)",
            "",
            f"- Total evaluation seconds: {latency['total_evaluation_seconds']}",
            f"- Mean / median / max seconds: {latency['mean_seconds']} / {latency['median_seconds']} / {latency['max_seconds']}",
            "",
            "Run: `python -m evaluation.investigation`",
            "",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    report = evaluate_heldout_investigations()
    json_path = write_investigation_report(report)
    md_path = write_investigation_markdown(
        report,
        Path(__file__).resolve().parent.parent / "docs" / "phase-7-investigation.md",
    )
    printable = {key: value for key, value in report.items() if key != "cases"}
    print(json.dumps(printable, indent=2))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
