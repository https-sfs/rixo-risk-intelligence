"""Methodology-only evaluation for the January 2026 collection.

This adapter does not emit an independent fraud prediction, so classifier
metrics are not calculated. is_fraud is delayed ground truth only.
Source CNN-LSTM outputs are never treated as our scores.
"""

from __future__ import annotations

from typing import Any

from evaluation.recent_data.mapper import (
    AMOUNT_CURRENCY,
    DATASET_NAME,
    SOURCE_MODEL_OUTPUTS,
    WORLD,
    ZENODO_DOI,
    ZENODO_URL,
)


def build_evaluation() -> dict[str, Any]:
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "amount_currency": AMOUNT_CURRENCY,
        "methodology": {
            "collection": "January 2026 rows with test_date present",
            "live_inputs": ["hourly transaction_count", "hourly amount_usd"],
            "delayed_ground_truth": "is_fraud overlay only; never a live detector input",
            "independent_predictive_score": False,
            "source_model_used_as_our_prediction": False,
            "classifier_metrics_calculated": False,
            "reason": (
                "This adapter does not emit an independent fraud score that can be "
                "compared with is_fraud. Source CNN-LSTM probability is not our "
                "prediction, so precision, recall, F1, and PR-AUC are not calculated."
            ),
            "source_model_outputs_excluded": list(SOURCE_MODEL_OUTPUTS),
        },
        "not_calculated": [
            "precision",
            "recall",
            "f1",
            "pr_auc",
            "source CNN-LSTM probability as our prediction",
        ],
        "attribution": {
            "zenodo": ZENODO_URL,
            "doi": ZENODO_DOI,
            "license": "CC BY 4.0",
        },
        "notes": [
            "Historical public research data, not our live production traffic.",
            "Hour-level volume and amount outliers are descriptive signals, not fraud verdicts.",
        ],
    }
