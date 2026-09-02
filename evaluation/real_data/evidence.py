"""Aggregate investigation evidence for one real-data anomaly. No ledger dump."""

from __future__ import annotations

from typing import Any

import pandas as pd

from evaluation.real_data.mapper import AMOUNT_CURRENCY, DATASET_NAME, UNAVAILABLE_SIGNALS, WORLD

OBSERVED = "OBSERVED FROM IEEE-CIS"
DERIVED = "DERIVED FROM IEEE-CIS"
PROXY = "PROXY SIGNAL"
UNAVAILABLE = "UNAVAILABLE"
EVALUATION_ONLY = "DELAYED GROUND TRUTH"


def _top_share(series: pd.Series, total: int) -> dict[str, Any] | None:
    counts = series.dropna().astype(str).value_counts()
    if counts.empty or total == 0:
        return None
    return {
        "value": str(counts.index[0]),
        "count": int(counts.iloc[0]),
        "share": float(counts.iloc[0] / total),
        "unique": int(counts.shape[0]),
    }


def build_hour_metrics(mapped: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped = mapped.dropna(subset=["relative_hour_bucket"]).groupby("relative_hour_bucket", sort=True)
    for bucket, group in grouped:
        total = int(len(group))
        fraud = group["fraud_label"] == 1
        product = _top_share(group["product"], total)
        card4 = _top_share(group["card4"], total) if "card4" in group.columns else None
        addr2 = _top_share(group["addr2"], total) if "addr2" in group.columns else None
        device = _top_share(group["DeviceType"], total) if "DeviceType" in group.columns else None
        rows.append(
            {
                "relative_hour_bucket": int(bucket),
                "transaction_count": total,
                "amount_usd": float(group["amount_usd"].sum(min_count=1) or 0.0),
                "product_top": None if product is None else product["value"],
                "product_top_share": None if product is None else product["share"],
                "unique_product": 0 if product is None else product["unique"],
                "unique_card1_proxy": int(group["card1"].nunique(dropna=True)) if "card1" in group.columns else 0,
                "card4_top": None if card4 is None else card4["value"],
                "card4_top_share": None if card4 is None else card4["share"],
                "addr2_top": None if addr2 is None else addr2["value"],
                "addr2_top_share": None if addr2 is None else addr2["share"],
                "identity_coverage": float(group["DeviceType"].notna().mean()) if "DeviceType" in group.columns else 0.0,
                "device_type_top": None if device is None else device["value"],
                "device_type_top_share": None if device is None else device["share"],
                "labelled_fraud_count": int(fraud.sum()),
                "labelled_fraud_rate": float(fraud.mean()) if total else None,
                "labelled_fraud_amount_usd": float(group.loc[fraud, "amount_usd"].sum(min_count=1) or 0.0),
            }
        )
    return pd.DataFrame(rows)


def build_entity_metrics(mapped: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    specs = (
        ("product", "product", OBSERVED),
        ("card4", "card4_proxy", PROXY),
        ("card6", "card6_proxy", PROXY),
        ("addr2", "addr2_proxy", PROXY),
        ("DeviceType", "device_type_proxy", PROXY),
    )
    for column, entity_type, kind in specs:
        if column not in mapped.columns:
            continue
        grouped = mapped.groupby(mapped[column].astype("string"), dropna=True)
        rows = []
        for value, group in grouped:
            total = int(len(group))
            fraud = group["fraud_label"] == 1
            rows.append(
                {
                    "entity_type": entity_type,
                    "entity_value": str(value),
                    "signal_kind": kind,
                    "transaction_count": total,
                    "amount_usd": float(group["amount_usd"].sum(min_count=1) or 0.0),
                    "labelled_fraud_count": int(fraud.sum()),
                    "labelled_fraud_rate": float(fraud.mean()) if total else None,
                    "labelled_fraud_amount_usd": float(group.loc[fraud, "amount_usd"].sum(min_count=1) or 0.0),
                }
            )
        if rows:
            frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def build_anomaly_evidence(
    anomaly: dict[str, Any],
    hour_row: pd.Series,
    hour_slice: pd.DataFrame,
) -> dict[str, Any]:
    total = int(len(hour_slice))
    fraud = hour_slice["fraud_label"] == 1
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "amount_currency": AMOUNT_CURRENCY,
        "anomaly_id": anomaly["anomaly_id"],
        "kind": "REAL DATA ANOMALY",
        "relative_hour_bucket": anomaly["relative_hour_bucket"],
        "live_evidence": {
            "transaction_count": {
                "value": total,
                "label": OBSERVED,
                "source": "train_transaction.csv row count in relative_hour_bucket",
            },
            "amount_usd": {
                "value": float(hour_slice["amount_usd"].sum(min_count=1) or 0.0),
                "label": OBSERVED,
                "source": "train_transaction.csv TransactionAmt",
            },
            "product_concentration": {
                "value": _top_share(hour_slice["product"], total),
                "label": DERIVED,
                "source": "share of train_transaction.csv ProductCD in the hour window",
            },
            "card_proxy_concentration": {
                "value": _top_share(hour_slice["card4"], total) if "card4" in hour_slice.columns else None,
                "label": PROXY,
                "source": "train_transaction.csv card4",
            },
            "address_proxy_concentration": {
                "value": _top_share(hour_slice["addr2"], total) if "addr2" in hour_slice.columns else None,
                "label": PROXY,
                "source": "train_transaction.csv addr2",
            },
            "device_proxy": {
                "value": _top_share(hour_slice["DeviceType"], total) if "DeviceType" in hour_slice.columns else None,
                "label": PROXY,
                "source": "train_identity.csv DeviceType",
            },
            "identity_coverage": {
                "value": float(hour_slice["DeviceType"].notna().mean()) if "DeviceType" in hour_slice.columns else 0.0,
                "label": PROXY,
                "source": "train_identity.csv join on TransactionID",
            },
            "temporal_anomaly": {
                "value": {
                    "relative_hour_bucket": anomaly["relative_hour_bucket"],
                    "live_score": anomaly["live_score"],
                    "signals": anomaly["signals"],
                },
                "label": DERIVED,
                "source": "evaluation.real_data.detect live score",
            },
        },
        "evaluation_overlay": {
            "note": "isFraud is delayed ground truth. It was not used to detect this anomaly.",
            "label": EVALUATION_ONLY,
            "fraud_count": int(fraud.sum()),
            "fraud_rate": float(fraud.mean()) if total else None,
            "fraud_amount_usd": float(hour_slice.loc[fraud, "amount_usd"].sum(min_count=1) or 0.0),
            "source": "train_transaction.csv isFraud",
        },
        "unavailable": {
            name: {"label": UNAVAILABLE, "reason": reason}
            for name, reason in UNAVAILABLE_SIGNALS.items()
        },
        "missing_signal_warnings": [
            "IP address and subnet are unavailable.",
            "Payment success/failure/decline is unavailable.",
            "True account, device, and SKU identities are unavailable.",
            "TransactionDT is a relative elapsed-time field, not a calendar date.",
        ],
        "hour_summary": {
            "transaction_count": int(hour_row["transaction_count"]),
            "amount_usd": float(hour_row["amount_usd"]),
            "product_top": None if pd.isna(hour_row.get("product_top")) else str(hour_row["product_top"]),
            "product_top_share": (
                None if pd.isna(hour_row.get("product_top_share")) else float(hour_row["product_top_share"])
            ),
        },
    }
