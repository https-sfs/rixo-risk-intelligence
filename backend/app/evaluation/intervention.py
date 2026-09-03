"""Hypothetical bounded-intervention counterfactual. Simulation only.

Does not execute Phase 3B actions, call APIs, or run the optional LLM.
Does not claim money saved, blocked, or prevented.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.exposure import (
    half_open_mask,
    json_amount,
    label_transaction_hours,
    load_exposure_transactions,
)
from evaluation.investigation import expected_investigation_verdict
from evaluation.labels import LABEL_BACKGROUND, LABEL_COORDINATED, LABEL_FESTIVE
from evaluation.metrics import json_number, safe_divide
from evaluation.paths import (
    EVALUATION_SEED,
    HELDOUT_INTERVENTION_PATH,
    HELDOUT_META_PATH,
    HELDOUT_SPIKES_CSV_PATH,
    HELDOUT_WINDOWS_PATH,
)

INVESTIGATION_METRICS_PATH = Path(__file__).resolve().parent / "investigation_metrics.json"

SCOPE_PATTERNS = (
    ("device", "device_id", re.compile(r"\bdevice\s+(\S+)", re.IGNORECASE)),
    ("subnet", "ip_subnet", re.compile(r"\bsubnet\s+(\S+)", re.IGNORECASE)),
    ("sku", "sku_id", re.compile(r"\bsku\s+(\S+)", re.IGNORECASE)),
)

FORBIDDEN_IMPACT_KEYS = (
    "money_saved",
    "money_prevented",
    "loss_prevented",
    "losses_avoided",
    "loss_avoided",
    "avoided_loss",
    "revenue_protected",
    "roi",
    "roi_of_blocking",
)


def parse_bounded_scope(scope: str) -> dict[str, str]:
    """Extract explicit entity constraints from an existing recommendation scope."""
    constraints: dict[str, str] = {}
    text = str(scope or "")
    for name, _column, pattern in SCOPE_PATTERNS:
        match = pattern.search(text)
        if match:
            constraints[name] = match.group(1).rstrip(",")
    return constraints


def classify_recommendation(action_type: str, scope: str) -> str:
    normalized = str(action_type or "").strip()
    if normalized in {"review", "monitor"}:
        return "not_mechanically_evaluable"
    if normalized != "tighten_rule":
        return "not_evaluable"
    if parse_bounded_scope(scope):
        return "evaluable"
    return "not_evaluable"


def match_scope_mask(
    frame: pd.DataFrame,
    constraints: dict[str, str],
    semantics: str,
) -> pd.Series:
    if not constraints:
        return pd.Series(False, index=frame.index)
    masks: list[pd.Series] = []
    for name, column, _pattern in SCOPE_PATTERNS:
        if name in constraints:
            masks.append(frame[column].astype(str) == constraints[name])
    if not masks:
        return pd.Series(False, index=frame.index)
    combined = masks[0]
    for mask in masks[1:]:
        combined = combined & mask if semantics == "and" else combined | mask
    return combined


def _summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"transaction_count": 0, "total_amount": 0.0}
    return {
        "transaction_count": int(len(frame)),
        "total_amount": json_amount(frame["amount"].fillna(0).sum()),
    }


def _contains_forbidden_keys(payload: Any) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(token == lowered or token in lowered.replace("-", "_") for token in FORBIDDEN_IMPACT_KEYS):
                found.append(str(key))
            found.extend(_contains_forbidden_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_contains_forbidden_keys(item))
    return found


def evaluate_heldout_intervention() -> dict[str, Any]:
    meta = json.loads(HELDOUT_META_PATH.read_text(encoding="utf-8"))
    seed = int(meta["seed"])
    if seed != EVALUATION_SEED:
        raise ValueError(f"Intervention evaluation requires held-out seed {EVALUATION_SEED}, got {seed}")
    if not INVESTIGATION_METRICS_PATH.is_file():
        raise FileNotFoundError("Step 4 investigation_metrics.json is required and must not be regenerated here")

    investigation = json.loads(INVESTIGATION_METRICS_PATH.read_text(encoding="utf-8"))
    transactions = load_exposure_transactions()
    if "event_type" in transactions.columns or "fraud_label" in transactions.columns:
        raise ValueError("Intervention working frame must not carry event_type or fraud_label")
    labels, unassigned = label_transaction_hours(transactions["timestamp"])
    transactions = transactions.assign(ground_truth=labels)

    action_counts = {"tighten_rule": 0, "review": 0, "monitor": 0, "other": 0}
    cases: list[dict[str, Any]] = []
    affected_and = pd.Series(False, index=transactions.index)
    affected_or = pd.Series(False, index=transactions.index)
    applicable_windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    for case in investigation.get("cases") or []:
        action = case.get("recommended_action") or {}
        action_type = str(action.get("type") or "")
        scope = str(action.get("scope") or "")
        action_counts[action_type if action_type in action_counts else "other"] += 1
        expected = expected_investigation_verdict(case["window_start"], case["window_end"])
        if expected != LABEL_COORDINATED and expected != "coordinated_abuse":
            continue
        status = classify_recommendation(action_type, scope)
        constraints = parse_bounded_scope(scope) if status == "evaluable" else {}
        record: dict[str, Any] = {
            "spike_id": case["spike_id"],
            "window_start": case["window_start"],
            "window_end": case["window_end"],
            "calendar_expected": expected,
            "investigator_verdict": case.get("actual_verdict"),
            "action_type": action_type,
            "scope_text": scope,
            "parsed_scope": constraints,
            "evaluability": status,
        }
        if status != "evaluable":
            cases.append(record)
            continue
        window_mask = half_open_mask(transactions["timestamp"], case["window_start"], case["window_end"])
        and_mask = window_mask & match_scope_mask(transactions, constraints, "and")
        or_mask = window_mask & match_scope_mask(transactions, constraints, "or")
        affected_and = affected_and | and_mask
        affected_or = affected_or | or_mask
        applicable_windows.append((pd.Timestamp(case["window_start"]), pd.Timestamp(case["window_end"])))
        window_txs = transactions.loc[window_mask]
        record.update(
            {
                "matching_semantics": "AND of parsed entity dimensions inside the spike window (narrowest)",
                "alternative_or_semantics": "OR of parsed entity dimensions inside the spike window",
                "window": _summary(window_txs),
                "window_coordinated": _summary(window_txs.loc[window_txs["ground_truth"] == LABEL_COORDINATED]),
                "hypothetically_affected_and": _summary(transactions.loc[and_mask]),
                "hypothetically_affected_or": _summary(transactions.loc[or_mask]),
            }
        )
        cases.append(record)

    applicable_mask = pd.Series(False, index=transactions.index)
    for start, end in applicable_windows:
        applicable_mask = applicable_mask | half_open_mask(transactions["timestamp"], start, end)
    applicable = transactions.loc[applicable_mask]
    applicable_coord = applicable.loc[applicable["ground_truth"] == LABEL_COORDINATED]
    hit = transactions.loc[affected_and]
    hit_coord = hit.loc[hit["ground_truth"] == LABEL_COORDINATED]
    hit_festive = hit.loc[hit["ground_truth"] == LABEL_FESTIVE]
    hit_background = hit.loc[hit["ground_truth"] == LABEL_BACKGROUND]
    all_festive = transactions.loc[transactions["ground_truth"] == LABEL_FESTIVE]

    overall = _summary(hit)
    coordinated = _summary(hit_coord)
    festive = _summary(hit_festive)
    background = _summary(hit_background)
    window_coord = _summary(applicable_coord)

    precision_tx = json_number(safe_divide(coordinated["transaction_count"], overall["transaction_count"]))
    precision_amount = json_number(safe_divide(coordinated["total_amount"], overall["total_amount"]))
    recall_tx = json_number(safe_divide(coordinated["transaction_count"], window_coord["transaction_count"]))
    recall_amount = json_number(safe_divide(coordinated["total_amount"], window_coord["total_amount"]))

    evaluable_n = sum(1 for item in cases if item["evaluability"] == "evaluable")
    report: dict[str, Any] = {
        "evaluation_unit": "hypothetically affected held-out transaction inside a recommended spike window",
        "heldout_seed": seed,
        "label": "HYPOTHETICAL / SIMULATION ONLY",
        "claim": "hypothetically_affected_observed_activity",
        "not_calculated": list(FORBIDDEN_IMPACT_KEYS),
        "counterfactual": {
            "status": "hypothetical_simulation_only",
            "action_type": "tighten_rule",
            "temporal_scope": "window_start <= timestamp < window_end for each objectively coordinated spike with an evaluable recommendation",
            "matching_semantics": "AND of parsed device/subnet/SKU dimensions (narrowest interpretation). OR is computed only as an explicit alternative and is not the reported metric.",
            "scope": {
                "source": "existing Step 4 investigation recommended_action.scope",
                "entity_dimensions": ["device", "subnet", "sku"],
                "evaluable_interventions": evaluable_n,
                "per_spike": [
                    {
                        "spike_id": item["spike_id"],
                        "window_start": item["window_start"],
                        "window_end": item["window_end"],
                        "parsed_scope": item["parsed_scope"],
                    }
                    for item in cases
                    if item["evaluability"] == "evaluable"
                ],
            },
        },
        "action_evaluability": {
            "tighten_rule": "evaluable when the existing scope names at least one device, subnet, or SKU",
            "review": "not_mechanically_evaluable",
            "monitor": "not_mechanically_evaluable",
            "counts": action_counts,
            "objectively_coordinated_spikes": len(cases),
            "evaluable": evaluable_n,
            "not_evaluable": sum(1 for item in cases if item["evaluability"] == "not_evaluable"),
            "not_mechanically_evaluable": sum(
                1 for item in cases if item["evaluability"] == "not_mechanically_evaluable"
            ),
        },
        "overall": {
            "terminology": "hypothetically affected",
            **overall,
        },
        "coordinated_abuse": {
            "applicable_window": window_coord,
            "hypothetically_affected": coordinated,
            "transaction_coverage_rate": recall_tx,
            "amount_coverage_rate": recall_amount,
        },
        "collateral": {
            "legitimate_festive": festive,
            "background": background,
            "non_coordinated": _summary(
                hit.loc[hit["ground_truth"] != LABEL_COORDINATED]
            ),
        },
        "metrics": {
            "precision_tx": precision_tx,
            "precision_amount": precision_amount,
            "recall_tx": recall_tx,
            "recall_amount": recall_amount,
            "definition": {
                "precision": "coordinated hypothetically affected / all hypothetically affected",
                "recall": "coordinated hypothetically affected / coordinated transactions in applicable intervention windows",
            },
        },
        "alternative_or_semantics": {
            "note": "Wider match. Not the official counterfactual.",
            **_summary(transactions.loc[affected_or]),
        },
        "festive_safety": {
            "entire_festive_period_in_scope": bool(
                len(all_festive) > 0 and festive["transaction_count"] == int(len(all_festive))
            ),
            "festive_transactions_in_heldout_world": int(len(all_festive)),
            "festive_transactions_hypothetically_affected": festive["transaction_count"],
            "festive_share_of_all_festive_transactions": json_number(
                safe_divide(festive["transaction_count"], int(len(all_festive)))
            ),
        },
        "cases": cases,
        "ground_truth": {
            "source": "Step 3 scenario calendars via transaction hour",
            "not_used": [
                "investigation verdict as ground truth",
                "detector spike_type as ground truth",
                "event_type",
                "fraud_label as live evidence",
            ],
            "unassigned_timestamps": unassigned,
        },
        "limitations": [
            "HYPOTHETICAL / SIMULATION ONLY. No intervention was executed.",
            "The dataset has no historical intervention logs; this constructs an affected set from existing recommendations.",
            "Matching uses AND of parsed entity dimensions (narrowest). OR is reported only as an alternative.",
            "A matching transaction is hypothetically affected, not blocked, prevented, or saved.",
            "review and monitor have no deterministic intervention effect and are not mechanically evaluable.",
            "Investigation verdicts are the policy source only; calendar labels remain ground truth.",
            "No payment, authorization, or settlement outcome is inferred.",
        ],
        "data_quality": {
            "heldout_meta_transactions": int(meta["n_transactions"]),
            "loaded_transactions": int(len(transactions)),
            "heldout_spikes": int(pd.read_csv(HELDOUT_SPIKES_CSV_PATH).shape[0]),
            "heldout_hourly_windows": int(pd.read_csv(HELDOUT_WINDOWS_PATH).shape[0]),
        },
    }
    forbidden = _contains_forbidden_keys(report)
    if forbidden:
        raise ValueError(f"Intervention report must not include impact-claim keys: {forbidden}")
    return report


def write_intervention_report(
    report: dict[str, Any] | None = None,
    output_path: Path | None = None,
) -> Path:
    payload = report if report is not None else evaluate_heldout_intervention()
    dest = output_path or HELDOUT_INTERVENTION_PATH
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def write_intervention_markdown(report: dict[str, Any], output_path: Path) -> Path:
    metrics = report["metrics"]
    overall = report["overall"]
    coord = report["coordinated_abuse"]
    collateral = report["collateral"]
    lines = [
        "# Phase 7 Step 6 — Intervention counterfactual",
        "",
        "**HYPOTHETICAL / SIMULATION ONLY.** Observed activity inside an existing bounded `tighten_rule` scope. Not blocked, saved, or prevented.",
        "",
        f"- Action: `{report['counterfactual']['action_type']}`",
        f"- Temporal scope: {report['counterfactual']['temporal_scope']}",
        f"- Matching: {report['counterfactual']['matching_semantics']}",
        f"- Hypothetically affected: {overall['transaction_count']} txs / {overall['total_amount']}",
        f"- Coordinated coverage: tx {coord['transaction_coverage_rate']} / amount {coord['amount_coverage_rate']}",
        f"- Precision: tx {metrics['precision_tx']} / amount {metrics['precision_amount']}",
        f"- Festive collateral: {collateral['legitimate_festive']['transaction_count']} txs / {collateral['legitimate_festive']['total_amount']}",
        f"- Background collateral: {collateral['background']['transaction_count']} txs / {collateral['background']['total_amount']}",
        "",
        "review / monitor: not mechanically evaluable.",
        "",
        "Run: `python -m evaluation.intervention`",
        "",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    report = evaluate_heldout_intervention()
    json_path = write_intervention_report(report)
    md_path = write_intervention_markdown(
        report,
        Path(__file__).resolve().parent.parent / "docs" / "phase-7-intervention.md",
    )
    printable = {key: value for key, value in report.items() if key != "cases"}
    print(json.dumps(printable, indent=2))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
