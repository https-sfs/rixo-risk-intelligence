"""Velocity summaries from existing 1-hour count columns."""

from __future__ import annotations

from typing import Any

import pandas as pd

from tools.serialize import as_float, as_int

DEFAULT_TOP_N = 5


def _series_summary(
    window: pd.DataFrame,
    column: str,
    entity: str,
    top_n: int,
) -> dict[str, Any]:
    if window.empty:
        return {
            "mean": None,
            "maximum": None,
            "top_entities": [],
        }
    values = window[column]
    ranked = window.sort_values(column, ascending=False).head(top_n)
    top_entities = [
        {
            "entity_id": str(row[entity]),
            "value": as_int(row[column]),
            "transaction_id": str(row["transaction_id"]),
        }
        for _, row in ranked.iterrows()
    ]
    return {
        "mean": as_float(values.mean()),
        "maximum": as_int(values.max()),
        "top_entities": top_entities,
    }


def calculate_velocity(
    window: pd.DataFrame,
    top_n: int = DEFAULT_TOP_N,
) -> dict[str, Any]:
    return {
        "account_tx_count_1h": _series_summary(window, "account_tx_count_1h", "account_id", top_n),
        "device_tx_count_1h": _series_summary(window, "device_tx_count_1h", "device_id", top_n),
        "ip_subnet_tx_count_1h": _series_summary(
            window, "ip_subnet_tx_count_1h", "ip_subnet", top_n
        ),
    }
