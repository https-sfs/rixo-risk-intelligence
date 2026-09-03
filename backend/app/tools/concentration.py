"""Top-N concentration of shared infrastructure."""

from __future__ import annotations

from typing import Any

import pandas as pd

from tools.serialize import as_float, as_int

DEFAULT_TOP_N = 5


def _entity_rows(
    window: pd.DataFrame,
    entity: str,
    *,
    account_col: str | None = "account_id",
    top_n: int = DEFAULT_TOP_N,
) -> list[dict[str, Any]]:
    if window.empty:
        return []
    total = float(len(window))
    counts = window[entity].astype(str).value_counts()
    rows: list[dict[str, Any]] = []
    for entity_id, tx_count in counts.head(top_n).items():
        subset = window.loc[window[entity].astype(str) == str(entity_id)]
        item: dict[str, Any] = {
            "entity_id": str(entity_id),
            "transaction_count": as_int(tx_count),
            "share_of_transactions": as_float(float(tx_count) / total),
        }
        if account_col is not None:
            item["distinct_accounts"] = int(subset[account_col].nunique())
        rows.append(item)
    return rows


def calculate_concentration(
    window: pd.DataFrame,
    top_n: int = DEFAULT_TOP_N,
) -> dict[str, list[dict[str, Any]]]:
    return {
        "devices": _entity_rows(window, "device_id", top_n=top_n),
        "subnets": _entity_rows(window, "ip_subnet", top_n=top_n),
        "pincodes": _entity_rows(window, "pincode", top_n=top_n),
        "skus": _entity_rows(window, "sku_id", top_n=top_n),
    }
