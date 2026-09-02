"""Read detected-spike artifacts. No recalculation. No ledger dump."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from tools.load import load_detected_spike
from tools.paths import DETECTED_SPIKES_PATH
from tools.serialize import is_missing, json_safe


def _parse_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _optional_number(value: Any) -> float | None:
    if is_missing(value):
        return None
    return json_safe(value)


def serialize_spike(row: dict[str, Any]) -> dict[str, Any]:
    start = row["window_start"]
    end = row["window_end"]
    return {
        "spike_id": str(row["spike_id"]),
        "window_start": start.isoformat() if hasattr(start, "isoformat") else str(start),
        "window_end": end.isoformat() if hasattr(end, "isoformat") else str(end),
        "spike_type": str(row["spike_type"]),
        "severity": str(row["severity"]),
        "volume": int(row["volume"]),
        "baseline_volume": _optional_number(row.get("baseline_volume")),
        "volume_change_ratio": _optional_number(row.get("volume_change_ratio")),
        "fraud_rate": float(row["fraud_rate"]),
        "baseline_fraud_rate": _optional_number(row.get("baseline_fraud_rate")),
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


def list_detected_spikes() -> list[dict[str, Any]]:
    frame = pd.read_csv(DETECTED_SPIKES_PATH)
    spikes: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        spikes.append(serialize_spike(dict(row)))
    return spikes


def get_detected_spike(spike_id: str) -> dict[str, Any]:
    return serialize_spike(load_detected_spike(spike_id))
