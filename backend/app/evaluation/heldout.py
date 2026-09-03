"""Build held-out evaluation artifacts using existing generator and detector."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from data.generate_dataset import write_dataset
from detection.run_detection import run_detection
from evaluation.paths import EVALUATION_SEED, HELDOUT_DIR


def generate_heldout_artifacts(
    output_dir: Path | None = None,
    seed: int = EVALUATION_SEED,
) -> dict[str, Any]:
    """Write a second generated world. Never defaults to the seed-42 data/ files."""
    dest = Path(output_dir) if output_dir is not None else HELDOUT_DIR
    if dest.resolve() == HELDOUT_DIR.parent.resolve():
        raise ValueError("Held-out generation must not write into the locked data/ directory")

    dest.mkdir(parents=True, exist_ok=True)
    transactions = write_dataset(output_dir=dest, seed=seed)
    spikes = run_detection(
        input_path=dest / "transactions.csv",
        output_path=dest / "detected_spikes.csv",
        windows_path=dest / "hourly_windows.csv",
    )
    windows_path = dest / "hourly_windows.csv"
    window_count = sum(1 for _ in windows_path.open(encoding="utf-8")) - 1
    return {
        "output_dir": dest,
        "seed": seed,
        "n_transactions": int(len(transactions)),
        "n_spikes": int(len(spikes)),
        "n_hourly_windows": int(window_count),
        "transactions_path": dest / "transactions.csv",
        "meta_path": dest / "dataset_meta.json",
        "spikes_csv_path": dest / "detected_spikes.csv",
        "spikes_json_path": dest / "detected_spikes.json",
        "windows_path": windows_path,
    }
