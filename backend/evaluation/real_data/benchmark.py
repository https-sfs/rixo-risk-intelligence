"""IEEE-CIS measurements for signals the dataset actually supports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation.real_data.coverage import build_coverage_report
from evaluation.real_data.mapper import (
    AMOUNT_CURRENCY,
    DATASET_NAME,
    FRAUD_LABEL_NOTE,
    TIMESTAMP_NOTE,
    WORLD,
    assert_not_synthetic_world_path,
    load_raw_tables,
    map_transactions,
)

REAL_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "real"

NOT_CALCULATED = (
    "festive-vs-coordinated classification",
    "coordinated-abuse ground truth",
    "IP subnet concentration",
    "success/failed/declined rate",
    "synthetic SKU targeting",
    "intervention effectiveness",
    "money saved",
    "money prevented",
    "ROI",
)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def benchmark_from_frames(
    transactions,
    identity=None,
) -> dict[str, Any]:
    """Compute labelled IEEE-CIS measurements from already-loaded frames."""
    mapped = map_transactions(transactions, identity)
    coverage = build_coverage_report(transactions, identity)
    total = int(len(mapped))
    fraud_mask = mapped["fraud_label"] == 1
    fraud_count = int(fraud_mask.sum())
    fraud_amount = float(mapped.loc[fraud_mask, "amount"].sum(min_count=1) or 0.0)

    hourly_rows: list[dict[str, Any]] = []
    if mapped["relative_hour_bucket"].notna().any():
        grouped = mapped.dropna(subset=["relative_hour_bucket"]).groupby(
            "relative_hour_bucket",
            sort=True,
        )
        for bucket, group in grouped:
            labelled = group["fraud_label"] == 1
            count = int(len(group))
            labelled_count = int(labelled.sum())
            hourly_rows.append(
                {
                    "relative_hour_bucket": int(bucket),
                    "transaction_count": count,
                    "labelled_fraud_count": labelled_count,
                    "labelled_fraud_rate": _rate(labelled_count, count),
                    "labelled_fraud_amount_usd": float(
                        group.loc[labelled, "amount"].sum(min_count=1) or 0.0
                    ),
                }
            )

    device_type_non_null = int(mapped["DeviceType"].notna().sum()) if "DeviceType" in mapped.columns else 0
    device_info_non_null = int(mapped["DeviceInfo"].notna().sum()) if "DeviceInfo" in mapped.columns else 0
    identity_join = (
        int((mapped["DeviceType"].notna() | mapped["DeviceInfo"].notna()).sum())
        if {"DeviceType", "DeviceInfo"}.issubset(mapped.columns)
        else 0
    )

    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "amount_currency": AMOUNT_CURRENCY,
        "measurements": {
            "total_transactions": total,
            "labelled_fraud_transactions": fraud_count,
            "fraud_transaction_rate": _rate(fraud_count, total),
            "labelled_fraud_amount_usd": fraud_amount,
            "hourly_transaction_volume": hourly_rows,
            "hourly_isFraud_rate": [
                {
                    "relative_hour_bucket": row["relative_hour_bucket"],
                    "labelled_fraud_rate": row["labelled_fraud_rate"],
                }
                for row in hourly_rows
            ],
            "identity_coverage": {
                "identity_file_present": identity is not None,
                "transactions_with_device_identity": identity_join,
                "device_type_coverage": _rate(device_type_non_null, total),
                "device_info_coverage": _rate(device_info_non_null, total),
            },
        },
        "coverage": coverage,
        "not_calculated": list(NOT_CALCULATED),
        "notes": [
            FRAUD_LABEL_NOTE,
            TIMESTAMP_NOTE,
            f"All amounts are {AMOUNT_CURRENCY}. Do not display them as INR.",
            "Hourly series use relative_hour_bucket from TransactionDT. No calendar date is assigned.",
        ],
    }


def run_benchmark(
    data_dir: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Run only when raw IEEE-CIS files exist. Never writes synthetic artifacts."""
    dest = Path(data_dir) if data_dir is not None else REAL_DATA_DIR
    transactions, identity = load_raw_tables(dest)
    report = benchmark_from_frames(transactions, identity)
    if output_path is not None:
        target = Path(output_path)
        assert_not_synthetic_world_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report = {**report, "output_path": str(target)}
    return report


if __name__ == "__main__":
    try:
        result = run_benchmark()
    except Exception as exc:  # noqa: BLE001 — CLI must surface the adapter instruction
        raise SystemExit(str(exc)) from exc
    print(json.dumps({
        "world": result["world"],
        "dataset": result["dataset"],
        "amount_currency": result["amount_currency"],
        "total_transactions": result["measurements"]["total_transactions"],
        "labelled_fraud_transactions": result["measurements"]["labelled_fraud_transactions"],
        "fraud_transaction_rate": result["measurements"]["fraud_transaction_rate"],
        "labelled_fraud_amount_usd": result["measurements"]["labelled_fraud_amount_usd"],
        "not_calculated": result["not_calculated"],
    }, indent=2))
