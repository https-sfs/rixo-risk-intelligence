"""Hourly window features computed from transaction activity."""

from __future__ import annotations

import pandas as pd

WINDOW_HOURS = 1


def _sku_stats(skus: pd.Series) -> tuple[list[dict[str, int | str]], float, float]:
    if skus.empty:
        return [], 0.0, 0.0
    counts = skus.value_counts()
    total = float(counts.sum())
    shares = counts / total
    top = [
        {"sku_id": str(sku_id), "count": int(count)}
        for sku_id, count in counts.head(3).items()
    ]
    return top, float(shares.iloc[0]), float((shares**2).sum())


def compute_window_features(transactions: pd.DataFrame) -> pd.DataFrame:
    df = transactions.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"] = df["timestamp"].dt.floor("h")
    failed = df["transaction_status"].isin(["failed", "declined"])

    rows: list[dict[str, object]] = []
    for hour, group in df.groupby("hour", sort=True):
        volume = int(len(group))
        unique_accounts = int(group["account_id"].nunique())
        unique_devices = int(group["device_id"].nunique())
        unique_subnets = int(group["ip_subnet"].nunique())
        unique_pincodes = int(group["pincode"].nunique())
        top_skus, top_share, hhi = _sku_stats(group["sku_id"])
        pincode_counts = group["pincode"].value_counts()
        pincode_share = float(pincode_counts.iloc[0] / volume) if volume else 0.0
        rows.append(
            {
                "window_start": hour,
                "window_end": hour + pd.Timedelta(hours=WINDOW_HOURS),
                "volume": volume,
                "fraud_rate": float(group["fraud_label"].mean()) if volume else 0.0,
                "failure_rate": float(failed.loc[group.index].mean()) if volume else 0.0,
                "avg_amount": float(group["amount"].mean()) if volume else 0.0,
                "unique_accounts": unique_accounts,
                "unique_devices": unique_devices,
                "unique_ip_subnets": unique_subnets,
                "unique_pincodes": unique_pincodes,
                "top_skus": top_skus,
                "top_sku_share": top_share,
                "sku_hhi": hhi,
                "accounts_per_device": unique_accounts / max(unique_devices, 1),
                "txs_per_device": volume / max(unique_devices, 1),
                "txs_per_subnet": volume / max(unique_subnets, 1),
                "pincode_concentration": pincode_share,
                "mean_account_velocity": float(group["account_tx_count_1h"].mean()),
                "mean_device_velocity": float(group["device_tx_count_1h"].mean()),
            }
        )

    return pd.DataFrame(rows).sort_values("window_start").reset_index(drop=True)
