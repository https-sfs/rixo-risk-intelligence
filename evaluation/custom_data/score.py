"""Bring Your Data scoring through the shared classifier inference service."""

from __future__ import annotations

import heapq
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from evaluation.custom_data import USER_MODEL_PROVENANCE, WORLD
from evaluation.custom_data.compatibility import official_ieee_columns
from evaluation.custom_data.detect import SECONDS_PER_HOUR, prepare_analysis_frame, relative_hour_key
from evaluation.custom_data.mapping import apply_mapping
from evaluation.custom_data.schema import CustomDataError
from evaluation.custom_data.stream import SCORE_CHUNK_ROWS, iter_csv_chunks
from models.ieee_fraud import FORBIDDEN_FEATURES
from models.ieee_fraud.adapt import adapt_custom, adapt_ieee
from models.ieee_fraud.features import ID_COLUMN
from models.ieee_fraud.infer import (
    ClassifierUnavailableError,
    classifier_from_hour_overlay,
    classifier_from_scores,
    score_canonical_frame,
)
from models.ieee_fraud.predict import IncompleteModelArtifactError, assert_ieee_predict_schema


class CustomModelUnavailableError(CustomDataError):
    """Persisted classifier artifact is missing; user data is not scored."""


def _hour_keys(mapped: pd.DataFrame) -> pd.Series:
    work = prepare_analysis_frame(mapped)
    if "hour_start" in work.columns:
        return work["hour_start"].astype("string")
    return pd.Series(pd.NA, index=mapped.index)


def score_compatible_frame(raw: pd.DataFrame) -> dict[str, Any]:
    official = official_ieee_columns([str(name) for name in raw.columns])
    if official:
        adapted = adapt_ieee(raw, world=WORLD)
    else:
        adapted = adapt_custom(raw, world=WORLD)
    if not adapted.can_score:
        raise CustomDataError(
            "Required classifier features could not be derived: "
            + ", ".join(adapted.missing_required)
        )
    scored = score_canonical_frame(
        adapted.frame,
        world=WORLD,
        features_used=adapted.features_used,
        features_unavailable=adapted.features_unavailable,
    )
    if not scored.get("scored"):
        raise CustomModelUnavailableError(str(scored.get("reason") or "Classifier did not score."))
    scores = scored["scores"]
    threshold = float(scored["threshold"])
    result = pd.DataFrame(
        {
            "row_index": raw.index,
            "fraud_risk_score": scores,
            "above_operating_threshold": scores >= threshold,
        }
    )
    return {
        "world": WORLD,
        "provenance": USER_MODEL_PROVENANCE,
        "threshold": threshold,
        "scored_rows": int(len(result)),
        "high_risk_count": int(result["above_operating_threshold"].sum()),
        "p95_score": float(result["fraud_risk_score"].quantile(0.95)) if len(result) else None,
        "scores": result,
        "features_used": adapted.features_used,
        "features_unavailable": adapted.features_unavailable,
        "features_fabricated": False,
        "not_a_live_production_decision": True,
        "not_an_llm": True,
        "invoked_shared_infer": True,
    }


def score_adapted_path(
    path: str | Path,
    columns: list[str],
    mapping: dict[str, str] | None = None,
    label_column: str | None = None,
) -> dict[str, Any]:
    """Score a user CSV through the world adapter + shared infer. Does not retrain."""
    mapping = mapping or {}
    official = official_ieee_columns(columns)
    sources = [name for name in mapping.values() if name]
    usecols = list(dict.fromkeys([*sources, *official, ID_COLUMN, label_column]))
    usecols = [name for name in usecols if name and name in columns]
    if not usecols:
        raise CustomDataError("No mapped or official columns are available to score.")
    threshold = None
    score_parts: list[np.ndarray] = []
    label_parts: list[np.ndarray] = []
    hours: dict[str, dict[str, Any]] = defaultdict(lambda: {"scores": [], "ids": []})
    features_used: list[str] = []
    features_unavailable: list[str] = []
    offset = 0
    try:
        for chunk in iter_csv_chunks(path, chunksize=SCORE_CHUNK_ROWS, usecols=usecols):
            mapped = apply_mapping(chunk, mapping) if mapping else chunk
            adapted = adapt_custom(mapped, world=WORLD)
            if not adapted.can_score:
                offset += int(len(chunk))
                features_unavailable = adapted.missing_required
                continue
            features_used = adapted.features_used
            features_unavailable = adapted.features_unavailable
            scored = score_canonical_frame(
                adapted.frame,
                world=WORLD,
                features_used=adapted.features_used,
                features_unavailable=adapted.features_unavailable,
            )
            if not scored.get("scored"):
                raise CustomModelUnavailableError(str(scored.get("reason") or "Classifier did not score."))
            scores = np.asarray(scored["scores"], dtype=np.float32)
            threshold = float(scored["threshold"])
            score_parts.append(scores)
            label_name = label_column or mapping.get("fraud_label")
            if label_name and label_name in chunk.columns:
                label_parts.append(pd.to_numeric(chunk[label_name], errors="coerce").to_numpy(dtype=float))
            elif "fraud_label" in mapped.columns:
                label_parts.append(pd.to_numeric(mapped["fraud_label"], errors="coerce").to_numpy(dtype=float))
            hour_keys = _hour_keys(mapped)
            ids = (
                mapped["transaction_id"].astype(str)
                if "transaction_id" in mapped.columns
                else pd.Series([f"user-{offset + index}" for index in range(len(mapped))], index=mapped.index)
            )
            for hour, score, txn in zip(hour_keys, scores, ids, strict=False):
                if pd.isna(hour) or hour in {"<NA>", "nan", "None"}:
                    continue
                key = str(hour)
                slot = hours[key]
                value = float(score)
                slot["scores"].append(value)
                tops = slot["ids"]
                item = (value, str(txn))
                if len(tops) < 5:
                    heapq.heappush(tops, item)
                elif value > tops[0][0]:
                    heapq.heapreplace(tops, item)
            offset += int(len(chunk))
    except ClassifierUnavailableError as exc:
        raise CustomModelUnavailableError(str(exc)) from exc
    except IncompleteModelArtifactError as exc:
        raise CustomModelUnavailableError(str(exc)) from exc
    if not score_parts or threshold is None:
        raise CustomDataError(
            "Required classifier features could not be derived from the upload. "
            "Missing: " + ", ".join(features_unavailable or ["TransactionAmt", "TransactionDT"])
        )
    all_scores = np.concatenate(score_parts)
    hour_overlay = {}
    for key, slot in hours.items():
        values = np.asarray(slot["scores"], dtype=np.float32)
        tops = sorted(slot["ids"], reverse=True)[:5]
        hour_overlay[key] = {
            "label": USER_MODEL_PROVENANCE,
            "high_risk_count": int((values >= threshold).sum()),
            "p95_score": float(np.quantile(values, 0.95)),
            "mean_score": float(values.mean()),
            "threshold": threshold,
            "transaction_count": int(values.size),
            "sample_scope": "USER_DATASET_MODEL_OVERLAY",
            "top_transactions": [
                {
                    "transaction_id": txn,
                    "fraud_risk_score": score,
                    "provenance": USER_MODEL_PROVENANCE,
                }
                for score, txn in tops
            ],
            "features_used": features_used,
            "features_unavailable": features_unavailable,
            "not_a_live_production_decision": True,
        }
    labels = np.concatenate(label_parts) if label_parts else None
    return {
        "world": WORLD,
        "provenance": USER_MODEL_PROVENANCE,
        "threshold": threshold,
        "scored_rows": int(all_scores.size),
        "high_risk_count": int((all_scores >= threshold).sum()),
        "p95_score": float(np.quantile(all_scores, 0.95)),
        "hours": hour_overlay,
        "score_array": all_scores,
        "label_array": labels,
        "features_used": features_used,
        "features_unavailable": features_unavailable,
        "features_fabricated": False,
        "chunked": True,
        "invoked_shared_infer": True,
        "not_a_live_production_decision": True,
        "not_an_llm": True,
        "retrained": False,
    }


def score_compatible_path(
    path: str | Path,
    columns: list[str],
    label_column: str | None = None,
) -> dict[str, Any]:
    """Official IEEE columns: still goes through the shared infer path."""
    official = official_ieee_columns(columns)
    if not official:
        raise CustomDataError("No official IEEE-CIS columns are present to score.")
    assert_ieee_predict_schema(official)
    mapping = {}
    if "TransactionAmt" in columns:
        mapping["amount"] = "TransactionAmt"
    if "TransactionDT" in columns:
        mapping["timestamp"] = "TransactionDT"
    if "TransactionID" in columns:
        mapping["transaction_id"] = "TransactionID"
    if label_column:
        mapping["fraud_label"] = label_column
    return score_adapted_path(path, columns, mapping=mapping, label_column=label_column)


def hour_model_overlay(
    mapped: pd.DataFrame | None,
    scored: dict[str, Any],
    hour_start: str | None,
) -> dict[str, Any] | None:
    if not hour_start:
        return None
    hours = scored.get("hours") or {}
    if hour_start in hours:
        return hours[hour_start]
    if mapped is None or "scores" not in scored:
        return None
    if "timestamp" not in mapped.columns:
        return None
    work = prepare_analysis_frame(mapped)
    if "hour_start" not in work.columns:
        return None
    scores = scored["scores"]
    aligned = work.copy()
    aligned["fraud_risk_score"] = scores.set_index("row_index")["fraud_risk_score"]
    window = aligned.loc[aligned["hour_start"] == pd.Timestamp(hour_start)]
    if window.empty:
        return None
    threshold = scored["threshold"]
    tops = window.sort_values("fraud_risk_score", ascending=False).head(5).reset_index()
    return {
        "label": USER_MODEL_PROVENANCE,
        "high_risk_count": int((window["fraud_risk_score"] >= threshold).sum()),
        "p95_score": float(window["fraud_risk_score"].quantile(0.95)),
        "mean_score": float(window["fraud_risk_score"].mean()),
        "threshold": threshold,
        "transaction_count": int(len(window)),
        "sample_scope": "USER_DATASET_MODEL_OVERLAY",
        "top_transactions": [
            {
                "transaction_id": None if getattr(row, "transaction_id", None) is None else str(row.transaction_id),
                "fraud_risk_score": float(row.fraud_risk_score),
                "provenance": USER_MODEL_PROVENANCE,
            }
            for row in tops.itertuples(index=False)
        ],
        "features_used": scored.get("features_used") or [],
        "features_unavailable": scored.get("features_unavailable") or [],
        "not_a_live_production_decision": True,
    }


def classifier_for_custom_hour(
    scored: dict[str, Any] | None,
    hour_start: str | None,
    anomaly_id: str,
) -> dict[str, Any]:
    from models.ieee_fraud.infer import get_cached, not_scored

    cached = get_cached(WORLD, anomaly_id)
    if cached is not None:
        return cached
    if not scored or not scored.get("scored_rows"):
        return not_scored(
            world=WORLD,
            anomaly_id=anomaly_id,
            reason=str(scored.get("reason") if scored else "Required feature(s) unavailable"),
            missing_features=list((scored or {}).get("features_unavailable") or ["TransactionAmt", "TransactionDT"]),
            features_used=list((scored or {}).get("features_used") or []),
        )
    overlay = hour_model_overlay(None, scored, hour_start)
    if overlay:
        return classifier_from_hour_overlay(
            overlay,
            world=WORLD,
            anomaly_id=anomaly_id,
            features_used=list(scored.get("features_used") or overlay.get("features_used") or []),
            features_unavailable=list(scored.get("features_unavailable") or []),
            source="shared_infer",
        )
    return classifier_from_scores(
        {
            "scored": True,
            "p95_score": scored.get("p95_score"),
            "mean_score": scored.get("mean_score"),
            "threshold": scored.get("threshold"),
            "high_risk_count": scored.get("high_risk_count"),
            "scored_rows": scored.get("scored_rows"),
            "features_used": scored.get("features_used") or [],
            "features_unavailable": scored.get("features_unavailable") or [],
        },
        world=WORLD,
        anomaly_id=anomaly_id,
        source="shared_infer",
    )
