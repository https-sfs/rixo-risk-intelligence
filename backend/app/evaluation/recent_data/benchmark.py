"""Independent descriptive metrics for the January 2026 collection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation.recent_data.coverage import build_coverage_report
from evaluation.recent_data.detect import build_hourly, detect_anomalies
from evaluation.recent_data.mapper import (
    AMOUNT_CURRENCY,
    DATASET_NAME,
    SOURCE_MODEL_OUTPUTS,
    WORLD,
    ZENODO_DOI,
    ZENODO_URL,
    assert_not_locked_path,
    load_raw,
    map_collection,
)

NOT_CALCULATED = (
    "precision / recall / F1 against is_fraud",
    "PR-AUC",
    "source CNN-LSTM probability as our prediction",
    "money saved",
    "fraud stopped",
    "live production detection",
)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def benchmark_from_raw(raw) -> dict[str, Any]:
    mapped = map_collection(raw)
    hourly = build_hourly(mapped)
    total = int(len(mapped))
    fraud = mapped["fraud_label"] == 1
    fraud_count = int(fraud.sum())
    total_amount = float(mapped["amount_usd"].sum(min_count=1) or 0.0)
    fraud_amount = float(mapped.loc[fraud, "amount_usd"].sum(min_count=1) or 0.0)
    hours = int(mapped["hour_start"].nunique()) if mapped["hour_start"].notna().any() else 0
    unique_ip = int(mapped["ip_address"].nunique()) if "ip_address" in mapped.columns else 0
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "amount_currency": AMOUNT_CURRENCY,
        "source": {"zenodo": ZENODO_URL, "doi": ZENODO_DOI},
        "collection": "January 2026 rows with test_date present",
        "measurements": {
            "total_transactions": {"value": total, "source": "january collection row count"},
            "labelled_fraud_transactions": {
                "value": fraud_count,
                "source": "is_fraud == 1 (delayed ground truth)",
            },
            "fraud_transaction_rate": {
                "value": _rate(fraud_count, total),
                "source": "labelled_fraud_transactions / total_transactions",
            },
            "total_amount_usd": {"value": total_amount, "source": "sum(amount) on January collection"},
            "labelled_fraud_amount_usd": {
                "value": fraud_amount,
                "source": "sum(amount) where is_fraud == 1",
            },
            "temporal_coverage_hours": {
                "value": hours,
                "source": "unique hour_start from timestamp",
            },
            "unique_ip_addresses": {
                "value": unique_ip,
                "source": "ip_address nunique; January IPs are one-per-row",
            },
        },
        "hourly_buckets": int(len(hourly)),
        "coverage": build_coverage_report(raw),
        "anomalies": detect_anomalies(hourly),
        "not_calculated": list(NOT_CALCULATED),
        "source_model_outputs_excluded": list(SOURCE_MODEL_OUTPUTS),
        "notes": [
            "Classifier metrics are omitted because this adapter has no independent predictive score.",
            "Source CNN-LSTM probability is not used as our prediction.",
            f"Amounts are {AMOUNT_CURRENCY} as documented by the source README.",
        ],
    }


def run_benchmark(data_dir: Path, output_path: Path | None = None) -> dict[str, Any]:
    report = benchmark_from_raw(load_raw(data_dir))
    if output_path is not None:
        target = Path(output_path)
        assert_not_locked_path(target)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report = {**report, "output_path": str(target)}
    return report
