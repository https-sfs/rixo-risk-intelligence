"""Honest mapper for the January 2026 Zenodo export. Does not reuse IEEE-CIS assumptions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

WORLD = "RECENT PUBLIC DATA"
DATASET_NAME = "2026 ONLINE BANKING FRAUD DATA"
AMOUNT_CURRENCY = "USD"
ZENODO_URL = "https://zenodo.org/records/20359708"
ZENODO_DOI = "10.5281/zenodo.20359708"
RAW_CSV_FILENAME = "fraud_tests_export_20260501_080333.csv"

REQUIRED_COLUMNS = ("transaction_id", "amount", "is_fraud")
SOURCE_MODEL_OUTPUTS = ("fraud_probability", "risk_level", "confidence", "recommendation")
PCA_FEATURES = tuple(f"v{i}" for i in range(1, 29))
DOCUMENTED_MISSING = {
    "response_time_ms": "Described in the source README; not present in this CSV export.",
}

UNAVAILABLE_FAMILIES = {
    "account_identity": "No account identifiers are provided.",
    "device_identity": "No device identifiers are provided.",
    "merchant_identity": "No merchant identifiers are provided.",
    "sku_identity": "No SKU or product codes are provided. v1–v28 are opaque PCA features.",
    "payment_outcome": "No success / failed / declined payment status is provided.",
    "source_latency": DOCUMENTED_MISSING["response_time_ms"],
}

LOCKED_SYNTHETIC_FILENAMES = frozenset(
    {
        "transactions.csv",
        "dataset_meta.json",
        "detected_spikes.csv",
        "detected_spikes.json",
        "hourly_windows.csv",
    }
)


class RecentDataError(RuntimeError):
    """Recent-public-data adapter failure."""


class MissingRecentDatasetError(RecentDataError):
    """Raw 2026 CSV was not found. The adapter does not download it."""


class InvalidRecentDatasetError(RecentDataError):
    """The CSV is present but missing required transaction columns."""


def classify_fields() -> dict[str, Any]:
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "amount_currency": AMOUNT_CURRENCY,
        "available": {
            "transaction_id": "transaction_id",
            "amount_usd": "amount (source-documented USD)",
            "event_timestamp": "timestamp",
            "collection_date": "test_date",
            "ip_address": "ip_address (as provided; January rows are unique)",
            "pca_features": list(PCA_FEATURES),
            "fraud_label": "is_fraud (delayed ground truth only)",
        },
        "derived": {
            "hour_start": "floor(timestamp to hour)",
            "relative_hour_index": "hours since first January timestamp",
        },
        "proxy": {
            "ip_address": "Network address as supplied. Not a verified customer identity.",
        },
        "source_model_output": {
            name: "Source CNN-LSTM / API output. Never used as our score, label, or metric."
            for name in SOURCE_MODEL_OUTPUTS
        },
        "unavailable": dict(UNAVAILABLE_FAMILIES),
        "notes": [
            "is_fraud is delayed/historical ground truth with source verification bias.",
            "time_value in this export is a Unix timestamp, not the README elapsed-second field.",
            "Primary analysis uses the January collection (test_date present).",
        ],
    }


def missing_dataset_message(data_dir: Path) -> str:
    return (
        f"The January 2026 Zenodo CSV was not found under {data_dir}. "
        "This adapter does not download the dataset. "
        f"Place {RAW_CSV_FILENAME} in data/real_2026/. "
        f"Official record: {ZENODO_URL}"
    )


def discover_csv(data_dir: Path) -> Path:
    dest = Path(data_dir)
    named = dest / RAW_CSV_FILENAME
    if named.is_file():
        return named
    csvs = sorted(dest.glob("*.csv"))
    if not csvs:
        raise MissingRecentDatasetError(missing_dataset_message(dest))
    return csvs[0]


def validate_required_columns(frame: pd.DataFrame) -> None:
    missing = [name for name in REQUIRED_COLUMNS if name not in frame.columns]
    if missing:
        raise InvalidRecentDatasetError(
            "Recent-data table is missing required columns: "
            + ", ".join(missing)
            + ". The adapter will not invent those fields."
        )


def load_raw(data_dir: Path) -> pd.DataFrame:
    path = discover_csv(data_dir)
    frame = pd.read_csv(path)
    validate_required_columns(frame)
    return frame


def january_collection(frame: pd.DataFrame) -> pd.DataFrame:
    """Official published collection: rows with test_date in January 2026.

    If test_date is absent (tiny fixtures), keep rows whose timestamp falls in January 2026.
    """
    if "test_date" in frame.columns:
        dated = pd.to_datetime(frame["test_date"], errors="coerce")
        selected = frame.loc[dated.notna()].copy()
        if not selected.empty:
            return selected
    if "timestamp" in frame.columns:
        ts = pd.to_datetime(frame["timestamp"], errors="coerce")
        mask = (ts.dt.year == 2026) & (ts.dt.month == 1)
        selected = frame.loc[mask].copy()
        if not selected.empty:
            return selected
    return frame.copy()


def map_collection(frame: pd.DataFrame) -> pd.DataFrame:
    """Map observed/derived fields. Drops source-model outputs from the analysis frame."""
    validate_required_columns(frame)
    collection = january_collection(frame)
    timestamp = (
        pd.to_datetime(collection["timestamp"], errors="coerce")
        if "timestamp" in collection.columns
        else pd.Series(pd.NaT, index=collection.index)
    )
    mapped = pd.DataFrame(
        {
            "transaction_id": collection["transaction_id"],
            "amount_usd": pd.to_numeric(collection["amount"], errors="coerce"),
            "amount_currency": AMOUNT_CURRENCY,
            "fraud_label": pd.to_numeric(collection["is_fraud"], errors="coerce"),
            "event_timestamp": timestamp,
            "hour_start": timestamp.dt.floor("h"),
        }
    )
    if "ip_address" in collection.columns:
        mapped["ip_address"] = collection["ip_address"]
    leaked = [name for name in SOURCE_MODEL_OUTPUTS if name in mapped.columns]
    if leaked:
        raise RecentDataError(f"Mapped analysis frame must not include source-model outputs: {leaked}")
    return mapped


def assert_not_locked_path(path: Path, repo_root: Path | None = None) -> None:
    resolved = Path(path).resolve()
    root = (repo_root or Path(__file__).resolve().parent.parent.parent).resolve()
    data_dir = (root / "data").resolve()
    heldout = (data_dir / "heldout").resolve()
    ieee = (data_dir / "real").resolve()
    if resolved.parent == data_dir and resolved.name in LOCKED_SYNTHETIC_FILENAMES:
        raise RecentDataError(f"Refusing to write {resolved.name} into the locked synthetic data/ directory.")
    for locked in (heldout, ieee):
        try:
            resolved.relative_to(locked)
        except ValueError:
            continue
        raise RecentDataError(f"Refusing to write recent-data artifacts into {locked}.")
