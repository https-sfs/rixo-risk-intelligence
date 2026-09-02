from __future__ import annotations

import pandas as pd

from data.generate_dataset import generate_transactions
from data.scenarios import ATTACKS, FESTIVE_END, FESTIVE_START
from data.schema import EVENT_ABUSE, EVENT_FESTIVE, TRANSACTION_COLUMNS


def test_generation_is_reproducible() -> None:
    first = generate_transactions(seed=42)
    second = generate_transactions(seed=42)
    pd.testing.assert_frame_equal(first, second)


def test_dataset_has_approximately_10000_records() -> None:
    df = generate_transactions(seed=42)
    assert 9_000 <= len(df) <= 11_000


def test_required_columns_exist() -> None:
    df = generate_transactions(seed=42)
    assert list(df.columns) == list(TRANSACTION_COLUMNS)


def test_legitimate_festive_spike_exists() -> None:
    df = generate_transactions(seed=42)
    timestamps = pd.to_datetime(df["timestamp"])
    festive = df[df["event_type"] == EVENT_FESTIVE]
    festive_hours = festive.assign(hour=pd.to_datetime(festive["timestamp"]).dt.floor("h"))
    baseline = df[(timestamps < FESTIVE_START) & (df["event_type"] != EVENT_ABUSE)]

    assert festive.shape[0] >= 800
    assert festive["account_id"].nunique() >= 250
    assert festive["device_id"].nunique() >= 200
    assert festive["pincode"].nunique() >= 20
    assert festive["ip_subnet"].nunique() >= 15
    assert festive["sku_id"].nunique() >= 20
    assert float(festive["fraud_label"].mean()) < 0.05
    assert float((festive["transaction_status"] == "success").mean()) >= 0.85

    festive_hourly = festive_hours.groupby("hour").size()
    baseline_hourly = (
        baseline.assign(hour=pd.to_datetime(baseline["timestamp"]).dt.floor("h"))
        .groupby("hour")
        .size()
    )
    assert festive_hourly.mean() > baseline_hourly.mean() * 1.6
    assert timestamps.between(FESTIVE_START, FESTIVE_END, inclusive="left").any()


def test_coordinated_abuse_clusters_exist() -> None:
    df = generate_transactions(seed=42)
    abuse = df[df["event_type"] == EVENT_ABUSE]
    assert abuse.shape[0] >= 200
    assert pd.to_datetime(abuse["timestamp"]).dt.date.nunique() >= 2
    assert abuse["device_id"].nunique() < abuse["account_id"].nunique() * 0.25
    assert abuse["ip_subnet"].nunique() <= 4
    assert abuse["sku_id"].nunique() <= 4
    assert float((abuse["transaction_status"] != "success").mean()) >= 0.35

    for spec in ATTACKS:
        cluster = abuse[
            pd.to_datetime(abuse["timestamp"]).between(spec.start, spec.end, inclusive="left")
        ]
        assert cluster.shape[0] >= 80
        assert cluster["account_id"].nunique() > cluster["device_id"].nunique()
        assert cluster["ip_subnet"].nunique() <= len(spec.ip_prefixes)
        assert set(cluster["sku_id"]).issubset(set(spec.sku_ids))
