"""Assemble Phase 2A evidence from held-out files.

tools/paths.py stays locked on seed-42. This loader never uses those paths.
event_type is dropped and is not passed into investigation evidence.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from detection.scoring import SPIKE_TYPE_FESTIVE, SPIKE_TYPE_ORDINARY
from tools.baseline import _aggregate, _metric
from tools.concentration import calculate_concentration
from tools.load import INVESTIGATION_COLUMNS, filter_window
from tools.metrics import calculate_entity_counts, calculate_window_metrics
from tools.relationships import calculate_relationships
from tools.serialize import is_missing, json_safe
from tools.velocity import calculate_velocity

from evaluation.paths import (
    HELDOUT_SPIKES_CSV_PATH,
    HELDOUT_TRANSACTIONS_PATH,
    HELDOUT_WINDOWS_PATH,
)


def _parse_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _optional_float(value: Any) -> float | None:
    if is_missing(value):
        return None
    return float(value)


def load_heldout_transactions() -> pd.DataFrame:
    frame = pd.read_csv(HELDOUT_TRANSACTIONS_PATH)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["pincode"] = frame["pincode"].astype(str)
    return frame.loc[:, list(INVESTIGATION_COLUMNS)]


def load_heldout_spikes() -> pd.DataFrame:
    return pd.read_csv(HELDOUT_SPIKES_CSV_PATH)


def load_heldout_hourly_windows() -> pd.DataFrame:
    frame = pd.read_csv(HELDOUT_WINDOWS_PATH)
    frame["window_start"] = pd.to_datetime(frame["window_start"])
    return frame


def spike_record_from_row(row: pd.Series) -> dict[str, Any]:
    return {
        "spike_id": str(row["spike_id"]),
        "window_start": pd.Timestamp(row["window_start"]),
        "window_end": pd.Timestamp(row["window_end"]),
        "spike_type": str(row["spike_type"]),
        "severity": str(row["severity"]),
        "volume": int(row["volume"]),
        "baseline_volume": _optional_float(row.get("baseline_volume")),
        "volume_change_ratio": _optional_float(row.get("volume_change_ratio")),
        "fraud_rate": float(row["fraud_rate"]),
        "baseline_fraud_rate": _optional_float(row.get("baseline_fraud_rate")),
        "failure_rate": float(row["failure_rate"]),
        "unique_accounts": int(row["unique_accounts"]),
        "unique_devices": int(row["unique_devices"]),
        "unique_ip_subnets": int(row["unique_ip_subnets"]),
        "unique_pincodes": int(row["unique_pincodes"]),
        "top_skus": _parse_json_field(row.get("top_skus")),
        "anomaly_reasons": _parse_json_field(row.get("anomaly_reasons")),
        "anomaly_score": float(row["anomaly_score"]),
        "coordination_score": float(row["coordination_score"]),
    }


def heldout_baseline_comparison(
    spike: dict[str, Any],
    window_metrics: dict[str, Any],
    hourly: pd.DataFrame,
) -> dict[str, Any]:
    """Same comparison shape as tools.baseline, using held-out hourly windows only."""
    current = None
    match = hourly.loc[hourly["window_start"] == spike["window_start"]]
    if not match.empty:
        current = match.iloc[0]

    volume_reason = "hour-of-day baseline unavailable"
    fraud_reason = "rolling fraud-rate baseline unavailable"
    if current is not None:
        if is_missing(spike.get("baseline_volume")) and is_missing(current.get("baseline_volume")):
            volume_reason = "hour-of-day baseline unavailable"
        if is_missing(spike.get("baseline_fraud_rate")) and is_missing(current.get("baseline_fraud_rate")):
            fraud_reason = "rolling fraud-rate baseline unavailable"

    ordinary = hourly.loc[hourly["spike_type"] == SPIKE_TYPE_ORDINARY] if "spike_type" in hourly.columns else pd.DataFrame()
    festive = hourly.loc[hourly["spike_type"] == SPIKE_TYPE_FESTIVE] if "spike_type" in hourly.columns else pd.DataFrame()
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
            "mean_volume": _aggregate(ordinary, "volume", "no ordinary hourly windows available for comparison"),
            "mean_failure_rate": _aggregate(
                ordinary, "failure_rate", "no ordinary hourly failure-rate baseline available"
            ),
        },
        "festive_period": {
            "mean_volume": _aggregate(festive, "volume", "no festive hourly windows available for comparison"),
            "mean_failure_rate": _aggregate(
                festive, "failure_rate", "no festive hourly failure-rate baseline available"
            ),
            "mean_unique_accounts": _aggregate(
                festive, "unique_accounts", "no festive unique-account baseline available"
            ),
            "source": "detector-classified legitimate_festive_spike hours",
        },
    }


def build_heldout_evidence(
    spike: dict[str, Any],
    transactions: pd.DataFrame,
    hourly: pd.DataFrame,
) -> dict[str, Any]:
    window = filter_window(transactions, spike["window_start"], spike["window_end"])
    metrics = calculate_window_metrics(window)
    evidence = {
        "spike": {
            "spike_id": spike["spike_id"],
            "window_start": spike["window_start"].strftime("%Y-%m-%dT%H:%M:%S"),
            "window_end": spike["window_end"].strftime("%Y-%m-%dT%H:%M:%S"),
            "detector_type": spike["spike_type"],
            "severity": spike["severity"],
            "anomaly_reasons": spike["anomaly_reasons"],
            "anomaly_score": spike["anomaly_score"],
            "coordination_score": spike["coordination_score"],
        },
        "window": metrics,
        "entities": calculate_entity_counts(window),
        "concentration": calculate_concentration(window),
        "relationships": calculate_relationships(window),
        "velocity": calculate_velocity(window),
        "baseline_comparison": heldout_baseline_comparison(spike, metrics, hourly),
    }
    return json_safe(evidence)
