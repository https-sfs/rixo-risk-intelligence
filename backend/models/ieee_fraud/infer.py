"""Shared fraud-classifier inference. One artifact, every world.

Worlds adapt raw rows into canonical IEEE-CIS feature names, then call this
module. Missing canonical columns stay missing (NaN). Nothing is fabricated.
This is evidence, not a payment decision.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from models.ieee_fraud import (
    BUNDLE_VERSION,
    FEATURE_SPEC_NAME,
    JOBLIB_NAME,
    MODEL_DIR,
)
from models.ieee_fraud.features import ID_COLUMN, build_feature_frame
from models.ieee_fraud.predict import (
    IncompleteModelArtifactError,
    load_model,
)

MODEL_NAME = "ieee_hgb"
CLASSIFIER_HEADING = "Classifier"
STATUS_SCORED = "scored"
STATUS_NOT_SCORED = "not_scored"
HIGH_RISK = "High risk"
LOW_RISK = "Low risk"
REQUIRED_CANONICAL = ("TransactionAmt", "TransactionDT")

INVOCATION_LOG: list[dict[str, Any]] = []
_RESULT_CACHE: dict[str, dict[str, Any]] = {}


class ClassifierUnavailableError(RuntimeError):
    """Persisted classifier artifact is missing or incomplete."""


def cache_key(world: str, anomaly_id: str) -> str:
    return f"{world}::{anomaly_id}"


def reset_inference_state(*, clear_artifact: bool = False) -> None:
    INVOCATION_LOG.clear()
    _RESULT_CACHE.clear()
    if clear_artifact:
        load_shared_artifact.cache_clear()
        expected_feature_columns.cache_clear()


def get_cached(world: str, anomaly_id: str) -> dict[str, Any] | None:
    hit = _RESULT_CACHE.get(cache_key(world, anomaly_id))
    if hit is None:
        return None
    return dict(hit)


def store_cached(world: str, anomaly_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    bound = {**payload, "anomaly_id": anomaly_id, "world": world}
    _RESULT_CACHE[cache_key(world, anomaly_id)] = bound
    return dict(bound)


def record_invocation(
    world: str,
    anomaly_id: str | None,
    kind: str,
    extra: dict[str, Any] | None = None,
) -> None:
    event = {"world": world, "anomaly_id": anomaly_id, "kind": kind}
    if extra:
        event.update(extra)
    INVOCATION_LOG.append(event)


@lru_cache(maxsize=1)
def load_shared_artifact():
    path = MODEL_DIR / JOBLIB_NAME
    if not path.is_file():
        raise ClassifierUnavailableError(
            f"{JOBLIB_NAME} is missing. The shared classifier cannot score."
        )
    try:
        return load_model(path)
    except IncompleteModelArtifactError as exc:
        raise ClassifierUnavailableError(str(exc)) from exc


@lru_cache(maxsize=1)
def expected_feature_columns() -> list[str]:
    spec_path = MODEL_DIR / FEATURE_SPEC_NAME
    if spec_path.is_file():
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        columns = list(spec.get("columns") or [])
        if columns:
            return columns
    artifact = load_shared_artifact()
    return list(artifact.encoder.columns)


def operating_threshold() -> float:
    return float(load_shared_artifact().threshold)


def classify_score(score: float | None, threshold: float | None = None) -> str | None:
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return None
    cut = float(threshold if threshold is not None else operating_threshold())
    return HIGH_RISK if float(score) >= cut else LOW_RISK


def _non_null_columns(frame: pd.DataFrame) -> list[str]:
    used: list[str] = []
    for name in frame.columns:
        if name == ID_COLUMN:
            continue
        series = frame[name]
        if series.notna().any():
            used.append(str(name))
    return used


def coverage_payload(
    features_used: list[str],
    features_unavailable: list[str] | None = None,
) -> dict[str, Any]:
    expected = expected_feature_columns()
    used = list(dict.fromkeys(features_used))
    expected_set = set(expected)
    present = [name for name in used if name in expected_set or name == "relative_hour"]
    missing = [name for name in expected if name not in set(present)]
    if features_unavailable is not None:
        missing_report = list(features_unavailable)
    else:
        missing_report = missing
    total = max(len(expected), 1)
    return {
        "feature_coverage": round(len(present) / total, 6),
        "features_used": present,
        "features_used_count": len(present),
        "expected_feature_count": len(expected),
        "features_unavailable": missing_report,
        "features_unavailable_count": len(missing),
    }


def _base_payload(world: str, anomaly_id: str | None) -> dict[str, Any]:
    return {
        "heading": CLASSIFIER_HEADING,
        "world": world,
        "anomaly_id": anomaly_id,
        "model": MODEL_NAME,
        "model_version": BUNDLE_VERSION,
        "bundle_version": BUNDLE_VERSION,
        "not_a_live_production_decision": True,
        "not_observed_fraud_label": True,
        "not_deterministic_detection": True,
        "features_fabricated": False,
        "not_an_llm": True,
    }


def not_scored(
    *,
    world: str,
    anomaly_id: str | None = None,
    reason: str,
    missing_features: list[str] | None = None,
    features_used: list[str] | None = None,
) -> dict[str, Any]:
    coverage = coverage_payload(features_used or [], missing_features)
    payload = {
        **_base_payload(world, anomaly_id),
        "status": STATUS_NOT_SCORED,
        "scored": False,
        "fraud_risk_score": None,
        "classification": None,
        "above_operating_threshold": None,
        "operating_threshold": None,
        "reason": reason,
        "missing_features": list(missing_features or []),
        **coverage,
    }
    record_invocation(world, anomaly_id, "not_scored", {"reason": reason})
    if anomaly_id:
        store_cached(world, anomaly_id, payload)
    return payload


def scored_block(
    *,
    world: str,
    anomaly_id: str | None,
    fraud_risk_score: float,
    threshold: float,
    high_risk_count: int | None = None,
    mean_score: float | None = None,
    p95_score: float | None = None,
    scored_rows: int | None = None,
    features_used: list[str] | None = None,
    features_unavailable: list[str] | None = None,
    source: str = "shared_infer",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    coverage = coverage_payload(features_used or [], features_unavailable)
    display = float(fraud_risk_score)
    payload = {
        **_base_payload(world, anomaly_id),
        "status": STATUS_SCORED,
        "scored": True,
        "fraud_risk_score": display,
        "classification": classify_score(display, threshold),
        "above_operating_threshold": display >= float(threshold),
        "operating_threshold": float(threshold),
        "high_risk_count": high_risk_count,
        "mean_score": mean_score,
        "p95_score": float(p95_score) if p95_score is not None else display,
        "scored_rows": scored_rows,
        "source": source,
        "reason": None,
        "missing_features": [],
        **coverage,
    }
    if extra:
        payload.update(extra)
    record_invocation(world, anomaly_id, "scored", {"source": source})
    if anomaly_id:
        store_cached(world, anomaly_id, payload)
    return payload


def score_canonical_frame(
    frame: pd.DataFrame,
    *,
    world: str,
    anomaly_id: str | None = None,
    features_used: list[str] | None = None,
    features_unavailable: list[str] | None = None,
) -> dict[str, Any]:
    """Score a frame that already uses canonical IEEE-CIS column names."""
    if frame is None or frame.empty:
        return not_scored(
            world=world,
            anomaly_id=anomaly_id,
            reason="Required feature(s) unavailable",
            missing_features=list(REQUIRED_CANONICAL),
        )
    work = frame.copy()
    leaked = [name for name in ("isFraud", "is_fraud", "fraud_label", "fraud_probability") if name in work.columns]
    if leaked:
        work = work.drop(columns=leaked)
    if ID_COLUMN not in work.columns:
        work[ID_COLUMN] = [f"{world}-row-{index}" for index in range(len(work))]
    present = _non_null_columns(work)
    missing_required = [name for name in REQUIRED_CANONICAL if name not in present]
    if missing_required:
        return not_scored(
            world=world,
            anomaly_id=anomaly_id,
            reason="Required feature(s) unavailable",
            missing_features=missing_required,
            features_used=present,
        )
    try:
        artifact = load_shared_artifact()
    except ClassifierUnavailableError as exc:
        return not_scored(
            world=world,
            anomaly_id=anomaly_id,
            reason=str(exc),
            missing_features=[],
            features_used=present,
        )
    features, _, meta = build_feature_frame(work)
    scores = np.asarray(artifact.score(features), dtype=np.float64)
    threshold = float(artifact.threshold)
    used = features_used if features_used is not None else present
    record_invocation(world, anomaly_id, "score_canonical_frame", {"rows": int(scores.size)})
    return {
        "world": world,
        "anomaly_id": anomaly_id,
        "status": STATUS_SCORED,
        "scored": True,
        "scores": scores,
        "threshold": threshold,
        "high_risk_count": int((scores >= threshold).sum()),
        "p95_score": float(np.quantile(scores, 0.95)) if scores.size else None,
        "mean_score": float(scores.mean()) if scores.size else None,
        "scored_rows": int(scores.size),
        "meta": meta,
        "features_used": list(used),
        "features_unavailable": list(features_unavailable or []),
        "features_fabricated": False,
        "model": MODEL_NAME,
        "model_version": BUNDLE_VERSION,
        "not_a_live_production_decision": True,
    }


def classifier_from_scores(
    scored: dict[str, Any],
    *,
    world: str,
    anomaly_id: str | None,
    source: str = "shared_infer",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not scored or not scored.get("scored"):
        return not_scored(
            world=world,
            anomaly_id=anomaly_id,
            reason=str(scored.get("reason") or "Required feature(s) unavailable"),
            missing_features=list(scored.get("missing_features") or scored.get("features_unavailable") or []),
            features_used=list(scored.get("features_used") or []),
        )
    p95 = scored.get("p95_score")
    mean = scored.get("mean_score")
    display = p95 if p95 is not None else mean
    if display is None:
        return not_scored(
            world=world,
            anomaly_id=anomaly_id,
            reason="Required feature(s) unavailable",
            missing_features=list(REQUIRED_CANONICAL),
        )
    return scored_block(
        world=world,
        anomaly_id=anomaly_id,
        fraud_risk_score=float(display),
        threshold=float(scored["threshold"]),
        high_risk_count=scored.get("high_risk_count"),
        mean_score=None if mean is None else float(mean),
        p95_score=None if p95 is None else float(p95),
        scored_rows=scored.get("scored_rows"),
        features_used=list(scored.get("features_used") or []),
        features_unavailable=list(scored.get("features_unavailable") or []),
        source=source,
        extra=extra,
    )


def classifier_from_hour_overlay(
    overlay_hour: dict[str, Any] | None,
    *,
    world: str,
    anomaly_id: str | None,
    features_used: list[str] | None = None,
    features_unavailable: list[str] | None = None,
    source: str = "persisted_overlay",
) -> dict[str, Any]:
    """Format a previously scored hour overlay through the shared contract.

    IEEE-CIS hours are scored once by the pipeline using the same artifact.
    This does not train a new model and does not rescore the ledger.
    """
    cached = get_cached(world, anomaly_id) if anomaly_id else None
    if cached is not None:
        record_invocation(world, anomaly_id, "cache")
        return cached
    if not overlay_hour:
        return not_scored(
            world=world,
            anomaly_id=anomaly_id,
            reason="Required feature(s) unavailable",
            missing_features=list(REQUIRED_CANONICAL),
        )
    p95 = overlay_hour.get("p95_score")
    threshold = overlay_hour.get("threshold")
    if p95 is None or threshold is None:
        return not_scored(
            world=world,
            anomaly_id=anomaly_id,
            reason="Required feature(s) unavailable",
            missing_features=list(REQUIRED_CANONICAL),
        )
    expected = expected_feature_columns()
    used = features_used if features_used is not None else list(expected)
    return scored_block(
        world=world,
        anomaly_id=anomaly_id,
        fraud_risk_score=float(p95),
        threshold=float(threshold),
        high_risk_count=overlay_hour.get("high_risk_count"),
        mean_score=overlay_hour.get("mean_score"),
        p95_score=float(p95),
        scored_rows=overlay_hour.get("transaction_count"),
        features_used=used,
        features_unavailable=features_unavailable or [],
        source=source,
        extra={
            "sample_scope": overlay_hour.get("sample_scope"),
            "label": overlay_hour.get("label"),
        },
    )


def attach_classifier(evidence: dict[str, Any], classifier: dict[str, Any]) -> dict[str, Any]:
    evidence["classifier"] = classifier
    return evidence
