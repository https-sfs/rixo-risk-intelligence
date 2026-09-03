"""Generate held-out evaluation artifacts. Does not overwrite the seed-42 baseline."""

from __future__ import annotations

import argparse
from pathlib import Path

from evaluation.heldout import generate_heldout_artifacts
from evaluation.paths import EVALUATION_SEED, HELDOUT_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Phase 7 held-out artifact set.")
    parser.add_argument("--seed", type=int, default=EVALUATION_SEED)
    parser.add_argument("--output-dir", type=Path, default=HELDOUT_DIR)
    args = parser.parse_args()
    result = generate_heldout_artifacts(output_dir=args.output_dir, seed=args.seed)
    print(f"Wrote held-out artifacts to {result['output_dir']}")
    print(f"seed={result['seed']}")
    print(f"transactions={result['n_transactions']}")
    print(f"spikes={result['n_spikes']}")
    print(f"hourly_windows={result['n_hourly_windows']}")


if __name__ == "__main__":
    main()
