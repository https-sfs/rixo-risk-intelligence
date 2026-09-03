"""Investigate one detected spike using Phase 2A facts plus a reasoner."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from agent.errors import LLMProviderError
from agent.facts import extract_reasoning_facts
from agent.policy import enforce_report_policy
from agent.providers.base import InvestigationProvider
from agent.providers.deterministic import DeterministicReasoner
from agent.providers.llm import LLMInvestigationProvider
from agent.schema import InvestigationReport
from tools.evidence import build_investigation_evidence


def resolve_provider(name: str) -> InvestigationProvider:
    normalized = name.strip().lower()
    if normalized in {"deterministic", "deterministic_reasoner"}:
        return DeterministicReasoner()
    if normalized == "llm":
        return LLMInvestigationProvider()
    raise ValueError(f"Unknown investigation provider: {name}")


def investigate_spike(
    spike_id: str,
    provider: InvestigationProvider | None = None,
    evidence: dict[str, Any] | None = None,
    fallback_to_deterministic: bool = False,
) -> dict[str, Any]:
    payload = evidence if evidence is not None else build_investigation_evidence(spike_id)
    facts = extract_reasoning_facts(payload)
    reasoner = provider or DeterministicReasoner()
    try:
        report = reasoner.reason(facts)
    except LLMProviderError:
        if not fallback_to_deterministic or isinstance(reasoner, DeterministicReasoner):
            raise
        reasoner = DeterministicReasoner()
        report = reasoner.reason(facts)
    report = enforce_report_policy(report)
    if report.spike_id != spike_id:
        report.spike_id = spike_id
    from agent.investigator import investigate_with_tools
    from evaluation.intelligence_worlds import for_synthetic

    intelligence = for_synthetic(payload, report.to_dict())
    return {
        "report": report.to_dict(),
        "facts_used": facts,
        "evidence_source": "phase_2a_deterministic",
        "provider": getattr(reasoner, "name", reasoner.__class__.__name__),
        "classifier": payload.get("classifier"),
        "investigation_intelligence": intelligence,
        "investigation_agent": investigate_with_tools(intelligence),
    }


def investigate_report(
    spike_id: str,
    provider: InvestigationProvider | None = None,
) -> InvestigationReport:
    return InvestigationReport.from_dict(
        investigate_spike(spike_id, provider=provider)["report"]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Investigate one detected spike. Default provider is deterministic."
    )
    parser.add_argument("--spike-id", required=True, help="Detected spike identifier")
    parser.add_argument(
        "--provider",
        choices=("deterministic", "llm"),
        default="deterministic",
        help="deterministic is the default. llm requires LLM_API_KEY.",
    )
    parser.add_argument(
        "--fallback-deterministic",
        action="store_true",
        help="If the LLM provider fails, use DeterministicReasoner and label it as such.",
    )
    args = parser.parse_args(argv)
    try:
        result = investigate_spike(
            args.spike_id,
            provider=resolve_provider(args.provider),
            fallback_to_deterministic=args.fallback_deterministic,
        )
    except (LLMProviderError, ValueError) as exc:
        print(f"Investigation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result["report"], indent=2))
    print(f"provider={result['provider']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
