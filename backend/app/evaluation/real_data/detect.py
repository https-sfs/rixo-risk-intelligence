"""Label-free IEEE-CIS anomaly detection on relative-hour aggregates.

Live inference uses only observed volume, amount, ProductCD concentration, and
available identity/card/address proxies. isFraud is never an input.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from evaluation.real_data.mapper import AMOUNT_CURRENCY, DATASET_NAME, WORLD

LIVE_COLUMNS = (
    "relative_hour_bucket",
    "transaction_count",
    "amount_usd",
    "product_top",
    "product_top_share",
    "unique_product",
    "unique_card1_proxy",
    "card4_top",
    "card4_top_share",
    "addr2_top",
    "addr2_top_share",
    "identity_coverage",
    "device_type_top",
    "device_type_top_share",
)

LABELLED_COLUMNS = (
    "labelled_fraud_count",
    "labelled_fraud_rate",
    "labelled_fraud_amount_usd",
)

VOLUME_Z_THRESHOLD = 2.5
AMOUNT_Z_THRESHOLD = 2.5
PRODUCT_SHARE_THRESHOLD = 0.85
MIN_TRANSACTIONS = 40


def _robust_z(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    median = float(values.median()) if values.notna().any() else 0.0
    mad = float((values - median).abs().median()) if values.notna().any() else 0.0
    if mad == 0:
        return pd.Series(0.0, index=series.index)
    return 0.6745 * (values - median) / mad


def score_hourly(hourly: pd.DataFrame) -> pd.DataFrame:
    """Attach live anomaly scores. Drops labelled columns from the scoring inputs."""
    frame = hourly.copy()
    leaked = [name for name in LABELLED_COLUMNS if name in frame.columns]
    live = frame.drop(columns=leaked, errors="ignore")
    live["volume_z"] = _robust_z(live["transaction_count"])
    live["amount_z"] = _robust_z(live["amount_usd"])
    share = pd.to_numeric(live.get("product_top_share"), errors="coerce").fillna(0.0)
    live["product_share"] = share
    live["live_score"] = live[["volume_z", "amount_z"]].max(axis=1) + (share * 0.5)
    volume_hit = live["volume_z"] >= VOLUME_Z_THRESHOLD
    amount_hit = live["amount_z"] >= AMOUNT_Z_THRESHOLD
    product_hit = (share >= PRODUCT_SHARE_THRESHOLD) & (
        live["transaction_count"] >= MIN_TRANSACTIONS
    )
    live["is_anomaly"] = (volume_hit | amount_hit | product_hit) & (
        live["transaction_count"] >= MIN_TRANSACTIONS
    )
    live["signal_volume"] = volume_hit
    live["signal_amount"] = amount_hit
    live["signal_product"] = product_hit
    if leaked:
        for name in leaked:
            live[name] = frame[name]
    return live


def detect_anomalies(hourly: pd.DataFrame, limit: int = 30) -> list[dict[str, Any]]:
    scored = score_hourly(hourly)
    flagged = scored.loc[scored["is_anomaly"]].sort_values("live_score", ascending=False)
    if flagged.empty:
        flagged = scored.sort_values("live_score", ascending=False).head(limit)
    else:
        flagged = flagged.head(limit)

    anomalies: list[dict[str, Any]] = []
    for _, row in flagged.iterrows():
        bucket = int(row["relative_hour_bucket"])
        signals = []
        if bool(row["signal_volume"]):
            signals.append("elevated transaction volume")
        if bool(row["signal_amount"]):
            signals.append("elevated transaction amount")
        if bool(row["signal_product"]):
            signals.append("ProductCD concentration")
        if float(row.get("identity_coverage") or 0) >= 0.5:
            signals.append("identity coverage present")
        if not signals:
            signals.append("relative-hour outlier on live score")
        anomalies.append(
            {
                "anomaly_id": f"rda-{bucket}",
                "kind": "REAL DATA ANOMALY",
                "world": WORLD,
                "dataset": DATASET_NAME,
                "relative_hour_bucket": bucket,
                "transactions": int(row["transaction_count"]),
                "amount_usd": float(row["amount_usd"]),
                "amount_currency": AMOUNT_CURRENCY,
                "live_score": float(row["live_score"]),
                "volume_z": float(row["volume_z"]),
                "amount_z": float(row["amount_z"]),
                "product_top": None if pd.isna(row.get("product_top")) else str(row["product_top"]),
                "product_top_share": (
                    None if pd.isna(row.get("product_top_share")) else float(row["product_top_share"])
                ),
                "signals": signals,
                "detection_inputs": "live observed fields only; isFraud was not used",
                "not_claimed": [
                    "coordinated abuse",
                    "festive surge",
                    "AttackSpec ground truth",
                ],
            }
        )
    return anomalies


def assert_no_label_leakage(source: str) -> None:
    lowered = source.lower()
    if "evaluation.labels" in lowered or "data.scenarios" in lowered:
        raise RuntimeError("Real-data detection must not use the synthetic calendar classifier.")
    if "isfraud" in lowered and "not used" not in lowered:
        raise RuntimeError("Live real-data detection must not use isFraud.")
