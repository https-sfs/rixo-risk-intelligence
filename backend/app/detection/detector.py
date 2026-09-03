"""Deterministic spike detector.

Classifies hourly activity as ordinary, a legitimate festive volume spike,
or a suspicious coordinated spike. It does not issue a payment-level fraud
decision and does not use event_type labels.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import pandas as pd

from detection.features import compute_window_features
from detection.scoring import (
    SPIKE_TYPE_COORDINATED,
    SPIKE_TYPE_FESTIVE,
    SPIKE_TYPE_ORDINARY,
    add_baselines,
    classify_window,
    coordination_score,
)


@dataclass
class SpikeRecord:
    spike_id: str
    window_start: str
    window_end: str
    spike_type: str
    severity: str
    volume: int
    baseline_volume: float
    volume_change_ratio: float
    fraud_rate: float
    baseline_fraud_rate: float
    failure_rate: float
    unique_accounts: int
    unique_devices: int
    unique_ip_subnets: int
    unique_pincodes: int
    top_skus: list[dict[str, int | str]]
    anomaly_reasons: list[str]
    anomaly_score: float
    coordination_score: float = 0.0
    extra: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("extra", None)
        return payload


def _fmt(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")


def _ratio(value: float, baseline: float) -> float:
    if baseline is None or pd.isna(baseline) or baseline <= 0:
        return float("nan")
    return float(value / baseline)


def detect_spikes(transactions: pd.DataFrame) -> list[SpikeRecord]:
    windows = add_baselines(compute_window_features(transactions))
    spikes: list[SpikeRecord] = []

    for _, row in windows.iterrows():
        coord, reasons = coordination_score(row)
        spike_type, severity, anomaly_score, reasons = classify_window(row, coord, reasons)
        if spike_type == SPIKE_TYPE_ORDINARY:
            continue

        prefix = "coord" if spike_type == SPIKE_TYPE_COORDINATED else "fest"
        start = pd.Timestamp(row["window_start"])
        spikes.append(
            SpikeRecord(
                spike_id=f"spk-{prefix}-{start.strftime('%Y%m%d-%H')}",
                window_start=_fmt(row["window_start"]),
                window_end=_fmt(row["window_end"]),
                spike_type=spike_type,
                severity=severity,
                volume=int(row["volume"]),
                baseline_volume=round(float(row["baseline_volume"]), 3),
                volume_change_ratio=round(_ratio(float(row["volume"]), float(row["baseline_volume"])), 3),
                fraud_rate=round(float(row["fraud_rate"]), 4),
                baseline_fraud_rate=round(float(row["baseline_fraud_rate"]), 4),
                failure_rate=round(float(row["failure_rate"]), 4),
                unique_accounts=int(row["unique_accounts"]),
                unique_devices=int(row["unique_devices"]),
                unique_ip_subnets=int(row["unique_ip_subnets"]),
                unique_pincodes=int(row["unique_pincodes"]),
                top_skus=list(row["top_skus"]),
                anomaly_reasons=reasons,
                anomaly_score=round(float(anomaly_score), 3),
                coordination_score=round(float(coord), 3),
            )
        )

    return spikes


def spikes_to_frame(spikes: list[SpikeRecord]) -> pd.DataFrame:
    rows = []
    for spike in spikes:
        row = spike.to_dict()
        row["top_skus"] = json.dumps(row["top_skus"])
        row["anomaly_reasons"] = json.dumps(row["anomaly_reasons"])
        rows.append(row)
    return pd.DataFrame(rows)


def compute_hourly_windows(transactions: pd.DataFrame) -> pd.DataFrame:
    windows = add_baselines(compute_window_features(transactions))
    types: list[str] = []
    scores: list[float] = []
    coords: list[float] = []
    for _, row in windows.iterrows():
        coord, reasons = coordination_score(row)
        spike_type, _, anomaly_score, _ = classify_window(row, coord, reasons)
        types.append(spike_type)
        scores.append(anomaly_score)
        coords.append(coord)
    windows["spike_type"] = types
    windows["anomaly_score"] = scores
    windows["coordination_score"] = coords
    return windows


__all__ = [
    "SpikeRecord",
    "SPIKE_TYPE_COORDINATED",
    "SPIKE_TYPE_FESTIVE",
    "SPIKE_TYPE_ORDINARY",
    "compute_hourly_windows",
    "detect_spikes",
    "spikes_to_frame",
]
