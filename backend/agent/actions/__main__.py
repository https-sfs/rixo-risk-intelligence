"""Demonstrate investigate → propose → approve → simulate → verify → audit."""

from __future__ import annotations

import argparse
import json
import sys

from agent.actions.service import run_approved_simulation
from agent.investigate import investigate_spike
from agent.providers.deterministic import DeterministicReasoner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 3B simulated action flow. Deterministic provider. No API key."
    )
    parser.add_argument("--spike-id", required=True)
    parser.add_argument("--approved-by", default="analyst")
    parser.add_argument("--note", default="manual demonstration")
    args = parser.parse_args(argv)
    investigation = investigate_spike(args.spike_id, provider=DeterministicReasoner())
    flow = run_approved_simulation(
        investigation["report"],
        approved_by=args.approved_by,
        note=args.note,
    )
    print(json.dumps({"investigation": investigation["report"], **flow}, indent=2))
    print(f"provider={investigation['provider']}", file=sys.stderr)
    print("executor=simulation-only", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
