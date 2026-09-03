"""Compare a spike window to available baselines without inventing values."""

from __future__ import annotations

from typing import Any

import pandas as pd

from detection.scoring import SPIKE_TYPE_FESTIVE, SPIKE_TYPE_ORDINARY
from tools.paths import HOURLY_WINDOWS_PATH
from tools.serialize import as_float, is_missing


def _metric(value: Any, reason: str) -> dict[str, Any]:
    if is_missing(value):
        return {
            "value": None,
            "status": "unavailable",
            "reason": reason,
        }
    return {
        "value": as_float(value, 4 if abs(float(value)) < 1000 else 3),
        "status": "available",
    }


def _load_hourly_windows() -> pd.DataFrame | None:
    if not HOURLY_WINDOWS_PATH.exists():
        return None
    frame = pd.read_csv(HOURLY_WINDOWS_PATH)
    frame["window_start"] = pd.to_datetime(frame["window_start"])
    return frame


def _aggregate(hours: pd.DataFrame, column: str, reason: str) -> dict[str, Any]:
    if hours.empty or column not in hours.columns:
        return _metric(None, reason)
    series = hours[column].dropna()
    if series.empty:
        return _metric(None, reason)
    return {
        "value": as_float(series.mean()),
        "status": "available",
        "sample_hours": int(len(series)),
    }


def calculate_baseline_comparison(
    spike: dict[str, Any],
    window_metrics: dict[str, Any],
) -> dict[str, Any]:
    hourly = _load_hourly_windows()
    current = None
    if hourly is not None:
        match = hourly.loc[hourly["window_start"] == spike["window_start"]]
        if not match.empty:
            current = match.iloc[0]

    volume_reason = "hour-of-day baseline unavailable"
    fraud_reason = "rolling fraud-rate baseline unavailable"
    if current is not None:
        if is_missing(spike.get("baseline_volume")) and is_missing(current.get("baseline_volume")):
            volume_reason = "hour-of-day baseline unavailable"
        if is_missing(spike.get("baseline_fraud_rate")) and is_missing(
            current.get("baseline_fraud_rate")
        ):
            fraud_reason = "rolling fraud-rate baseline unavailable"

    ordinary = (
        hourly.loc[hourly["spike_type"] == SPIKE_TYPE_ORDINARY]
        if hourly is not None and "spike_type" in hourly.columns
        else pd.DataFrame()
    )
    festive = (
        hourly.loc[hourly["spike_type"] == SPIKE_TYPE_FESTIVE]
        if hourly is not None and "spike_type" in hourly.columns
        else pd.DataFrame()
    )

    return {
        "hourly_baseline": {
            "baseline_volume": _metric(spike.get("baseline_volume"), volume_reason),
            "volume_change_ratio": _metric(
                spike.get("volume_change_ratio"),
                "volume change ratio unavailable because baseline volume is unavailable",
            ),
            "baseline_fraud_rate": _metric(spike.get("baseline_fraud_rate"), fraud_reason),
            "window_volume": window_metrics["transaction_count"],
            "window_failure_rate": window_metrics["status_rates"]["failed"]
            + window_metrics["status_rates"]["declined"],
        },
        "normal_baseline": {
            "mean_volume": _aggregate(
                ordinary,
                "volume",
                "no ordinary hourly windows available for comparison",
            ),
            "mean_failure_rate": _aggregate(
                ordinary,
                "failure_rate",
                "no ordinary hourly failure-rate baseline available",
            ),
        },
        "festive_period": {
            "mean_volume": _aggregate(
                festive,
                "volume",
                "no festive hourly windows available for comparison",
            ),
            "mean_failure_rate": _aggregate(
                festive,
                "failure_rate",
                "no festive hourly failure-rate baseline available",
            ),
            "mean_unique_accounts": _aggregate(
                festive,
                "unique_accounts",
                "no festive unique-account baseline available",
            ),
            "source": "detector-classified legitimate_festive_spike hours",
        },
    }
