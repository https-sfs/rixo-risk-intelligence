"""Load one detected spike and only the transactions in its window."""

from __future__ import annotations

from typing import Any

import pandas as pd

from tools.paths import DETECTED_SPIKES_PATH, TRANSACTIONS_PATH
from tools.serialize import is_missing

INVESTIGATION_COLUMNS: tuple[str, ...] = (
    "transaction_id",
    "timestamp",
    "account_id",
    "device_id",
    "ip_address",
    "ip_subnet",
    "pincode",
    "sku_id",
    "amount",
    "payment_method",
    "transaction_status",
    "fraud_label",
    "account_tx_count_1h",
    "device_tx_count_1h",
    "ip_subnet_tx_count_1h",
)


def _optional_float(value: Any) -> float | None:
    if is_missing(value):
        return None
    return float(value)


def load_detected_spike(spike_id: str) -> dict[str, Any]:
    spikes = pd.read_csv(DETECTED_SPIKES_PATH)
    matches = spikes.loc[spikes["spike_id"] == spike_id]
    if matches.empty:
        raise KeyError(f"Unknown spike_id: {spike_id}")

    row = matches.iloc[0]
    reasons_raw = row.get("anomaly_reasons", "[]")
    top_skus_raw = row.get("top_skus", "[]")
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
        "top_skus": top_skus_raw,
        "anomaly_reasons": reasons_raw,
        "anomaly_score": float(row["anomaly_score"]),
        "coordination_score": float(row["coordination_score"]),
    }


def load_transactions() -> pd.DataFrame:
    frame = pd.read_csv(TRANSACTIONS_PATH)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["pincode"] = frame["pincode"].astype(str)
    return frame.loc[:, list(INVESTIGATION_COLUMNS)]


def filter_window(
    transactions: pd.DataFrame,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> pd.DataFrame:
    stamps = pd.to_datetime(transactions["timestamp"])
    mask = (stamps >= window_start) & (stamps < window_end)
    return transactions.loc[mask].copy()


def load_spike_transactions(spike_id: str) -> tuple[dict[str, Any], pd.DataFrame]:
    spike = load_detected_spike(spike_id)
    window = filter_window(
        load_transactions(),
        spike["window_start"],
        spike["window_end"],
    )
    return spike, window
