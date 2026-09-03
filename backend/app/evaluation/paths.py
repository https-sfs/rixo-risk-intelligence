"""Held-out evaluation locations. Does not change tools/paths.py."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HELDOUT_DIR = REPO_ROOT / "data" / "heldout"
BASELINE_DATA_DIR = REPO_ROOT / "data"

EVALUATION_SEED = 2027
BASELINE_SEED = 42

HELDOUT_TRANSACTIONS_PATH = HELDOUT_DIR / "transactions.csv"
HELDOUT_META_PATH = HELDOUT_DIR / "dataset_meta.json"
HELDOUT_SPIKES_CSV_PATH = HELDOUT_DIR / "detected_spikes.csv"
HELDOUT_SPIKES_JSON_PATH = HELDOUT_DIR / "detected_spikes.json"
HELDOUT_WINDOWS_PATH = HELDOUT_DIR / "hourly_windows.csv"
HELDOUT_EXPOSURE_PATH = HELDOUT_DIR / "exposure_metrics.json"
HELDOUT_INTERVENTION_PATH = HELDOUT_DIR / "intervention_metrics.json"
HELDOUT_LLM_PATH = HELDOUT_DIR / "llm_metrics.json"

BASELINE_TRANSACTIONS_PATH = BASELINE_DATA_DIR / "transactions.csv"
BASELINE_META_PATH = BASELINE_DATA_DIR / "dataset_meta.json"
BASELINE_SPIKES_CSV_PATH = BASELINE_DATA_DIR / "detected_spikes.csv"
BASELINE_SPIKES_JSON_PATH = BASELINE_DATA_DIR / "detected_spikes.json"
BASELINE_WINDOWS_PATH = BASELINE_DATA_DIR / "hourly_windows.csv"
