"""Run the Phase 1 detector over the synthetic transaction file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from detection.detector import compute_hourly_windows, detect_spikes, spikes_to_frame

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "data" / "transactions.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "detected_spikes.csv"
WINDOWS_OUTPUT = REPO_ROOT / "data" / "hourly_windows.csv"


def run_detection(input_path: Path, output_path: Path, windows_path: Path | None = None) -> pd.DataFrame:
    transactions = pd.read_csv(input_path)
    spikes = detect_spikes(transactions)
    frame = spikes_to_frame(spikes)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)
    json_path = output_path.with_suffix(".json")
    json_path.write_text(
        json.dumps([spike.to_dict() for spike in spikes], indent=2),
        encoding="utf-8",
    )

    if windows_path is not None:
        windows = compute_hourly_windows(transactions)
        export = windows.copy()
        export["top_skus"] = export["top_skus"].apply(json.dumps)
        export.to_csv(windows_path, index=False)

    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect festive and coordinated spikes.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--windows-output", type=Path, default=WINDOWS_OUTPUT)
    args = parser.parse_args()
    frame = run_detection(args.input, args.output, args.windows_output)
    counts = frame["spike_type"].value_counts().to_dict() if not frame.empty else {}
    print(f"Wrote {len(frame)} spike records to {args.output}")
    print(f"Counts by type: {counts}")


if __name__ == "__main__":
    main()
