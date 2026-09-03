"""Hour-level IEEE-CIS evaluation. isFraud is used only as delayed ground truth.

There is no trained ML model in this repository. These metrics evaluate the
label-free heuristic detector against high-fraud-rate relative hours.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from evaluation.metrics import binary_counts, binary_scores
from evaluation.real_data.detect import score_hourly
from evaluation.real_data.mapper import AMOUNT_CURRENCY, DATASET_NAME, WORLD


def _pr_not_applicable() -> dict[str, Any]:
    return {
        "calculated": False,
        "reason": (
            "No trained scoring model exists. PR-AUC is not reported for the "
            "deterministic heuristic detector."
        ),
    }


def evaluate_hourly_detector(hourly: pd.DataFrame, split: float = 0.7) -> dict[str, Any]:
    if hourly.empty:
        raise ValueError("hourly metrics are empty")
    scored = score_hourly(hourly).sort_values("relative_hour_bucket")
    if "labelled_fraud_rate" not in scored.columns:
        raise ValueError("Evaluation requires labelled_fraud_rate as delayed ground truth.")

    cutoff_index = max(int(len(scored) * split), 1)
    early = scored.iloc[:cutoff_index]
    late = scored.iloc[cutoff_index:]
    early_rate = pd.to_numeric(early["labelled_fraud_rate"], errors="coerce")
    threshold = float(early_rate.mean() + 2 * early_rate.std(ddof=0)) if early_rate.notna().any() else 1.0

    def _labels(frame: pd.DataFrame) -> list[str]:
        rates = pd.to_numeric(frame["labelled_fraud_rate"], errors="coerce").fillna(0.0)
        return ["high_fraud_hour" if rate >= threshold else "ordinary_hour" for rate in rates]

    def _preds(frame: pd.DataFrame) -> list[str]:
        return ["high_fraud_hour" if flag else "ordinary_hour" for flag in frame["is_anomaly"]]

    late_truth = _labels(late)
    late_pred = _preds(late)
    counts = binary_counts(late_truth, late_pred, "high_fraud_hour")
    scores = binary_scores(counts)
    early_counts = binary_counts(_labels(early), _preds(early), "high_fraud_hour")
    early_scores = binary_scores(early_counts)

    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "amount_currency": AMOUNT_CURRENCY,
        "methodology": {
            "unit": "relative_hour_bucket",
            "live_inputs": [
                "transaction_count",
                "amount_usd",
                "product_top_share",
            ],
            "delayed_ground_truth": (
                "An evaluation-positive hour has labelled_fraud_rate >= "
                "early-period mean + 2 standard deviations. isFraud is not a live input."
            ),
            "split": (
                f"First {split:.0%} of relative-hour buckets are the reference window; "
                "the remainder is the temporal holdout."
            ),
            "not_a_trained_model": True,
            "synthetic_calendar_used": False,
        },
        "reference_window": {
            "hours": int(len(early)),
            "high_fraud_rate_threshold": threshold,
            "counts": early_counts,
            "scores": early_scores,
        },
        "temporal_holdout": {
            "hours": int(len(late)),
            "counts": counts,
            "precision": scores["precision"],
            "recall": scores["recall"],
            "f1": scores["f1"],
        },
        "pr_auc": _pr_not_applicable(),
        "signal_coverage": {
            "hours_scored": int(len(scored)),
            "hours_flagged_live": int(scored["is_anomaly"].sum()),
            "hours_with_fraud_label": int(scored["labelled_fraud_rate"].notna().sum()),
        },
        "notes": [
            "These scores evaluate hour-level heuristic flags, not a transaction classifier.",
            "Precision/recall can be low because elevated volume is not the same as elevated fraud.",
            "Do not present these numbers as model-training results.",
        ],
    }
