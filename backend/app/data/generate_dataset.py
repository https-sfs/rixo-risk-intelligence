"""Generate a reproducible synthetic transaction dataset.

Produces normal baseline traffic, a legitimate festive volume spike, and
two coordinated abuse clusters with discoverable entity relationships.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from data.catalog import Catalog, Sku, build_catalog, random_ip, subnet_from_prefix
from data.scenarios import (
    ATTACKS,
    BASELINE_ISOLATED_FRAUD_RATE,
    DATASET_END,
    DATASET_START,
    FESTIVE_END,
    FESTIVE_NAME,
    FESTIVE_START,
    FESTIVE_VOLUME_MULTIPLIER,
    WEEKEND_VOLUME_MULTIPLIER,
    AttackSpec,
)
from data.schema import (
    DEFAULT_SEED,
    EVENT_ABUSE,
    EVENT_FESTIVE,
    EVENT_LEGITIMATE,
    PAYMENT_METHODS,
    TRANSACTION_COLUMNS,
)

DATA_DIR = Path(__file__).resolve().parent
LEGIT_PAYMENT_WEIGHTS = np.array([0.56, 0.24, 0.11, 0.09])


def hourly_baseline_rate(hour: int) -> float:
    rates = (
        3.2, 2.6, 2.2, 2.0, 2.2, 3.0,
        7.5, 11.0, 14.5,
        18.5, 20.5, 21.5,
        22.5, 23.5, 22.5,
        21.5, 20.5, 22.0,
        29.0, 31.0, 26.5, 19.5,
        11.5, 6.5,
    )
    return rates[hour]


def _hour_starts(start: datetime, end: datetime) -> list[datetime]:
    hours: list[datetime] = []
    cursor = start
    while cursor < end:
        hours.append(cursor)
        cursor += timedelta(hours=1)
    return hours


def _is_festive(hour_start: datetime) -> bool:
    return FESTIVE_START <= hour_start < FESTIVE_END


def _volume_multiplier(hour_start: datetime) -> float:
    multiplier = 1.0
    if hour_start.weekday() >= 5:
        multiplier *= WEEKEND_VOLUME_MULTIPLIER
    if _is_festive(hour_start):
        multiplier *= FESTIVE_VOLUME_MULTIPLIER
    return multiplier


def _choose(rng: np.random.Generator, values: list[Any] | tuple[Any, ...], p: np.ndarray | None = None) -> Any:
    index = int(rng.choice(len(values), p=p))
    return values[index]


def _round_amount(value: float) -> float:
    return round(max(9.0, value), 2)


def _legit_amount(rng: np.random.Generator, sku: Sku, festive: bool) -> float:
    sigma = 0.28 if festive else 0.32
    lift = 1.08 if festive else 1.0
    amount = float(rng.lognormal(mean=np.log(sku.typical_amount * lift), sigma=sigma))
    return _round_amount(min(amount, sku.typical_amount * 4.5))


def _legit_status(rng: np.random.Generator, festive: bool) -> str:
    success_p = 0.90 if festive else 0.93
    failed_p = 0.06 if festive else 0.04
    draw = float(rng.random())
    if draw < success_p:
        return "success"
    if draw < success_p + failed_p:
        return "failed"
    return "declined"


def _attack_amount(rng: np.random.Generator, spec: AttackSpec) -> float:
    if rng.random() < spec.small_amount_share:
        return _round_amount(float(rng.uniform(29.0, 249.0)))
    return _round_amount(float(rng.uniform(spec.amount_low, spec.amount_high)))


def _attack_status(rng: np.random.Generator, spec: AttackSpec, prior_account_txs: int) -> str:
    success_p = spec.success_rate
    failed_p = spec.failed_rate
    if prior_account_txs == 0:
        success_p *= 0.45
        failed_p *= 0.8
    draw = float(rng.random())
    if draw < success_p:
        return "success"
    if draw < success_p + failed_p:
        return "failed"
    return "declined"


def _build_attack_entities(
    rng: np.random.Generator,
    spec: AttackSpec,
    start_account: int,
    start_device: int,
) -> tuple[list[str], dict[str, str], dict[str, np.ndarray], int, int]:
    accounts = [f"acc_{start_account + i:04d}" for i in range(spec.n_accounts)]
    devices = [f"dev_{start_device + i:04d}" for i in range(spec.n_devices)]
    device_weights = np.array([1.0 / ((i + 1) ** 0.85) for i in range(spec.n_devices)])
    device_weights = device_weights / device_weights.sum()

    account_device: dict[str, str] = {}
    account_weights = np.array([1.0 / ((i + 1) ** 0.55) for i in range(spec.n_accounts)])
    account_weights = account_weights / account_weights.sum()
    for account in accounts:
        account_device[account] = str(_choose(rng, devices, p=device_weights))

    return accounts, account_device, {"accounts": account_weights, "devices": device_weights}, start_account + spec.n_accounts, start_device + spec.n_devices


def _legitimate_row(
    rng: np.random.Generator,
    catalog: Catalog,
    hour_start: datetime,
    festive: bool,
) -> dict[str, Any]:
    account = str(_choose(rng, catalog.accounts, p=catalog.account_weights))
    devices = catalog.account_devices[account]
    device = str(_choose(rng, devices))
    if rng.random() < 0.08:
        prefix = str(_choose(rng, catalog.all_ip_prefixes))
        pincode = str(_choose(rng, catalog.all_pincodes))
    else:
        prefix = str(_choose(rng, catalog.account_ip_prefixes[account]))
        pincode = catalog.account_pincode[account]
        if rng.random() < 0.12:
            pincode = str(_choose(rng, catalog.all_pincodes))

    sku = catalog.skus[int(rng.choice(len(catalog.skus), p=catalog.sku_weights))]
    isolated_fraud = rng.random() < BASELINE_ISOLATED_FRAUD_RATE
    return {
        "timestamp": hour_start + timedelta(seconds=int(rng.integers(0, 3600))),
        "account_id": account,
        "device_id": device,
        "ip_address": random_ip(rng, prefix),
        "ip_subnet": subnet_from_prefix(prefix),
        "pincode": pincode,
        "sku_id": sku.sku_id,
        "amount": _legit_amount(rng, sku, festive),
        "payment_method": str(_choose(rng, PAYMENT_METHODS, p=LEGIT_PAYMENT_WEIGHTS)),
        "transaction_status": _legit_status(rng, festive),
        "fraud_label": 1 if isolated_fraud else 0,
        "event_type": EVENT_FESTIVE if festive else EVENT_LEGITIMATE,
    }


def _attack_row(
    rng: np.random.Generator,
    spec: AttackSpec,
    hour_start: datetime,
    accounts: list[str],
    account_device: dict[str, str],
    account_weights: np.ndarray,
    prior_counts: dict[str, int],
) -> dict[str, Any]:
    account = str(_choose(rng, accounts, p=account_weights))
    device = account_device[account]
    prefix = str(_choose(rng, spec.ip_prefixes, p=_prefix_weights(spec)))
    sku_id = str(_choose(rng, spec.sku_ids, p=np.array(spec.sku_weights)))
    prior = prior_counts.get(account, 0)
    prior_counts[account] = prior + 1
    fraud = rng.random() < spec.isolated_fraud_rate
    return {
        "timestamp": hour_start + timedelta(seconds=int(rng.integers(0, 3600))),
        "account_id": account,
        "device_id": device,
        "ip_address": random_ip(rng, prefix),
        "ip_subnet": subnet_from_prefix(prefix),
        "pincode": str(_choose(rng, spec.pincodes)),
        "sku_id": sku_id,
        "amount": _attack_amount(rng, spec),
        "payment_method": str(_choose(rng, ("card", "UPI"), p=np.array([0.72, 0.28]))),
        "transaction_status": _attack_status(rng, spec, prior),
        "fraud_label": 1 if fraud else 0,
        "event_type": EVENT_ABUSE,
    }


def _prefix_weights(spec: AttackSpec) -> np.ndarray:
    weights = np.array([0.8 if i == 0 else 0.2 / max(len(spec.ip_prefixes) - 1, 1) for i in range(len(spec.ip_prefixes))])
    return weights / weights.sum()


def add_velocity_features(df: pd.DataFrame) -> pd.DataFrame:
    ordered = df.sort_values("timestamp").reset_index(drop=True)
    timestamps = pd.to_datetime(ordered["timestamp"])
    window = pd.Timedelta(hours=1)

    for feature, entity in (
        ("account_tx_count_1h", "account_id"),
        ("device_tx_count_1h", "device_id"),
        ("ip_subnet_tx_count_1h", "ip_subnet"),
    ):
        counts: list[int] = []
        seen: dict[str, deque[pd.Timestamp]] = {}
        for time, key in zip(timestamps, ordered[entity], strict=True):
            bucket = seen.setdefault(str(key), deque())
            cutoff = time - window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            bucket.append(time)
            counts.append(len(bucket))
        ordered[feature] = counts
    return ordered


def generate_transactions(seed: int = DEFAULT_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    catalog = build_catalog(rng)
    rows: list[dict[str, Any]] = []

    next_account = 2000
    next_device = 5000
    attack_state: dict[str, tuple[list[str], dict[str, str], np.ndarray, dict[str, int]]] = {}
    for spec in ATTACKS:
        accounts, account_device, weights, next_account, next_device = _build_attack_entities(
            rng, spec, next_account, next_device
        )
        attack_state[spec.name] = (accounts, account_device, weights["accounts"], {})

    for hour_start in _hour_starts(DATASET_START, DATASET_END):
        festive = _is_festive(hour_start)
        rate = hourly_baseline_rate(hour_start.hour) * _volume_multiplier(hour_start)
        n_legit = int(rng.poisson(rate))
        for _ in range(n_legit):
            rows.append(_legitimate_row(rng, catalog, hour_start, festive))

        for spec in ATTACKS:
            if spec.start <= hour_start < spec.end:
                n_attack = int(rng.poisson(spec.hourly_extra_lambda))
                accounts, account_device, account_weights, prior_counts = attack_state[spec.name]
                for _ in range(n_attack):
                    rows.append(
                        _attack_row(
                            rng,
                            spec,
                            hour_start,
                            accounts,
                            account_device,
                            account_weights,
                            prior_counts,
                        )
                    )

    frame = pd.DataFrame(rows)
    frame = add_velocity_features(frame)
    frame.insert(0, "transaction_id", [f"txn_{i:06d}" for i in range(1, len(frame) + 1)])
    frame["timestamp"] = pd.to_datetime(frame["timestamp"]).dt.strftime("%Y-%m-%dT%H:%M:%S")
    frame["fraud_label"] = frame["fraud_label"].astype(int)
    return frame.loc[:, list(TRANSACTION_COLUMNS)]


def dataset_metadata(df: pd.DataFrame, seed: int) -> dict[str, Any]:
    timestamps = pd.to_datetime(df["timestamp"])
    return {
        "seed": seed,
        "n_transactions": int(len(df)),
        "start": timestamps.min().strftime("%Y-%m-%dT%H:%M:%S"),
        "end": timestamps.max().strftime("%Y-%m-%dT%H:%M:%S"),
        "columns": list(TRANSACTION_COLUMNS),
        "festive_name": FESTIVE_NAME,
        "event_types": sorted(df["event_type"].unique().tolist()),
        "notes": (
            "fraud_label is ground truth for later evaluation. "
            "The detection layer classifies activity windows, not individual payments."
        ),
    }


def write_dataset(output_dir: Path | None = None, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    output = output_dir or DATA_DIR
    output.mkdir(parents=True, exist_ok=True)
    df = generate_transactions(seed)
    df.to_csv(output / "transactions.csv", index=False)
    meta = dataset_metadata(df, seed)
    (output / "dataset_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic transaction dataset.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output-dir", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    df = write_dataset(output_dir=args.output_dir, seed=args.seed)
    print(f"Wrote {len(df)} transactions to {args.output_dir / 'transactions.csv'}")


if __name__ == "__main__":
    main()
