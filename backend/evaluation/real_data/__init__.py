"""IEEE-CIS real-public-data adapter. Separate from seed-42 and seed-2027 worlds."""

from __future__ import annotations

from pathlib import Path

from evaluation.real_data.benchmark import run_benchmark
from evaluation.real_data.coverage import build_coverage_report
from evaluation.real_data.mapper import (
    InvalidRealDatasetError,
    MissingRealDatasetError,
    RealDataError,
    classify_fields,
    map_transactions,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REAL_DATA_DIR = REPO_ROOT / "data" / "real"
TRAIN_TRANSACTION_FILENAME = "train_transaction.csv"
TRAIN_IDENTITY_FILENAME = "train_identity.csv"

WORLD = "REAL PUBLIC DATA"
DATASET_NAME = "IEEE-CIS Fraud Detection"
AMOUNT_CURRENCY = "USD"

__all__ = [
    "AMOUNT_CURRENCY",
    "DATASET_NAME",
    "InvalidRealDatasetError",
    "MissingRealDatasetError",
    "REAL_DATA_DIR",
    "RealDataError",
    "TRAIN_IDENTITY_FILENAME",
    "TRAIN_TRANSACTION_FILENAME",
    "WORLD",
    "build_coverage_report",
    "classify_fields",
    "map_transactions",
    "run_benchmark",
]
