"""Window-level counts and rates for one spike."""

from __future__ import annotations

from typing import Any

import pandas as pd

from tools.serialize import as_float, as_int

DELAYED_LABEL_NOTE = "delayed ground truth; not a live score"


def calculate_window_metrics(window: pd.DataFrame) -> dict[str, Any]:
    count = int(len(window))
    if count == 0:
        return {
            "transaction_count": 0,
            "total_amount": 0.0,
            "mean_amount": None,
            "status_counts": {"success": 0, "failed": 0, "declined": 0},
            "status_rates": {"success": 0.0, "failed": 0.0, "declined": 0.0},
            "payment_methods": {},
            "fraud_label_rate": {
                "value": None,
                "labelled_count": 0,
                "interpretation": DELAYED_LABEL_NOTE,
            },
        }

    status = window["transaction_status"].value_counts()
    success = as_int(status.get("success", 0))
    failed = as_int(status.get("failed", 0))
    declined = as_int(status.get("declined", 0))
    payments = {
        str(method): as_int(qty)
        for method, qty in window["payment_method"].value_counts().items()
    }
    labelled = as_int(window["fraud_label"].sum())
    return {
        "transaction_count": count,
        "total_amount": as_float(window["amount"].sum(), 2),
        "mean_amount": as_float(window["amount"].mean(), 2),
        "status_counts": {
            "success": success,
            "failed": failed,
            "declined": declined,
        },
        "status_rates": {
            "success": as_float(success / count),
            "failed": as_float(failed / count),
            "declined": as_float(declined / count),
        },
        "payment_methods": payments,
        "fraud_label_rate": {
            "value": as_float(labelled / count),
            "labelled_count": labelled,
            "interpretation": DELAYED_LABEL_NOTE,
        },
    }


def calculate_entity_counts(window: pd.DataFrame) -> dict[str, int]:
    return {
        "unique_accounts": int(window["account_id"].nunique()),
        "unique_devices": int(window["device_id"].nunique()),
        "unique_ips": int(window["ip_address"].nunique()),
        "unique_subnets": int(window["ip_subnet"].nunique()),
        "unique_pincodes": int(window["pincode"].astype(str).nunique()),
        "unique_skus": int(window["sku_id"].nunique()),
    }
