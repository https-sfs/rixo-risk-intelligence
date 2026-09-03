"""Transaction-level IEEE-CIS fraud-risk scores using persisted preprocessing."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from models.ieee_fraud import (
    BUNDLE_VERSION,
    DATASET_NAME,
    FORBIDDEN_FEATURES,
    PROVENANCE,
    WORLD,
)
from models.ieee_fraud.features import (
    AMOUNT_COLUMN,
    ELAPSED_COLUMN,
    ID_COLUMN,
    CategoricalEncoder,
    PredictSchemaError,
    assert_no_leakage,
    build_feature_frame,
    discover_feature_columns,
)

CORE_TRANSACTION_FIELDS = (AMOUNT_COLUMN, ELAPSED_COLUMN, "ProductCD", "card1")
MIN_CORE_FIELDS = 2
SYNTHETIC_ONLY_COLUMNS = frozenset(
    {
        "event_type",
        "sku",
        "pincode",
        "device_id",
        "subnet",
        "merchant_id",
        "payment_status",
    }
)
RECENT_PCA = re.compile(r"^v\d+$")


class IncompletePredictPayloadError(ValueError):
    """Payload is IEEE-shaped but too sparse to represent a meaningful transaction."""

    def __init__(self, message: str, present_core: list[str] | None = None) -> None:
        super().__init__(message)
        self.present_core = present_core or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "incomplete_payload": True,
            "detail": str(self),
            "world": WORLD,
            "dataset": DATASET_NAME,
            "provenance": PROVENANCE,
            "present_core_fields": self.present_core,
            "required_core_fields": list(CORE_TRANSACTION_FIELDS),
            "minimum_core_fields": MIN_CORE_FIELDS,
            "features_fabricated": False,
            "not_a_live_production_decision": True,
            "not_delayed_ground_truth": True,
            "not_an_llm": True,
            "not_january_2026_source_model": True,
        }


class IncompleteModelArtifactError(ValueError):
    """Persisted joblib is missing the train-fit encoder required for inference."""


def score_encoded(model: Any, features: pd.DataFrame) -> np.ndarray:
    assert_no_leakage(features)
    expected = list(getattr(model, "feature_names_in_", features.columns))
    missing = [name for name in expected if name not in features.columns]
    if missing:
        aligned = features.copy()
        for name in missing:
            aligned[name] = np.nan
    else:
        aligned = features
    return model.predict_proba(aligned.loc[:, expected])[:, 1]


def score_frame(model: Any, features: pd.DataFrame) -> np.ndarray:
    """Score an already-encoded frame. Prefer IeeeFraudArtifact.score for raw rows."""
    return score_encoded(model, features)


class IeeeFraudArtifact:
    """Classifier + train-fit encoder + frozen threshold."""

    def __init__(
        self,
        estimator: Any,
        encoder: CategoricalEncoder,
        threshold: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.estimator = estimator
        self.encoder = encoder
        self.threshold = float(threshold)
        self.metadata = metadata or {}

    def score(self, raw_features: pd.DataFrame) -> np.ndarray:
        encoded = self.encoder.transform(raw_features)
        return score_encoded(self.estimator, encoded)

    def to_bundle(self) -> dict[str, Any]:
        return {
            "bundle_version": BUNDLE_VERSION,
            "estimator": self.estimator,
            "encoder": self.encoder.to_dict(),
            "threshold": self.threshold,
            "metadata": self.metadata,
            "provenance": PROVENANCE,
            "world": WORLD,
        }

    @classmethod
    def from_bundle(cls, payload: Any) -> IeeeFraudArtifact:
        if not isinstance(payload, dict) or "encoder" not in payload or "estimator" not in payload:
            raise IncompleteModelArtifactError(
                "IEEE-CIS model artifact is incomplete: train-fit preprocessing state is missing. "
                "Retrain with models.ieee_fraud.pipeline."
            )
        return cls(
            estimator=payload["estimator"],
            encoder=CategoricalEncoder.from_dict(payload["encoder"]),
            threshold=float(payload["threshold"]),
            metadata=dict(payload.get("metadata") or {}),
        )


def load_model(path: Path) -> IeeeFraudArtifact:
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"IEEE-CIS model artifact is missing: {target}")
    return IeeeFraudArtifact.from_bundle(joblib.load(target))


def save_model(artifact: IeeeFraudArtifact, path: Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact.to_bundle(), target)
    return target


def save_encoder(encoder: CategoricalEncoder, path: Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(encoder.to_dict(), indent=2), encoding="utf-8")
    return target


def _unwrap_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "transaction" in payload and isinstance(payload["transaction"], dict):
        return dict(payload["transaction"])
    return dict(payload)


def assert_ieee_predict_schema(columns: list[str]) -> None:
    usable = [name for name in columns if name not in FORBIDDEN_FEATURES]
    if any(RECENT_PCA.fullmatch(name) for name in usable):
        raise PredictSchemaError(
            "January 2026 schema cannot be scored by the IEEE-CIS model. "
            "v1–v28 are not IEEE-CIS V*."
        )
    if SYNTHETIC_ONLY_COLUMNS.intersection(usable) and not discover_feature_columns(usable):
        raise PredictSchemaError(
            "Synthetic seed-42 schema cannot be scored by the IEEE-CIS model."
        )
    if not discover_feature_columns(usable):
        raise PredictSchemaError(
            "Payload has no IEEE-CIS features that this model can score honestly."
        )
    present_core = [name for name in CORE_TRANSACTION_FIELDS if name in usable]
    if len(present_core) < MIN_CORE_FIELDS:
        raise IncompletePredictPayloadError(
            "IEEE-CIS payload does not contain enough identifiable transaction fields "
            f"to score honestly. Provide at least {MIN_CORE_FIELDS} of "
            f"{list(CORE_TRANSACTION_FIELDS)}. Missing fields are not fabricated.",
            present_core=present_core,
        )


def raw_frame_from_payload(payload: dict[str, Any]) -> pd.DataFrame:
    row = _unwrap_payload(payload)
    if not row:
        raise PredictSchemaError("Prediction payload is empty.")
    assert_ieee_predict_schema(list(row.keys()))
    frame = pd.DataFrame([row])
    leaked = [name for name in frame.columns if name in FORBIDDEN_FEATURES]
    if leaked:
        frame = frame.drop(columns=leaked)
    if ID_COLUMN not in frame.columns:
        frame[ID_COLUMN] = "predict-0"
    features, _, _ = build_feature_frame(frame)
    return features


def predict_transaction(artifact: IeeeFraudArtifact, payload: dict[str, Any]) -> dict[str, Any]:
    raw = raw_frame_from_payload(payload)
    scores = artifact.score(raw)
    score = float(scores[0])
    present_core = [name for name in CORE_TRANSACTION_FIELDS if name in raw.columns and raw[name].notna().any()]
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "provenance": PROVENANCE,
        "fraud_risk_score": score,
        "operating_threshold": artifact.threshold,
        "above_operating_threshold": score >= artifact.threshold,
        "incomplete_payload": False,
        "present_core_fields": present_core,
        "features_fabricated": False,
        "not_a_live_production_decision": True,
        "not_delayed_ground_truth": True,
        "not_an_llm": True,
        "not_january_2026_source_model": True,
    }
