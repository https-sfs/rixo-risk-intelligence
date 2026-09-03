"""Build derived IEEE-CIS artifacts once. API reads these instead of the 590k-row ledger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.real_data.detect import detect_anomalies
from evaluation.real_data.evaluate import evaluate_hourly_detector
from evaluation.real_data.evidence import build_anomaly_evidence, build_entity_metrics, build_hour_metrics
from evaluation.real_data.mapper import (
    AMOUNT_CURRENCY,
    DATASET_NAME,
    WORLD,
    assert_not_synthetic_world_path,
    load_raw_tables,
    map_transactions,
)
from evaluation.real_data.profile import write_profile


def _rate_table(mapped: pd.DataFrame, column: str, source: str, kind: str) -> list[dict[str, Any]]:
    if column not in mapped.columns:
        return []
    rows: list[dict[str, Any]] = []
    for value, group in mapped.groupby(mapped[column].astype("string"), dropna=True):
        total = int(len(group))
        fraud = group["fraud_label"] == 1
        rows.append(
            {
                "value": str(value),
                "transactions": total,
                "labelled_fraud_count": int(fraud.sum()),
                "labelled_fraud_rate": float(fraud.mean()) if total else None,
                "amount_usd": float(group["amount_usd"].sum(min_count=1) or 0.0),
                "labelled_fraud_amount_usd": float(group.loc[fraud, "amount_usd"].sum(min_count=1) or 0.0),
                "source": source,
                "signal_kind": kind,
            }
        )
    rows.sort(key=lambda item: item["transactions"], reverse=True)
    return rows


def build_benchmark(mapped: pd.DataFrame, hourly: pd.DataFrame, profile: dict[str, Any]) -> dict[str, Any]:
    total = int(len(mapped))
    fraud = mapped["fraud_label"] == 1
    fraud_count = int(fraud.sum())
    total_amount = float(mapped["amount_usd"].sum(min_count=1) or 0.0)
    fraud_amount = float(mapped.loc[fraud, "amount_usd"].sum(min_count=1) or 0.0)
    legit_amount = float(mapped.loc[~fraud, "amount_usd"].sum(min_count=1) or 0.0)
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "amount_currency": AMOUNT_CURRENCY,
        "source_file": "train_transaction.csv",
        "measurements": {
            "total_transactions": {
                "value": total,
                "source": "train_transaction.csv row count",
            },
            "labelled_fraud_transactions": {
                "value": fraud_count,
                "source": "train_transaction.csv isFraud == 1",
            },
            "legitimate_transactions": {
                "value": int((mapped["fraud_label"] == 0).sum()),
                "source": "train_transaction.csv isFraud == 0",
            },
            "fraud_transaction_rate": {
                "value": (fraud_count / total) if total else None,
                "source": "labelled_fraud_transactions / total_transactions",
            },
            "total_amount_usd": {
                "value": total_amount,
                "source": "sum(TransactionAmt)",
            },
            "labelled_fraud_amount_usd": {
                "value": fraud_amount,
                "source": "sum(TransactionAmt) where isFraud == 1",
            },
            "legitimate_amount_usd": {
                "value": legit_amount,
                "source": "sum(TransactionAmt) where isFraud != 1",
            },
            "fraud_amount_share": {
                "value": (fraud_amount / total_amount) if total_amount else None,
                "source": "labelled_fraud_amount_usd / total_amount_usd",
            },
            "identity_coverage": {
                "value": profile["identity_coverage"],
                "source": "train_identity.csv DeviceType/DeviceInfo join",
            },
        },
        "by_product": _rate_table(mapped, "product", "train_transaction.csv ProductCD", "OBSERVED FROM IEEE-CIS"),
        "by_card4_proxy": _rate_table(mapped, "card4", "train_transaction.csv card4", "PROXY SIGNAL"),
        "by_card6_proxy": _rate_table(mapped, "card6", "train_transaction.csv card6", "PROXY SIGNAL"),
        "by_addr2_proxy": _rate_table(mapped, "addr2", "train_transaction.csv addr2", "PROXY SIGNAL"),
        "by_device_type_proxy": _rate_table(mapped, "DeviceType", "train_identity.csv DeviceType", "PROXY SIGNAL"),
        "hourly_artifact": "hourly_metrics.csv",
        "hourly_buckets": int(len(hourly)),
        "not_calculated": [
            "festive-vs-coordinated classification",
            "coordinated-abuse ground truth",
            "IP subnet concentration",
            "success/failed/declined rate",
            "money saved",
            "ROI",
            "trained-model accuracy",
        ],
        "notes": [
            "Hourly fraud rates are evaluation overlays, not live detector inputs.",
            f"All amounts are {AMOUNT_CURRENCY}.",
        ],
    }


def preprocess(data_dir: Path) -> dict[str, Any]:
    dest = Path(data_dir)
    profile = write_profile(dest, dest / "profile.json")
    transactions, identity = load_raw_tables(dest)
    mapped = map_transactions(transactions, identity)
    hourly = build_hour_metrics(mapped)
    entities = build_entity_metrics(mapped)
    anomalies = detect_anomalies(hourly)
    hourly_path = dest / "hourly_metrics.csv"
    entity_path = dest / "entity_metrics.csv"
    for path in (hourly_path, entity_path):
        assert_not_synthetic_world_path(path)
    hourly.to_csv(hourly_path, index=False)
    entities.to_csv(entity_path, index=False)

    evidence_map: dict[str, Any] = {}
    hourly_index = hourly.set_index("relative_hour_bucket")
    mapped_hours = mapped.dropna(subset=["relative_hour_bucket"])
    for anomaly in anomalies:
        bucket = anomaly["relative_hour_bucket"]
        hour_slice = mapped_hours.loc[mapped_hours["relative_hour_bucket"] == bucket]
        evidence_map[anomaly["anomaly_id"]] = build_anomaly_evidence(
            anomaly,
            hourly_index.loc[bucket],
            hour_slice,
        )

    benchmark = build_benchmark(mapped, hourly, profile)
    evaluation = evaluate_hourly_detector(hourly)

    artifacts = {
        "benchmark.json": benchmark,
        "anomalies.json": {
            "world": WORLD,
            "dataset": DATASET_NAME,
            "count": len(anomalies),
            "anomalies": anomalies,
            "detection": "label-free relative-hour heuristic",
        },
        "evidence.json": evidence_map,
        "evaluation.json": evaluation,
    }
    for name, payload in artifacts.items():
        target = dest / name
        assert_not_synthetic_world_path(target)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "train_transactions": int(len(mapped)),
        "hourly_buckets": int(len(hourly)),
        "anomalies": len(anomalies),
        "artifacts": [
            "profile.json",
            "benchmark.json",
            "hourly_metrics.csv",
            "entity_metrics.csv",
            "anomalies.json",
            "evidence.json",
            "evaluation.json",
        ],
    }


if __name__ == "__main__":
    from evaluation.real_data import REAL_DATA_DIR

    print(json.dumps(preprocess(REAL_DATA_DIR), indent=2))
