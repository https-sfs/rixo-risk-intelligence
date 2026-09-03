"""Machine-generated IEEE-CIS profile from the actual downloaded files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.real_data.mapper import (
    AMOUNT_CURRENCY,
    DATASET_NAME,
    DEVICE_SOURCES,
    ELAPSED_SOURCE,
    FRAUD_LABEL_SOURCE,
    PRODUCT_SOURCE,
    TIMESTAMP_NOTE,
    TRANSACTION_ID_SOURCE,
    UNAVAILABLE_SIGNALS,
    WORLD,
    amount_source_column,
    assert_not_synthetic_world_path,
    count_csv_rows,
    discover_files,
    labelled_usecols,
    load_raw_tables,
    map_transactions,
    read_csv_header,
)

SOURCE = "Kaggle / Vesta"
SAMPLE_SUBMISSION_NOTE = (
    "sample_submission.csv is a competition template. Its isFraud values are not "
    "ground truth and are not used for evaluation."
)


def _file_entry(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"present": False}
    header = read_csv_header(path)
    return {
        "present": True,
        "name": path.name,
        "rows": count_csv_rows(path),
        "columns": len(header),
        "column_names_head": header[:25],
        "has_isFraud": FRAUD_LABEL_SOURCE in header,
    }


def _series_stats(series: pd.Series) -> dict[str, Any]:
    numeric = pd.to_numeric(series, errors="coerce")
    present = numeric.dropna()
    if present.empty:
        return {"non_null": 0, "min": None, "max": None, "mean": None, "median": None}
    return {
        "non_null": int(present.shape[0]),
        "min": float(present.min()),
        "max": float(present.max()),
        "mean": float(present.mean()),
        "median": float(present.median()),
    }


def build_profile(data_dir: Path) -> dict[str, Any]:
    dest = Path(data_dir)
    files = discover_files(dest)
    train_tx = files["train_transaction.csv"]
    if train_tx is None:
        from evaluation.real_data.mapper import MissingRealDatasetError, missing_dataset_message

        raise MissingRealDatasetError(missing_dataset_message(dest))

    train_header = read_csv_header(train_tx)
    amount_col = amount_source_column(train_header)
    transactions, identity = load_raw_tables(dest)
    mapped = map_transactions(transactions, identity)
    total = int(len(mapped))
    fraud_count = int((mapped["fraud_label"] == 1).sum())
    legitimate_count = int((mapped["fraud_label"] == 0).sum())
    unlabelled = total - fraud_count - legitimate_count

    test_entry = _file_entry(files["test_transaction.csv"])
    train_identity_entry = _file_entry(files["train_identity.csv"])
    test_identity_entry = _file_entry(files["test_identity.csv"])
    submission_entry = _file_entry(files["sample_submission.csv"])

    missingness = {}
    for column in labelled_usecols(train_header):
        missingness[column] = {
            "non_null": int(transactions[column].notna().sum()) if column in transactions.columns else 0,
            "coverage": (
                float(transactions[column].notna().mean()) if column in transactions.columns and total else None
            ),
        }

    identity_coverage = {
        "train_identity_rows": train_identity_entry.get("rows"),
        "transactions_with_device_type": int(mapped["DeviceType"].notna().sum()),
        "transactions_with_device_info": int(mapped["DeviceInfo"].notna().sum()),
        "transactions_with_any_device_identity": int(
            (mapped["DeviceType"].notna() | mapped["DeviceInfo"].notna()).sum()
        ),
        "coverage": float((mapped["DeviceType"].notna() | mapped["DeviceInfo"].notna()).mean()) if total else None,
    }

    product_values = (
        sorted(mapped["product"].dropna().astype(str).unique().tolist())
        if "product" in mapped.columns
        else []
    )

    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "source": SOURCE,
        "amount_currency": AMOUNT_CURRENCY,
        "files": {
            "train_transaction.csv": _file_entry(train_tx),
            "train_identity.csv": train_identity_entry,
            "test_transaction.csv": test_entry,
            "test_identity.csv": test_identity_entry,
            "sample_submission.csv": submission_entry,
        },
        "train_labelled": {
            "transactions": total,
            "columns_in_raw_file": len(train_header),
            "columns_loaded": list(transactions.columns),
            "fraud_count": fraud_count,
            "legitimate_count": legitimate_count,
            "unlabelled_count": unlabelled,
            "fraud_rate": (fraud_count / total) if total else None,
            "amount_column": amount_col,
            "amount_usd": _series_stats(mapped["amount_usd"]),
            "elapsed_seconds": _series_stats(mapped["elapsed_seconds"]),
            "relative_hour_bucket": _series_stats(mapped["relative_hour_bucket"]),
            "product_values": product_values,
            "card_fields_present": [name for name in ("card1", "card2", "card3", "card4", "card5", "card6") if name in transactions.columns],
            "addr_fields_present": [name for name in ("addr1", "addr2") if name in transactions.columns],
        },
        "identity_coverage": identity_coverage,
        "missingness": missingness,
        "available_signals": {
            "transaction_id": TRANSACTION_ID_SOURCE,
            "amount_usd": amount_col,
            "fraud_label_evaluation_only": FRAUD_LABEL_SOURCE,
        },
        "partial_proxy_signals": {
            "elapsed_seconds": ELAPSED_SOURCE,
            "relative_hour_bucket": f"floor({ELAPSED_SOURCE}/3600)",
            "product": PRODUCT_SOURCE,
            "card_proxy": ["card1", "card2", "card3", "card4", "card5", "card6"],
            "account_proxy": ["card1", "addr1", "P_emaildomain"],
            "device_proxy": list(DEVICE_SOURCES),
            "geographic_proxy": ["addr1", "addr2"],
        },
        "unavailable_signals": dict(UNAVAILABLE_SIGNALS),
        "timestamp_limitations": TIMESTAMP_NOTE,
        "notes": [
            "Fraud labels exist only on train_transaction.csv.",
            "test_transaction.csv has no isFraud column and is not used for labelled metrics.",
            SAMPLE_SUBMISSION_NOTE,
            "There is no trained ML fraud model in this repository.",
            f"Amounts are {AMOUNT_CURRENCY}.",
        ],
    }


def write_profile(data_dir: Path, output_path: Path | None = None) -> dict[str, Any]:
    dest = Path(data_dir)
    profile = build_profile(dest)
    target = Path(output_path) if output_path is not None else dest / "profile.json"
    assert_not_synthetic_world_path(target)
    target.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    profile["output_path"] = str(target)
    return profile


if __name__ == "__main__":
    from evaluation.real_data import REAL_DATA_DIR

    result = write_profile(REAL_DATA_DIR)
    print(json.dumps({
        "train_transactions": result["train_labelled"]["transactions"],
        "fraud_count": result["train_labelled"]["fraud_count"],
        "fraud_rate": result["train_labelled"]["fraud_rate"],
        "test_transactions": result["files"]["test_transaction.csv"].get("rows"),
        "output_path": result["output_path"],
    }, indent=2))
