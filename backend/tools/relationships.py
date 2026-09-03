"""Deterministic shared-infrastructure relationships."""

from __future__ import annotations

from typing import Any

import pandas as pd

from tools.serialize import as_int

DEFAULT_TOP_N = 5


def _group_distinct(
    window: pd.DataFrame,
    source: str,
    target: str,
    top_n: int,
) -> list[dict[str, Any]]:
    if window.empty:
        return []
    grouped = (
        window.groupby(window[source].astype(str), sort=False)[target]
        .nunique()
        .sort_values(ascending=False)
    )
    rows: list[dict[str, Any]] = []
    for source_id, distinct in grouped.head(top_n).items():
        subset = window.loc[window[source].astype(str) == str(source_id)]
        rows.append(
            {
                "entity_id": str(source_id),
                "distinct_related": as_int(distinct),
                "transaction_count": int(len(subset)),
            }
        )
    return rows


def calculate_relationships(
    window: pd.DataFrame,
    top_n: int = DEFAULT_TOP_N,
) -> dict[str, list[dict[str, Any]]]:
    return {
        "device_to_accounts": _group_distinct(window, "device_id", "account_id", top_n),
        "subnet_to_accounts": _group_distinct(window, "ip_subnet", "account_id", top_n),
        "pincode_to_accounts": _group_distinct(window, "pincode", "account_id", top_n),
        "sku_to_accounts": _group_distinct(window, "sku_id", "account_id", top_n),
        "account_to_devices": _group_distinct(window, "account_id", "device_id", top_n),
        "account_to_subnets": _group_distinct(window, "account_id", "ip_subnet", top_n),
    }
