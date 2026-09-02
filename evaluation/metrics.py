"""Binary and multiclass detection scores. No dataset I/O."""

from __future__ import annotations

from typing import Any

import numpy as np


def safe_divide(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def f1_score(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    return safe_divide(2 * precision * recall, precision + recall)


def binary_counts(
    truths: list[str],
    predictions: list[str],
    positive: str,
) -> dict[str, int]:
    tp = fp = tn = fn = 0
    for truth, prediction in zip(truths, predictions, strict=True):
        actual = truth == positive
        predicted = prediction == positive
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif (not predicted) and actual:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def binary_scores(counts: dict[str, int]) -> dict[str, float | None]:
    precision = safe_divide(counts["tp"], counts["tp"] + counts["fp"])
    recall = safe_divide(counts["tp"], counts["tp"] + counts["fn"])
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1_score(precision, recall),
    }


def confusion_matrix(
    truths: list[str],
    predictions: list[str],
    labels: tuple[str, ...],
) -> dict[str, dict[str, int]]:
    matrix = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    for truth, prediction in zip(truths, predictions, strict=True):
        matrix[truth][prediction] += 1
    return matrix


def class_breakdown(
    truths: list[str],
    predictions: list[str],
    labels: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    breakdown: dict[str, dict[str, Any]] = {}
    for label in labels:
        counts = binary_counts(truths, predictions, label)
        breakdown[label] = {**counts, **binary_scores(counts)}
    return breakdown


def json_number(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def ranking_scores(y_true: np.ndarray, y_score: np.ndarray) -> dict[str, float | None]:
    """PR-AUC and ROC-AUC for an independent probability score vs binary labels."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    labels = np.asarray(y_true, dtype=float)
    scores = np.asarray(y_score, dtype=float)
    mask = np.isfinite(labels) & np.isfinite(scores)
    labels = labels[mask]
    scores = scores[mask]
    if labels.size == 0 or len(np.unique(labels)) < 2:
        return {"pr_auc": None, "roc_auc": None}
    return {
        "pr_auc": float(average_precision_score(labels, scores)),
        "roc_auc": float(roc_auc_score(labels, scores)),
    }


def threshold_sweep(
    y_true: np.ndarray,
    y_score: np.ndarray,
    thresholds: list[float] | None = None,
) -> list[dict[str, Any]]:
    labels = np.asarray(y_true, dtype=float)
    scores = np.asarray(y_score, dtype=float)
    if thresholds is None:
        thresholds = [0.01, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5]
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        predicted = (scores >= threshold).astype(int)
        truths = ["fraud" if value == 1 else "legit" for value in labels]
        preds = ["fraud" if value == 1 else "legit" for value in predicted]
        counts = binary_counts(truths, preds, "fraud")
        rows.append({"threshold": threshold, **counts, **binary_scores(counts)})
    return rows


def choose_operating_threshold(
    sweep: list[dict[str, Any]],
    rule: str | None = None,
) -> dict[str, Any]:
    scored = [row for row in sweep if row.get("f1") is not None]
    selected_rule = rule or (
        "maximum F1 on the validation set "
        "(validation-selected operating point; not an untouched test result)"
    )
    if not scored:
        return {"threshold": 0.5, "rule": "default 0.5; no F1 available"}
    best = max(scored, key=lambda row: (row["f1"], row.get("recall") or 0.0))
    return {
        "threshold": best["threshold"],
        "f1": best["f1"],
        "precision": best["precision"],
        "recall": best["recall"],
        "rule": selected_rule,
    }


def calibration_report(
    y_true: np.ndarray,
    y_score: np.ndarray,
    bins: int = 10,
) -> dict[str, Any]:
    from sklearn.metrics import brier_score_loss

    labels = np.asarray(y_true, dtype=float)
    scores = np.clip(np.asarray(y_score, dtype=float), 0.0, 1.0)
    if labels.size == 0:
        return {"brier": None, "bins": []}
    edges = np.linspace(0.0, 1.0, bins + 1)
    reliability: list[dict[str, Any]] = []
    for index in range(bins):
        low, high = edges[index], edges[index + 1]
        if index == bins - 1:
            mask = (scores >= low) & (scores <= high)
        else:
            mask = (scores >= low) & (scores < high)
        count = int(mask.sum())
        reliability.append(
            {
                "low": float(low),
                "high": float(high),
                "count": count,
                "mean_score": float(scores[mask].mean()) if count else None,
                "empirical_rate": float(labels[mask].mean()) if count else None,
            }
        )
    return {
        "brier": float(brier_score_loss(labels, scores)),
        "bins": reliability,
    }
