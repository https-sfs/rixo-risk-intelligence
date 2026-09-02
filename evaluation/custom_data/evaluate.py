"""User-provided ground-truth metrics. Labels are never detector inputs."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from evaluation.custom_data import USER_LABEL_PROVENANCE, USER_MODEL_PROVENANCE, WORLD
from evaluation.metrics import json_number
from models.ieee_fraud.evaluate import evaluate_scores


def _coerce_labels(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.astype(int)
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().mean() >= 0.8:
        return numeric
    normalized = series.astype(str).str.strip().str.lower()
    mapped = normalized.map(
        {
            "1": 1,
            "true": 1,
            "fraud": 1,
            "yes": 1,
            "0": 0,
            "false": 0,
            "legit": 0,
            "no": 0,
            "genuine": 0,
        }
    )
    return pd.to_numeric(mapped, errors="coerce")


def evaluate_user_labels(
    mapped: pd.DataFrame,
    scored: dict[str, Any] | None,
) -> dict[str, Any]:
    if "fraud_label" not in mapped.columns:
        return {
            "world": WORLD,
            "available": False,
            "reason": "No user-provided fraud label was mapped.",
            "labels_invented": False,
            "used_as_detector_input": False,
        }
    labels = _coerce_labels(mapped["fraud_label"])
    usable = labels.dropna()
    if usable.empty:
        return {
            "world": WORLD,
            "available": False,
            "reason": "The mapped fraud-label column could not be interpreted as binary labels.",
            "labels_invented": False,
            "used_as_detector_input": False,
        }
    fraud_count = int((usable == 1).sum())
    payload: dict[str, Any] = {
        "world": WORLD,
        "available": True,
        "provenance": USER_LABEL_PROVENANCE,
        "rows_labelled": int(usable.size),
        "fraud_count": fraud_count,
        "fraud_rate": json_number(fraud_count / usable.size if usable.size else None),
        "classifier_metrics_calculated": False,
        "labels_invented": False,
        "used_as_detector_input": False,
        "retrained_on_upload": False,
    }
    if not scored or scored.get("scores") is None:
        payload["reason"] = (
            "User-provided labels support a fraud rate only. "
            "Precision, recall, F1, PR-AUC, ROC-AUC, confusion, and calibration "
            "require a genuine supervised score from a compatible IEEE feature contract."
        )
        return payload
    scores = scored["scores"].set_index("row_index")["fraud_risk_score"]
    aligned = pd.DataFrame({"label": labels, "score": scores}).dropna()
    if aligned.empty or aligned["label"].nunique() < 2:
        payload["reason"] = (
            "Labels and scores could not be aligned with both classes present, "
            "so ranking and threshold metrics are not calculated."
        )
        return payload
    metrics = evaluate_scores(
        np.asarray(aligned["label"], dtype=float),
        np.asarray(aligned["score"], dtype=float),
        threshold=float(scored["threshold"]),
    )
    payload.update(
        {
            "classifier_metrics_calculated": True,
            "score_provenance": USER_MODEL_PROVENANCE,
            "threshold_source": "ieee_validation_frozen",
            "ranking": metrics["ranking"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
            "confusion": metrics["confusion"],
            "calibration": {
                "brier": metrics.get("calibration", {}).get("brier"),
                "bins": metrics.get("calibration", {}).get("bins"),
            },
            "reason": (
                "Metrics compare USER-PROVIDED GROUND TRUTH with "
                "MODEL PREDICTION · USER DATASET at the frozen IEEE operating threshold. "
                "This is not a live production detection claim and the model was not retrained."
            ),
        }
    )
    return payload


def evaluate_label_arrays(
    labels: np.ndarray | None,
    scores: np.ndarray | None,
    threshold: float | None,
) -> dict[str, Any]:
    if labels is None or not np.isfinite(labels).any():
        return {
            "world": WORLD,
            "available": False,
            "reason": "No user-provided fraud label was mapped.",
            "labels_invented": False,
            "used_as_detector_input": False,
        }
    usable = labels[np.isfinite(labels)]
    fraud_count = int((usable == 1).sum())
    payload: dict[str, Any] = {
        "world": WORLD,
        "available": True,
        "provenance": USER_LABEL_PROVENANCE,
        "rows_labelled": int(usable.size),
        "fraud_count": fraud_count,
        "fraud_rate": json_number(fraud_count / usable.size if usable.size else None),
        "classifier_metrics_calculated": False,
        "labels_invented": False,
        "used_as_detector_input": False,
        "retrained_on_upload": False,
    }
    if scores is None or threshold is None:
        payload["reason"] = (
            "User-provided labels support a fraud rate only. "
            "Precision, recall, F1, PR-AUC, ROC-AUC, confusion, and calibration "
            "require a genuine supervised score from a compatible IEEE feature contract."
        )
        return payload
    aligned_labels = []
    aligned_scores = []
    for label, score in zip(labels, scores, strict=False):
        if np.isfinite(label) and np.isfinite(score):
            aligned_labels.append(float(label))
            aligned_scores.append(float(score))
    if len(set(aligned_labels)) < 2:
        payload["reason"] = (
            "Labels and scores could not be aligned with both classes present, "
            "so ranking and threshold metrics are not calculated."
        )
        return payload
    metrics = evaluate_scores(
        np.asarray(aligned_labels, dtype=float),
        np.asarray(aligned_scores, dtype=float),
        threshold=float(threshold),
    )
    payload.update(
        {
            "classifier_metrics_calculated": True,
            "score_provenance": USER_MODEL_PROVENANCE,
            "threshold_source": "ieee_validation_frozen",
            "ranking": metrics["ranking"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
            "confusion": metrics["confusion"],
            "calibration": {
                "brier": metrics.get("calibration", {}).get("brier"),
                "bins": metrics.get("calibration", {}).get("bins"),
            },
            "reason": (
                "Metrics compare USER-PROVIDED GROUND TRUTH with "
                "MODEL PREDICTION · USER DATASET at the frozen IEEE operating threshold. "
                "This is not a live production detection claim and the model was not retrained."
            ),
        }
    )
    return payload
