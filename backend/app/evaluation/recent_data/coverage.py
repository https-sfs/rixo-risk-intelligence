"""Coverage for the January 2026 collection. Missingness is left as missing."""

from __future__ import annotations

from typing import Any

import pandas as pd

from evaluation.recent_data.mapper import (
    AMOUNT_CURRENCY,
    DATASET_NAME,
    SOURCE_MODEL_OUTPUTS,
    UNAVAILABLE_FAMILIES,
    WORLD,
    january_collection,
    validate_required_columns,
)


def _ratio(non_null: int, total: int) -> float | None:
    if total == 0:
        return None
    return non_null / total


def build_coverage_report(raw: pd.DataFrame) -> dict[str, Any]:
    validate_required_columns(raw)
    collection = january_collection(raw)
    total = int(len(collection))
    present = {
        "transaction_id": int(collection["transaction_id"].notna().sum()),
        "amount": int(pd.to_numeric(collection["amount"], errors="coerce").notna().sum()),
        "is_fraud": int(collection["is_fraud"].notna().sum()),
        "timestamp": int(collection["timestamp"].notna().sum()) if "timestamp" in collection.columns else 0,
        "ip_address": int(collection["ip_address"].notna().sum()) if "ip_address" in collection.columns else 0,
    }
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "amount_currency": AMOUNT_CURRENCY,
        "collection_rows": total,
        "export_rows": int(len(raw)),
        "observed": {
            name: {"non_null": count, "coverage": _ratio(count, total)}
            for name, count in present.items()
        },
        "source_model_output_present": {
            name: name in raw.columns for name in SOURCE_MODEL_OUTPUTS
        },
        "source_model_outputs_excluded_from_analysis": True,
        "unavailable": {
            name: {"available": False, "reason": reason}
            for name, reason in UNAVAILABLE_FAMILIES.items()
        },
        "notes": [
            "Primary coverage is the January collection (test_date present).",
            "Source-model outputs may exist in the file and are not analysis inputs.",
        ],
    }
