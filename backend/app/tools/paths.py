"""Filesystem locations used by investigation tools."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
TRANSACTIONS_PATH = DATA_DIR / "transactions.csv"
DETECTED_SPIKES_PATH = DATA_DIR / "detected_spikes.csv"
HOURLY_WINDOWS_PATH = DATA_DIR / "hourly_windows.csv"
