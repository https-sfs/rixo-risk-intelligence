"""Honest IEEE-CIS field coverage. Does not invent values to improve rates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.real_data.mapper import (
    ADDRESS_SOURCES,
    AMOUNT_CURRENCY,
    CARD_SOURCES,
    DATASET_NAME,
    DEVICE_SOURCES,
    ELAPSED_SOURCE,
    FRAUD_LABEL_NOTE,
    FRAUD_LABEL_SOURCE,
    PRODUCT_SOURCE,
    TIMESTAMP_NOTE,
    TRANSACTION_ID_SOURCE,
    UNAVAILABLE_SIGNALS,
    WORLD,
    load_raw_tables,
    validate_required_columns,
)


def _ratio(non_null: int, total: int) -> float | None:
    if total == 0:
        return None
    return non_null / total


def _column_coverage(frame: pd.DataFrame, column: str, total: int) -> dict[str, Any]:
    if column not in frame.columns:
        return {
            "column": column,
            "present_in_file": False,
            "non_null": 0,
            "coverage": 0.0 if total else None,
        }
    non_null = int(frame[column].notna().sum())
    return {
        "column": column,
        "present_in_file": True,
        "non_null": non_null,
        "coverage": _ratio(non_null, total),
    }


def _any_coverage(frame: pd.DataFrame, columns: tuple[str, ...], total: int) -> dict[str, Any]:
    present = [name for name in columns if name in frame.columns]
    if not present:
        return {
            "columns": list(columns),
            "present_in_file": False,
            "non_null": 0,
            "coverage": 0.0 if total else None,
        }
    mask = frame[present[0]].notna()
    for name in present[1:]:
        mask = mask | frame[name].notna()
    non_null = int(mask.sum())
    return {
        "columns": present,
        "present_in_file": True,
        "non_null": non_null,
        "coverage": _ratio(non_null, total),
    }


def build_coverage_report(
    transactions: pd.DataFrame,
    identity: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Coverage from supplied frames. Missingness is left as missing."""
    amount_col = validate_required_columns(transactions)
    total = int(len(transactions))
    identity_rows = int(len(identity)) if identity is not None else 0

    device_frame = transactions
    if identity is not None and TRANSACTION_ID_SOURCE in identity.columns:
        device_cols = [TRANSACTION_ID_SOURCE, *[name for name in DEVICE_SOURCES if name in identity.columns]]
        device_frame = transactions.merge(
            identity.loc[:, device_cols].drop_duplicates(subset=[TRANSACTION_ID_SOURCE]),
            on=TRANSACTION_ID_SOURCE,
            how="left",
        )

    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "amount_currency": AMOUNT_CURRENCY,
        "totals": {
            "transactions": total,
            "identity_rows": identity_rows,
            "identity_file_present": identity is not None,
        },
        "available": {
            "transaction_id": _column_coverage(transactions, TRANSACTION_ID_SOURCE, total),
            "amount": _column_coverage(transactions, amount_col, total),
            "fraud_label": _column_coverage(transactions, FRAUD_LABEL_SOURCE, total),
        },
        "partial_proxy": {
            "timestamp_elapsed": {
                **_column_coverage(transactions, ELAPSED_SOURCE, total),
                "note": TIMESTAMP_NOTE,
            },
            "product": _column_coverage(transactions, PRODUCT_SOURCE, total),
            "payment_card": _any_coverage(transactions, CARD_SOURCES, total),
            "account_proxy": {
                **_any_coverage(transactions, ("card1",), total),
                "kind": "documented_composite_proxy",
                "sources": ["card1", "addr1", "P_emaildomain"],
                "note": "Reported only as a proxy. Not a real account identifier.",
            },
            "device_identity": {
                **_any_coverage(device_frame, DEVICE_SOURCES, total),
                "identity_file_present": identity is not None,
            },
            "geographic_proxy": _any_coverage(transactions, ADDRESS_SOURCES, total),
        },
        "unavailable": {
            name: {"available": False, "reason": reason}
            for name, reason in UNAVAILABLE_SIGNALS.items()
        },
        "notes": [
            FRAUD_LABEL_NOTE,
            TIMESTAMP_NOTE,
            "Missing values are reported as missing. No values were invented to improve coverage.",
            f"Amount coverage uses column {amount_col} and remains {AMOUNT_CURRENCY}.",
        ],
    }


def coverage_from_dir(data_dir: Path) -> dict[str, Any]:
    transactions, identity = load_raw_tables(Path(data_dir))
    return build_coverage_report(transactions, identity)
