"""Label-free recent-data anomalies from amount and temporal volume only."""

from __future__ import annotations

from typing import Any

import pandas as pd

from evaluation.recent_data.mapper import AMOUNT_CURRENCY, DATASET_NAME, SOURCE_MODEL_OUTPUTS, WORLD

VOLUME_Z = 2.5
AMOUNT_Z = 2.5
MIN_TRANSACTIONS = 20


def _robust_z(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    median = float(values.median()) if values.notna().any() else 0.0
    mad = float((values - median).abs().median()) if values.notna().any() else 0.0
    if mad > 0:
        return 0.6745 * (values - median) / mad
    std = float(values.std(ddof=0)) if values.notna().any() else 0.0
    if std == 0:
        return pd.Series(0.0, index=series.index)
    return (values - values.mean()) / std


def assert_no_source_model_or_label_inputs(frame: pd.DataFrame) -> None:
    leaked = [name for name in (*SOURCE_MODEL_OUTPUTS, "is_fraud", "fraud_label") if name in frame.columns]
    if leaked:
        raise RuntimeError(
            "Recent-data live scoring must not use source-model outputs or fraud labels: "
            + ", ".join(leaked)
        )


def build_hourly(mapped: pd.DataFrame) -> pd.DataFrame:
    work = mapped.dropna(subset=["hour_start"]).copy()
    work["hour_start"] = pd.to_datetime(work["hour_start"]).dt.floor("h")
    rows: list[dict[str, Any]] = []
    for hour, group in work.groupby("hour_start", sort=True):
        total = int(len(group))
        amount = float(group["amount_usd"].sum(min_count=1) or 0.0)
        labelled = None
        labelled_amount = None
        if "fraud_label" in group.columns:
            labels = pd.to_numeric(group["fraud_label"], errors="coerce")
            labelled = int((labels == 1).sum())
            labelled_amount = float(
                group.loc[labels == 1, "amount_usd"].sum(min_count=1) or 0.0
            )
        rows.append(
            {
                "hour_start": pd.Timestamp(hour).isoformat(),
                "transaction_count": total,
                "amount_usd": amount,
                "unique_ip": int(group["ip_address"].nunique()) if "ip_address" in group.columns else 0,
                "labelled_fraud_count": labelled,
                "labelled_fraud_amount_usd": labelled_amount,
                "labelled_fraud_rate": (labelled / total) if labelled is not None and total else None,
            }
        )
    return pd.DataFrame(rows)


def score_hourly(hourly: pd.DataFrame) -> pd.DataFrame:
    live = hourly.drop(
        columns=[name for name in hourly.columns if name.startswith("labelled_")],
        errors="ignore",
    )
    assert_no_source_model_or_label_inputs(live)
    scored = live.copy()
    scored["volume_z"] = _robust_z(scored["transaction_count"])
    scored["amount_z"] = _robust_z(scored["amount_usd"])
    scored["live_score"] = scored[["volume_z", "amount_z"]].max(axis=1)
    volume_hit = scored["volume_z"] >= VOLUME_Z
    amount_hit = scored["amount_z"] >= AMOUNT_Z
    scored["is_anomaly"] = (volume_hit | amount_hit) & (scored["transaction_count"] >= MIN_TRANSACTIONS)
    scored["signal_volume"] = volume_hit
    scored["signal_amount"] = amount_hit
    for name in hourly.columns:
        if name.startswith("labelled_"):
            scored[name] = hourly[name]
    return scored


def detect_anomalies(hourly: pd.DataFrame, limit: int = 20) -> list[dict[str, Any]]:
    scored = score_hourly(hourly)
    flagged = scored.loc[scored["is_anomaly"]].sort_values("live_score", ascending=False).head(limit)
    anomalies: list[dict[str, Any]] = []
    for row in flagged.itertuples(index=False):
        signals: list[str] = []
        kinds: list[str] = []
        if bool(row.signal_volume):
            signals.append("elevated transaction volume")
            kinds.append("Temporal anomaly")
        if bool(row.signal_amount):
            signals.append("elevated transaction amount")
            kinds.append("Amount concentration")
        if not kinds:
            kinds.append("Temporal anomaly")
            signals.append("hour-level volume or amount outlier")
        hour = str(row.hour_start)
        overlay = None
        if hasattr(row, "labelled_fraud_count") and row.labelled_fraud_count is not None:
            overlay = {
                "label": "DELAYED GROUND TRUTH",
                "fraud_count": int(row.labelled_fraud_count),
                "fraud_amount_usd": (
                    float(row.labelled_fraud_amount_usd)
                    if getattr(row, "labelled_fraud_amount_usd", None) is not None
                    else None
                ),
                "fraud_rate": (
                    float(row.labelled_fraud_rate)
                    if getattr(row, "labelled_fraud_rate", None) is not None
                    else None
                ),
            }
        anomalies.append(
            {
                "anomaly_id": f"rct-{pd.Timestamp(hour):%Y%m%d-%H}",
                "kind": kinds[0],
                "kinds": kinds,
                "world": WORLD,
                "dataset": DATASET_NAME,
                "hour_start": hour,
                "transactions": int(row.transaction_count),
                "amount_usd": float(row.amount_usd),
                "amount_currency": AMOUNT_CURRENCY,
                "live_score": float(row.live_score),
                "signals": signals,
                "detection_inputs": "hour volume and amount only; is_fraud and source-model outputs were not used",
                "evaluation_overlay": overlay,
                "not_claimed": [
                    "coordinated abuse",
                    "account takeover",
                    "card testing",
                    "our model detected fraud",
                ],
            }
        )
    return anomalies
