"""Controlled synthetic counterfactual outcome measurement.

Receives an already-selected synthetic window and an already-selected bounded
action. Evaluates the hypothetical effect on an in-memory copy.

Does not choose, approve, or execute an action. Does not call Razorpay.
Does not mutate the source dataset or ActionStore.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from evaluation.exposure import half_open_mask, json_amount
from evaluation.intelligence import BYOD_WORLD, IEEE_WORLD, JANUARY_WORLD, SYNTHETIC_WORLD
from evaluation.intervention import (
    FORBIDDEN_IMPACT_KEYS,
    classify_recommendation,
    match_scope_mask,
    parse_bounded_scope,
)
from evaluation.metrics import json_number, safe_divide
from evaluation.paths import BASELINE_META_PATH, BASELINE_SEED, BASELINE_TRANSACTIONS_PATH
from evaluation.scorecard import IEEE_INTERVENTION_LIMITATION
from tools.load import load_detected_spike

COUNTERFACTUAL_COLUMNS = (
    "transaction_id",
    "timestamp",
    "device_id",
    "ip_subnet",
    "sku_id",
    "amount",
    "fraud_label",
)

LABEL = "CONTROLLED SYNTHETIC COUNTERFACTUAL"
OUTCOME_LABEL = "SIMULATION-ONLY OUTCOME"

IEEE_WORLDS = frozenset({IEEE_WORLD, "IEEE-CIS", "REAL PUBLIC DATA / IEEE-CIS"})
FOREIGN_WORLDS = frozenset({IEEE_WORLD, JANUARY_WORLD, BYOD_WORLD}) | IEEE_WORLDS


def ieee_intervention_limitation() -> dict[str, Any]:
    return {
        "world": IEEE_WORLD,
        "available": False,
        "label": "NOT MEASURABLE",
        "genuine_before_after": False,
        "reason": IEEE_INTERVENTION_LIMITATION,
        "not_production_performance": True,
        "not_money_saved": True,
        "synthetic_counterfactual_metrics": None,
    }


def _contains_forbidden_keys(payload: Any) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower().replace("-", "_")
            if lowered in FORBIDDEN_IMPACT_KEYS or lowered in {
                "money_saved",
                "roi",
                "production_performance",
            }:
                found.append(str(key))
            found.extend(_contains_forbidden_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_contains_forbidden_keys(item))
    return found


def _load_demo_copy() -> pd.DataFrame:
    payload = json.loads(BASELINE_META_PATH.read_text(encoding="utf-8"))
    if int(payload["seed"]) != BASELINE_SEED:
        raise ValueError(f"Synthetic counterfactual requires demo seed {BASELINE_SEED}")
    frame = pd.read_csv(BASELINE_TRANSACTIONS_PATH)
    missing = [column for column in COUNTERFACTUAL_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Synthetic ledger missing columns required for counterfactual: {missing}")
    columns = list(COUNTERFACTUAL_COLUMNS)
    if "event_type" in frame.columns:
        columns.append("event_type")
    out = frame.loc[:, columns].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
    out["fraud_label"] = pd.to_numeric(out["fraud_label"], errors="coerce").fillna(0).astype(int)
    return out


def _ids(frame: pd.DataFrame) -> list[str]:
    return sorted(str(value) for value in frame["transaction_id"].tolist())


def _window_stats(frame: pd.DataFrame) -> dict[str, Any]:
    fraud = frame.loc[frame["fraud_label"] == 1]
    legit = frame.loc[frame["fraud_label"] == 0]
    count = int(len(frame))
    fraud_count = int(len(fraud))
    return {
        "transaction_count": count,
        "fraud_count": fraud_count,
        "legitimate_count": int(len(legit)),
        "fraud_rate": json_number(safe_divide(fraud_count, count)),
        "amount_sum": json_amount(frame["amount"].fillna(0).sum()) if count else 0.0,
        "fraud_amount": json_amount(fraud["amount"].fillna(0).sum()) if fraud_count else 0.0,
    }


def evaluate_synthetic_counterfactual(
    *,
    spike_id: str,
    action_type: str,
    scope: str,
    world: str = SYNTHETIC_WORLD,
) -> dict[str, Any]:
    """Measure a hypothetical bounded intervention on a seed-42 window copy."""
    requested_world = str(world or "").strip()
    if requested_world in FOREIGN_WORLDS or requested_world != SYNTHETIC_WORLD:
        raise ValueError(
            IEEE_INTERVENTION_LIMITATION
            if requested_world in IEEE_WORLDS or requested_world.startswith("REAL")
            else (
                "Controlled synthetic counterfactual is available only in SYNTHETIC SCENARIO. "
                "Worlds are not mixed."
            )
        )
    if str(spike_id).startswith("rda-") or str(spike_id).startswith("rct-"):
        raise ValueError(IEEE_INTERVENTION_LIMITATION if str(spike_id).startswith("rda-") else "January 2026 cannot receive synthetic counterfactual outcome metrics.")

    spike = load_detected_spike(spike_id)
    transactions = _load_demo_copy()
    source_rows = int(len(transactions))
    window_mask = half_open_mask(transactions["timestamp"], spike["window_start"], spike["window_end"])
    window = transactions.loc[window_mask].copy()
    baseline = _window_stats(window)

    status = classify_recommendation(action_type, scope)
    constraints = parse_bounded_scope(scope) if status == "evaluable" else {}
    target_mask = pd.Series(False, index=transactions.index)
    if status == "evaluable":
        target_mask = window_mask & match_scope_mask(transactions, constraints, "and")

    targeted = transactions.loc[target_mask].copy()
    targeted_fraud = targeted.loc[targeted["fraud_label"] == 1]
    targeted_legit = targeted.loc[targeted["fraud_label"] == 0]
    residual = window.loc[~window.index.isin(targeted.index)].copy()
    after = _window_stats(residual)

    capture = json_number(safe_divide(int(len(targeted_fraud)), baseline["fraud_count"]))
    targeted_fpr = json_number(safe_divide(int(len(targeted_legit)), int(len(targeted))))
    amount_before = baseline["fraud_amount"]
    amount_targeted = json_amount(targeted_fraud["amount"].fillna(0).sum()) if len(targeted_fraud) else 0.0
    amount_remaining = json_amount(amount_before - amount_targeted)

    event_breakdown: dict[str, Any] | None = None
    if "event_type" in targeted.columns:
        event_breakdown = {
            "methodology": (
                "event_type is injected synthetic scenario type. It is not a live detector input. "
                "Reported only because the seed-42 ledger includes the column."
            ),
            "targeted": targeted["event_type"].value_counts().to_dict() if len(targeted) else {},
        }

    payload: dict[str, Any] = {
        "label": LABEL,
        "outcome_label": OUTCOME_LABEL,
        "world": SYNTHETIC_WORLD,
        "not_production_performance": True,
        "not_money_saved": True,
        "does_not_choose_action": True,
        "does_not_approve": True,
        "does_not_execute": True,
        "does_not_call_razorpay": True,
        "does_not_mutate_source_dataset": True,
        "does_not_mutate_governance": True,
        "source_transaction_count_unchanged": source_rows,
        "case": {
            "spike_id": spike_id,
            "window_start": pd.Timestamp(spike["window_start"]).isoformat(timespec="seconds"),
            "window_end": pd.Timestamp(spike["window_end"]).isoformat(timespec="seconds"),
            "detector_type": spike["spike_type"],
        },
        "selected_action": {
            "type": action_type,
            "scope": scope,
            "parsed_scope": constraints,
            "evaluability": status,
            "matching_semantics": "AND of parsed device/subnet/SKU dimensions inside the spike window",
            "temporal_scope": "window_start <= timestamp < window_end",
            "received_already_selected": True,
        },
        "methodology": {
            "ground_truth": {
                "field": "fraud_label",
                "role": "delayed synthetic transaction ground truth for evaluation only",
                "not_used_as_live_detector_input": True,
                "source": "data/transactions.csv",
            },
            "intervention": (
                "Hypothetically mark matching rows as affected on an in-memory copy. "
                "Residual metrics are the window rows that would remain untargeted."
            ),
            "amount_field": "simulated_fraud_amount_targeted_protected",
            "amount_field_is_not": ["money_saved", "ROI", "production fraud reduction"],
        },
        "baseline": {
            "transaction_count": baseline["transaction_count"],
            "fraud_count": baseline["fraud_count"],
            "legitimate_count": baseline["legitimate_count"],
            "fraud_rate": baseline["fraud_rate"],
            "amount_exposure_before": amount_before,
            "methodology": "All seed-42 transactions in the selected half-open spike window.",
            "source": "data/transactions.csv in-memory copy",
        },
        "targeted": {
            "transaction_count": int(len(targeted)),
            "fraud_transactions_targeted": int(len(targeted_fraud)),
            "legitimate_transactions_targeted": int(len(targeted_legit)),
            "fraud_exposure_targeted_protected": int(len(targeted_fraud)),
            "simulated_fraud_amount_targeted_protected": amount_targeted,
            "amount_exposure_targeted": amount_targeted,
            "protected_transaction_ids": _ids(targeted_fraud),
            "legitimate_transactions_that_would_be_affected": _ids(targeted_legit),
            "false_positive_rate_among_targeted": targeted_fpr,
            "fraud_recall_capture_rate": capture,
            "event_type_breakdown": event_breakdown,
        }
        if status == "evaluable"
        else {
            "evaluability": status,
            "reason": (
                "review, monitor, and unscoped tighten_rule have no deterministic "
                "bounded intervention effect."
            ),
        },
        "after": {
            "simulated_residual_fraud_count": after["fraud_count"],
            "simulated_residual_fraud_rate": after["fraud_rate"],
            "simulated_residual_transaction_count": after["transaction_count"],
            "amount_exposure_remaining": amount_remaining,
            "methodology": "Window rows not hypothetically targeted. Source CSV is unchanged.",
        }
        if status == "evaluable"
        else None,
        "delta": {
            "fraud_count": after["fraud_count"] - baseline["fraud_count"],
            "fraud_rate": json_number(
                None
                if after["fraud_rate"] is None or baseline["fraud_rate"] is None
                else after["fraud_rate"] - baseline["fraud_rate"]
            ),
            "amount_exposure": json_amount(amount_remaining - amount_before),
            "note": "Negative values are simulated residual reduction, not money saved.",
        }
        if status == "evaluable"
        else None,
        "limitations": [
            LABEL + ". " + OUTCOME_LABEL + ".",
            "No intervention was executed. Razorpay was not called.",
            "The source dataset was not mutated and the counterfactual is not a payment event.",
            "This is not production fraud reduction, money saved, or ROI.",
            IEEE_INTERVENTION_LIMITATION,
        ],
    }
    forbidden = _contains_forbidden_keys(payload)
    if forbidden:
        raise ValueError(f"Counterfactual must not include impact-claim keys: {forbidden}")
    if int(len(transactions)) != source_rows:
        raise RuntimeError("Counterfactual working copy changed the loaded row count")
    return payload
