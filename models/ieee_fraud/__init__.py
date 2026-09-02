"""Supervised IEEE-CIS fraud-risk model. Isolated from spike detectors and other worlds."""

from __future__ import annotations

from pathlib import Path

WORLD = "REAL PUBLIC DATA"
DATASET_NAME = "IEEE-CIS Fraud Detection"
PROVENANCE = "MODEL PREDICTION"
TARGET_COLUMN = "isFraud"
AMOUNT_CURRENCY = "USD"

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = REPO_ROOT / "data" / "real" / "model"
JOBLIB_NAME = "ieee_hgb.joblib"
FEATURE_SPEC_NAME = "feature_spec.json"
ENCODER_NAME = "encoder.json"
EVALUATION_NAME = "model_evaluation.json"
OVERLAY_NAME = "hour_risk_overlay.json"
BUNDLE_VERSION = 2
TRAIN_FRACTION = 0.7
VALIDATION_FRACTION = 0.1
TEST_FRACTION = 0.2

FORBIDDEN_FEATURES = frozenset(
    {
        "isFraud",
        "fraud_label",
        "fraud_probability",
        "risk_level",
        "confidence",
        "recommendation",
    }
)
