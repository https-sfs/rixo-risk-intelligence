"""January 2026 Zenodo recent-public-data adapter. Isolated from seed-42 and IEEE-CIS."""

from __future__ import annotations

from pathlib import Path

from evaluation.recent_data.benchmark import run_benchmark
from evaluation.recent_data.coverage import build_coverage_report
from evaluation.recent_data.mapper import (
    InvalidRecentDatasetError,
    MissingRecentDatasetError,
    RecentDataError,
    classify_fields,
    map_collection,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RECENT_DATA_DIR = REPO_ROOT / "data" / "real_2026"
RAW_CSV_FILENAME = "fraud_tests_export_20260501_080333.csv"

WORLD = "RECENT PUBLIC DATA"
DATASET_NAME = "2026 ONLINE BANKING FRAUD DATA"
AMOUNT_CURRENCY = "USD"
ZENODO_URL = "https://zenodo.org/records/20359708"
ZENODO_DOI = "10.5281/zenodo.20359708"

__all__ = [
    "AMOUNT_CURRENCY",
    "DATASET_NAME",
    "InvalidRecentDatasetError",
    "MissingRecentDatasetError",
    "RECENT_DATA_DIR",
    "RAW_CSV_FILENAME",
    "RecentDataError",
    "WORLD",
    "ZENODO_DOI",
    "ZENODO_URL",
    "build_coverage_report",
    "classify_fields",
    "map_collection",
    "run_benchmark",
]
