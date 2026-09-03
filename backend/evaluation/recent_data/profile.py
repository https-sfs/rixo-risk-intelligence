"""Machine-generated profile from the actual 2026 CSV."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.recent_data.mapper import (
    AMOUNT_CURRENCY,
    DATASET_NAME,
    RAW_CSV_FILENAME,
    SOURCE_MODEL_OUTPUTS,
    WORLD,
    ZENODO_DOI,
    ZENODO_URL,
    assert_not_locked_path,
    classify_fields,
    discover_csv,
    january_collection,
    load_raw,
)


def _stats(series: pd.Series) -> dict[str, Any]:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return {"non_null": 0, "min": None, "max": None, "mean": None, "median": None}
    return {
        "non_null": int(len(numeric)),
        "min": float(numeric.min()),
        "max": float(numeric.max()),
        "mean": float(numeric.mean()),
        "median": float(numeric.median()),
    }


def build_profile(data_dir: Path) -> dict[str, Any]:
    path = discover_csv(data_dir)
    raw = load_raw(data_dir)
    collection = january_collection(raw)
    extra = raw.loc[~raw.index.isin(collection.index)]
    ts = pd.to_datetime(collection["timestamp"], errors="coerce") if "timestamp" in collection.columns else None
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "source": {
            "title": "A Production-Collected Online Banking Fraud Detection Dataset from a Live Cloud-Based Deep Learning System",
            "zenodo_record": "20359708",
            "doi": ZENODO_DOI,
            "url": ZENODO_URL,
            "license": "CC BY 4.0",
            "collection_period": "2026-01-01 to 2026-01-31",
        },
        "amount_currency": AMOUNT_CURRENCY,
        "file": {
            "name": path.name,
            "expected_name": RAW_CSV_FILENAME,
            "export_rows": int(len(raw)),
            "export_columns": list(raw.columns),
            "export_column_count": int(len(raw.columns)),
            "source_readme_claimed_rows": 56962,
            "source_readme_claimed_columns": 38,
            "source_readme_claimed_fraud": 98,
        },
        "january_collection": {
            "rows": int(len(collection)),
            "fraud_count": int((collection["is_fraud"] == 1).sum()),
            "legitimate_count": int((collection["is_fraud"] == 0).sum()),
            "fraud_rate": float((collection["is_fraud"] == 1).mean()) if len(collection) else None,
            "amount_usd": _stats(collection["amount"]),
            "timestamp_min": None if ts is None or ts.isna().all() else str(ts.min()),
            "timestamp_max": None if ts is None or ts.isna().all() else str(ts.max()),
            "unique_transaction_id": int(collection["transaction_id"].nunique()),
            "unique_ip": int(collection["ip_address"].nunique()) if "ip_address" in collection.columns else 0,
        },
        "excluded_export_rows": {
            "rows": int(len(extra)),
            "reason": "No test_date; timestamps fall outside the stated January 2026 collection.",
            "fraud_count": int((extra["is_fraud"] == 1).sum()) if len(extra) and "is_fraud" in extra else 0,
        },
        "field_classification": classify_fields(),
        "source_model_outputs_in_file": [name for name in SOURCE_MODEL_OUTPUTS if name in raw.columns],
        "documented_but_missing": ["response_time_ms"],
        "notes": [
            "Primary metrics use the January collection only.",
            "is_fraud has source verification bias and is evaluation-only.",
            "This is historical public data, not our live production traffic.",
        ],
    }


def write_profile(data_dir: Path, output_path: Path | None = None) -> dict[str, Any]:
    profile = build_profile(Path(data_dir))
    target = Path(output_path) if output_path is not None else Path(data_dir) / "profile.json"
    assert_not_locked_path(target)
    target.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    profile["output_path"] = str(target)
    return profile
