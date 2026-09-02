"""January 2026 classifier overlay. Uses the shared infer path, never January PCA."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.recent_data import RECENT_DATA_DIR, WORLD
from evaluation.recent_data.mapper import (
    RAW_CSV_FILENAME,
    discover_csv,
    map_collection,
    validate_required_columns,
)
from models.ieee_fraud.adapt import adapt_recent
from models.ieee_fraud.infer import (
    classifier_from_scores,
    get_cached,
    not_scored,
    record_invocation,
    score_canonical_frame,
    store_cached,
)

OVERLAY_NAME = "classifier_overlay.json"
LITE_COLUMNS = ("transaction_id", "amount", "is_fraud", "timestamp", "test_date")
_OVERLAY_MEMORY: dict[str, dict[str, Any]] | None = None
PERSIST_OVERLAY = True


def overlay_path(data_dir: Path | None = None) -> Path:
    return (data_dir or RECENT_DATA_DIR) / OVERLAY_NAME


def reset_recent_classifier_state() -> None:
    global _OVERLAY_MEMORY
    _OVERLAY_MEMORY = None
    _january_mapped_lite.cache_clear()


def _hour_key(value: Any) -> str:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        return str(value)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S")


@lru_cache(maxsize=1)
def _january_mapped_lite() -> pd.DataFrame:
    path = discover_csv(RECENT_DATA_DIR)
    header = pd.read_csv(path, nrows=0)
    available = [name for name in LITE_COLUMNS if name in header.columns]
    raw = pd.read_csv(path, usecols=available)
    validate_required_columns(raw)
    return map_collection(raw)


def _load_disk_overlay() -> dict[str, dict[str, Any]]:
    global _OVERLAY_MEMORY
    if _OVERLAY_MEMORY is not None:
        return _OVERLAY_MEMORY
    path = overlay_path()
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        hours = payload.get("hours") if isinstance(payload, dict) else None
        _OVERLAY_MEMORY = {str(key): dict(value) for key, value in (hours or {}).items()}
        return _OVERLAY_MEMORY
    _OVERLAY_MEMORY = {}
    return _OVERLAY_MEMORY


def _write_disk_overlay(hours: dict[str, dict[str, Any]]) -> None:
    if not PERSIST_OVERLAY:
        return
    path = overlay_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"world": WORLD, "hours": hours}, indent=2),
        encoding="utf-8",
    )


def _score_hour(mapped_hour: pd.DataFrame, anomaly_id: str, hour_key: str) -> dict[str, Any]:
    adapted = adapt_recent(mapped_hour, world=WORLD)
    if not adapted.can_score:
        return not_scored(
            world=WORLD,
            anomaly_id=anomaly_id,
            reason="Required feature(s) unavailable",
            missing_features=adapted.missing_required,
            features_used=adapted.features_used,
        )
    scored = score_canonical_frame(
        adapted.frame,
        world=WORLD,
        anomaly_id=anomaly_id,
        features_used=adapted.features_used,
        features_unavailable=adapted.features_unavailable,
    )
    return classifier_from_scores(
        scored,
        world=WORLD,
        anomaly_id=anomaly_id,
        source="shared_infer",
        extra={"hour_start": hour_key, "adapter_notes": adapted.notes},
    )


def classifier_for_recent_anomaly(anomaly_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
    cached = get_cached(WORLD, anomaly_id)
    if cached is not None:
        record_invocation(WORLD, anomaly_id, "cache")
        return cached
    hour = evidence.get("hour_start")
    if not hour:
        return not_scored(
            world=WORLD,
            anomaly_id=anomaly_id,
            reason="Required feature(s) unavailable",
            missing_features=["TransactionDT"],
        )
    hour_key = _hour_key(hour)
    overlay = _load_disk_overlay()
    if hour_key in overlay:
        stored = dict(overlay[hour_key])
        stored["anomaly_id"] = anomaly_id
        store_cached(WORLD, anomaly_id, stored)
        record_invocation(WORLD, anomaly_id, "overlay")
        return stored
    try:
        mapped = _january_mapped_lite()
    except Exception as exc:  # noqa: BLE001
        return not_scored(
            world=WORLD,
            anomaly_id=anomaly_id,
            reason=str(exc),
            missing_features=["TransactionAmt", "TransactionDT"],
        )
    hours = pd.to_datetime(mapped["hour_start"], errors="coerce")
    target = pd.Timestamp(hour)
    slice_ = mapped.loc[hours == target]
    if slice_.empty:
        return not_scored(
            world=WORLD,
            anomaly_id=anomaly_id,
            reason="Required feature(s) unavailable",
            missing_features=["TransactionAmt", "TransactionDT"],
        )
    result = _score_hour(slice_, anomaly_id, hour_key)
    overlay[hour_key] = dict(result)
    _write_disk_overlay(overlay)
    return result
