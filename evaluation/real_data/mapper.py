"""Explicit IEEE-CIS field mapper. Never invents unavailable signals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

SECONDS_PER_HOUR = 3600

WORLD = "REAL PUBLIC DATA"
DATASET_NAME = "IEEE-CIS Fraud Detection"
AMOUNT_CURRENCY = "USD"

TRANSACTION_ID_SOURCE = "TransactionID"
AMOUNT_SOURCES = ("TransactionAmt", "TransactionAMT")
FRAUD_LABEL_SOURCE = "isFraud"
ELAPSED_SOURCE = "TransactionDT"
PRODUCT_SOURCE = "ProductCD"
CARD_SOURCES = ("card1", "card2", "card3", "card4", "card5", "card6")
ADDRESS_SOURCES = ("addr1", "addr2")
EMAIL_PROXY_SOURCE = "P_emaildomain"
DEVICE_SOURCES = ("DeviceType", "DeviceInfo")
ACCOUNT_PROXY_SOURCES = ("card1", "addr1", "P_emaildomain")

REQUIRED_TRANSACTION_SOURCES = (TRANSACTION_ID_SOURCE, FRAUD_LABEL_SOURCE, ELAPSED_SOURCE)

LOCKED_SYNTHETIC_FILENAMES = frozenset(
    {
        "transactions.csv",
        "dataset_meta.json",
        "detected_spikes.csv",
        "detected_spikes.json",
        "hourly_windows.csv",
    }
)

UNAVAILABLE_SIGNALS: dict[str, str] = {
    "ip_address": "IEEE-CIS does not provide real IP addresses.",
    "ip_subnet": "IEEE-CIS does not provide IP subnets.",
    "transaction_status": "IEEE-CIS does not provide success/failed/declined payment status.",
    "sku_id": "IEEE-CIS does not provide real SKU identity.",
    "festive_calendar": "IEEE-CIS does not provide a festive, Diwali, or sale calendar.",
    "attack_spec": "IEEE-CIS does not provide AttackSpec or coordinated-abuse ground truth.",
}

FRAUD_LABEL_NOTE = (
    "isFraud is an evaluation-only delayed label. It is not live evidence and must not "
    "be treated as an observed operational signal."
)
TIMESTAMP_NOTE = (
    "TransactionDT is relative elapsed seconds from an unpublished origin. "
    "It is not a calendar timestamp. Do not derive Diwali, festive sale, day of week, "
    "or a real-world date from it."
)
ACCOUNT_PROXY_NOTE = (
    "account_proxy is an explicit composite of card1 + addr1 + P_emaildomain. "
    "It is not a real account identifier."
)


class RealDataError(RuntimeError):
    """IEEE-CIS adapter failure."""


class MissingRealDatasetError(RealDataError):
    """Raw IEEE-CIS files were not found. The adapter does not download them."""


class InvalidRealDatasetError(RealDataError):
    """Raw IEEE-CIS tables are present but missing required columns."""


def classify_fields() -> dict[str, Any]:
    """Static field classification. Does not read data or invent values."""
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "amount_currency": AMOUNT_CURRENCY,
        "available": {
            "transaction_id": TRANSACTION_ID_SOURCE,
            "amount_usd": " / ".join(AMOUNT_SOURCES),
            "amount": " / ".join(AMOUNT_SOURCES),
            "fraud_label": FRAUD_LABEL_SOURCE,
        },
        "partial_proxy": {
            "elapsed_seconds": {
                "source": ELAPSED_SOURCE,
                "kind": "relative_elapsed_seconds",
                "note": TIMESTAMP_NOTE,
            },
            "relative_hour_bucket": {
                "source": ELAPSED_SOURCE,
                "kind": "floor(TransactionDT / 3600)",
                "note": "Relative hour index only. Not a clock hour or calendar date.",
            },
            "product": PRODUCT_SOURCE,
            "payment_card": list(CARD_SOURCES),
            "account_proxy": {
                "sources": list(ACCOUNT_PROXY_SOURCES),
                "kind": "documented_composite_proxy",
                "note": ACCOUNT_PROXY_NOTE,
            },
            "device_identity": {
                "sources": list(DEVICE_SOURCES),
                "file": "train_identity.csv",
                "note": "Present only when the identity table is supplied and the row joins.",
            },
            "geographic_proxy": list(ADDRESS_SOURCES),
        },
        "unavailable": dict(UNAVAILABLE_SIGNALS),
        "notes": [
            FRAUD_LABEL_NOTE,
            TIMESTAMP_NOTE,
            "TransactionAmt is USD-denominated IEEE-CIS data. Do not display it as INR.",
        ],
    }


def amount_source_column(columns: list[str] | pd.Index) -> str | None:
    present = set(columns)
    for name in AMOUNT_SOURCES:
        if name in present:
            return name
    return None


def validate_required_columns(frame: pd.DataFrame) -> str:
    missing = [name for name in REQUIRED_TRANSACTION_SOURCES if name not in frame.columns]
    amount = amount_source_column(frame.columns)
    if amount is None:
        missing.append(" or ".join(AMOUNT_SOURCES))
    if missing:
        raise InvalidRealDatasetError(
            "IEEE-CIS transaction table is missing required columns: "
            + ", ".join(missing)
            + ". The adapter will not invent those fields."
        )
    return amount


def missing_dataset_message(data_dir: Path) -> str:
    return (
        f"IEEE-CIS raw files were not found under {data_dir}. "
        "This adapter does not download the dataset and will not generate fake results. "
        "Obtain IEEE-CIS Fraud Detection from Kaggle / Vesta manually, respect the "
        "dataset terms, and place train_transaction.csv in data/real/. "
        "See data/real/README.md."
    )


def transaction_file(data_dir: Path) -> Path:
    return Path(data_dir) / "train_transaction.csv"


def identity_file(data_dir: Path) -> Path:
    return Path(data_dir) / "train_identity.csv"


def read_csv_header(path: Path) -> list[str]:
    return list(pd.read_csv(path, nrows=0).columns)


def count_csv_rows(path: Path) -> int:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def discover_files(data_dir: Path) -> dict[str, Path | None]:
    dest = Path(data_dir)
    names = (
        "train_transaction.csv",
        "train_identity.csv",
        "test_transaction.csv",
        "test_identity.csv",
        "sample_submission.csv",
    )
    return {name: dest / name if (dest / name).is_file() else None for name in names}


def labelled_usecols(header: list[str] | pd.Index) -> list[str]:
    wanted = [
        TRANSACTION_ID_SOURCE,
        FRAUD_LABEL_SOURCE,
        ELAPSED_SOURCE,
        PRODUCT_SOURCE,
        EMAIL_PROXY_SOURCE,
        *CARD_SOURCES,
        *ADDRESS_SOURCES,
    ]
    amount = amount_source_column(header)
    if amount is not None:
        wanted.append(amount)
    return [name for name in wanted if name in set(header)]


def identity_usecols(header: list[str] | pd.Index) -> list[str]:
    wanted = [TRANSACTION_ID_SOURCE, *DEVICE_SOURCES]
    return [name for name in wanted if name in set(header)]


def load_raw_tables(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Load official IEEE-CIS CSVs using supported columns only. Does not write anywhere."""
    dest = Path(data_dir)
    tx_path = transaction_file(dest)
    if not tx_path.is_file():
        raise MissingRealDatasetError(missing_dataset_message(dest))
    header = read_csv_header(tx_path)
    transactions = pd.read_csv(tx_path, usecols=labelled_usecols(header))
    validate_required_columns(transactions)
    identity_path = identity_file(dest)
    identity = None
    if identity_path.is_file():
        identity = pd.read_csv(identity_path, usecols=identity_usecols(read_csv_header(identity_path)))
    return transactions, identity


def _series_or_missing(frame: pd.DataFrame, column: str) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series(pd.NA, index=frame.index, dtype="object")


def build_account_proxy(frame: pd.DataFrame) -> pd.Series:
    """Documented composite proxy only. Never claimed to be account_id."""
    parts = [_series_or_missing(frame, name).astype("string") for name in ACCOUNT_PROXY_SOURCES]
    proxy = parts[0].str.cat(parts[1:], sep="|", na_rep="")
    has_card = _series_or_missing(frame, "card1").notna()
    return proxy.where(has_card, pd.NA)


def map_transactions(
    transactions: pd.DataFrame,
    identity: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Map available/partial IEEE-CIS fields. Does not manufacture unavailable columns."""
    amount_col = validate_required_columns(transactions)
    mapped = pd.DataFrame(
        {
            "transaction_id": transactions[TRANSACTION_ID_SOURCE],
            "amount": pd.to_numeric(transactions[amount_col], errors="coerce"),
            "amount_usd": pd.to_numeric(transactions[amount_col], errors="coerce"),
            "amount_currency": AMOUNT_CURRENCY,
            "fraud_label": pd.to_numeric(transactions[FRAUD_LABEL_SOURCE], errors="coerce"),
            "elapsed_seconds": pd.to_numeric(transactions[ELAPSED_SOURCE], errors="coerce"),
            "product": _series_or_missing(transactions, PRODUCT_SOURCE),
            "account_proxy": build_account_proxy(transactions),
            "addr1": _series_or_missing(transactions, "addr1"),
            "addr2": _series_or_missing(transactions, "addr2"),
        }
    )
    mapped["relative_hour_bucket"] = (mapped["elapsed_seconds"] // SECONDS_PER_HOUR).astype("Int64")
    for card in CARD_SOURCES:
        mapped[card] = _series_or_missing(transactions, card)

    if identity is not None and TRANSACTION_ID_SOURCE in identity.columns:
        device_cols = [TRANSACTION_ID_SOURCE, *[name for name in DEVICE_SOURCES if name in identity.columns]]
        devices = identity.loc[:, device_cols].drop_duplicates(subset=[TRANSACTION_ID_SOURCE])
        mapped = mapped.merge(
            devices.rename(columns={TRANSACTION_ID_SOURCE: "transaction_id"}),
            on="transaction_id",
            how="left",
        )
    for device in DEVICE_SOURCES:
        if device not in mapped.columns:
            mapped[device] = pd.NA

    forbidden = {
        "ip_address",
        "ip_subnet",
        "transaction_status",
        "sku_id",
        "timestamp",
        "account_id",
        "device_id",
        "event_type",
        "festive",
        "diwali",
        "day_of_week",
    }
    overlap = forbidden.intersection(mapped.columns)
    if overlap:
        raise RealDataError(f"Mapper must not emit unavailable or calendar fields: {sorted(overlap)}")
    return mapped


def assert_not_synthetic_world_path(path: Path, repo_root: Path | None = None) -> None:
    """Refuse writes that would overwrite seed-42 or seed-2027 artifacts."""
    resolved = Path(path).resolve()
    root = (repo_root or Path(__file__).resolve().parent.parent.parent).resolve()
    data_dir = (root / "data").resolve()
    heldout_dir = (data_dir / "heldout").resolve()
    if resolved.parent == data_dir and resolved.name in LOCKED_SYNTHETIC_FILENAMES:
        raise RealDataError(
            f"Refusing to write {resolved.name} into the locked synthetic data/ directory."
        )
    try:
        resolved.relative_to(heldout_dir)
    except ValueError:
        return
    if resolved.name in LOCKED_SYNTHETIC_FILENAMES:
        raise RealDataError(
            f"Refusing to write {resolved.name} into the locked held-out data/heldout/ directory."
        )
