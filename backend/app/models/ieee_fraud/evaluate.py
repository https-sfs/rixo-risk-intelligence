"""Validation threshold selection and untouched test metrics. Target is isFraud only."""

from __future__ import annotations

from typing import Any

import numpy as np

from evaluation.metrics import (
    binary_counts,
    binary_scores,
    calibration_report,
    choose_operating_threshold,
    json_number,
    ranking_scores,
    threshold_sweep,
)
from models.ieee_fraud import AMOUNT_CURRENCY, DATASET_NAME, PROVENANCE, WORLD

VALIDATION_THRESHOLD_RULE = (
    "maximum F1 on the validation set "
    "(validation-selected operating point; not an untouched test result)"
)


def _confusion_from_scores(labels: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, Any]:
    predicted = (scores >= threshold).astype(int)
    truths = ["fraud" if value == 1 else "legit" for value in labels]
    preds = ["fraud" if value == 1 else "legit" for value in predicted]
    counts = binary_counts(truths, preds, "fraud")
    metrics = binary_scores(counts)
    return {
        "threshold": float(threshold),
        "precision": json_number(metrics["precision"]),
        "recall": json_number(metrics["recall"]),
        "f1": json_number(metrics["f1"]),
        "confusion": counts,
    }


def evaluate_scores(
    y_true: np.ndarray,
    y_score: np.ndarray,
    prevalence: float | None = None,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Score a single labelled fold. Pass threshold to freeze an operating point."""
    labels = np.asarray(y_true, dtype=float)
    scores = np.asarray(y_score, dtype=float)
    ranking = ranking_scores(labels, scores)
    sweep = threshold_sweep(labels, scores)
    if threshold is None:
        selected = choose_operating_threshold(sweep, rule=VALIDATION_THRESHOLD_RULE)
        frozen = float(selected["threshold"])
        threshold_source = "selected_on_this_set"
    else:
        frozen = float(threshold)
        selected = {
            "threshold": frozen,
            "rule": "frozen threshold supplied by caller",
        }
        threshold_source = "frozen"
    at_threshold = _confusion_from_scores(labels, scores, frozen)
    return {
        "n_rows": int(labels.size),
        "n_fraud": int((labels == 1).sum()),
        "prevalence": prevalence if prevalence is not None else (float(labels.mean()) if labels.size else None),
        "ranking": {
            "pr_auc": json_number(ranking["pr_auc"]),
            "roc_auc": json_number(ranking["roc_auc"]),
        },
        "threshold": frozen,
        "threshold_source": threshold_source,
        "precision": at_threshold["precision"],
        "recall": at_threshold["recall"],
        "f1": at_threshold["f1"],
        "confusion": at_threshold["confusion"],
        "selection": selected,
        "threshold_sweep": [
            {
                "threshold": row["threshold"],
                "precision": json_number(row["precision"]),
                "recall": json_number(row["recall"]),
                "f1": json_number(row["f1"]),
                "tp": row["tp"],
                "fp": row["fp"],
                "tn": row["tn"],
                "fn": row["fn"],
            }
            for row in sweep
        ],
        "calibration": calibration_report(labels, scores),
    }


def compose_evaluation(
    validation: dict[str, Any],
    test: dict[str, Any],
    split: dict[str, Any],
    feature_spec_payload: dict[str, Any],
    preprocessing: dict[str, Any],
    estimator: dict[str, Any],
) -> dict[str, Any]:
    frozen = float(validation["threshold"])
    test_at_frozen = {
        "threshold": frozen,
        "threshold_source": "validation_frozen",
        "untouched": True,
        "precision": test["precision"],
        "recall": test["recall"],
        "f1": test["f1"],
        "confusion": test["confusion"],
        "rule": (
            "Frozen validation-selected threshold; "
            "precision/recall/F1/confusion are the untouched temporal test set."
        ),
    }
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "amount_currency": AMOUNT_CURRENCY,
        "provenance": PROVENANCE,
        "target": "isFraud",
        "target_used_as_feature": False,
        "split": split,
        "preprocessing": preprocessing,
        "class_imbalance": {
            "method": "sklearn.utils.class_weight.compute_sample_weight('balanced')",
            "fitted_on": "train labels only",
        },
        "validation": {
            "role": "threshold_selection",
            "not_an_untouched_test_result": True,
            "n_rows": validation["n_rows"],
            "n_fraud": validation["n_fraud"],
            "prevalence": validation["prevalence"],
            "ranking": validation["ranking"],
            "threshold_selection": validation["selection"],
            "threshold": frozen,
            "precision": validation["precision"],
            "recall": validation["recall"],
            "f1": validation["f1"],
            "confusion": validation["confusion"],
            "threshold_sweep": validation["threshold_sweep"],
            "calibration": validation["calibration"],
        },
        "test": {
            "role": "untouched_final_evaluation",
            "untouched": True,
            "n_rows": test["n_rows"],
            "n_fraud": test["n_fraud"],
            "prevalence": test["prevalence"],
            "ranking": test["ranking"],
            **test_at_frozen,
            "calibration": test["calibration"],
        },
        "ranking": test["ranking"],
        "operating_point": test_at_frozen,
        "prevalence": test["prevalence"],
        "feature_spec": feature_spec_payload,
        "estimator": estimator,
        "notes": [
            "Scores are MODEL PREDICTION from an IEEE-CIS-trained classifier.",
            "isFraud is delayed ground truth for evaluation only and is never a feature.",
            "Categorical mappings were fit on the train fold only; unseen categories map to NaN.",
            "The operating threshold was selected on validation only, then frozen.",
            "PR-AUC, ROC-AUC, precision, recall, F1, confusion, and calibration under test "
            "are the untouched temporal test set.",
            "Validation F1 is a threshold-selection statistic, not an untouched test result.",
            "These metrics are historical IEEE-CIS test results, not production performance.",
        ],
    }
