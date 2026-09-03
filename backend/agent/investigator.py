"""Deterministic tool-calling investigator. Evidence only. Not a chatbot."""

from __future__ import annotations

from typing import Any

from agent.investigator_tools import TOOL_NAMES, run_tool
from evaluation.intelligence import _as_record

PLAN = list(TOOL_NAMES)

FORBIDDEN_PHRASES = (
    "classifier detected",
    "classifier caused",
    "confirms fraud",
    "confirmed fraud",
    "fraud confirmed",
    "authorizes the action",
    "authorize the action",
    "execute this",
    "approved automatically",
)


def _reject_if_forbidden(text: str) -> str:
    lowered = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            return "Supporting evidence is available. Classifier output does not confirm fraud."
    return text


def _evidence_item(statement: str, tool: str, provenance: str) -> dict[str, Any]:
    return {
        "statement": _reject_if_forbidden(statement),
        "tool": tool,
        "provenance": provenance,
    }


def synthesize(intelligence: dict[str, Any], results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    brief = _as_record(intelligence.get("brief"))
    flagged = [str(item) for item in (brief.get("why_flagged") or []) if item]
    observed = [str(item) for item in (brief.get("observed") or []) if item]
    derived = [str(item) for item in (brief.get("derived") or []) if item]
    uncertain = [str(item) for item in (brief.get("uncertain") or []) if item]
    next_checks = [str(item) for item in (brief.get("next_checks") or []) if item]
    entities = results.get("inspect_entities") or {}
    temporal = results.get("inspect_temporal_context") or {}
    baseline = results.get("inspect_historical_baseline") or {}
    classifier = results.get("inspect_classifier_evidence") or {}
    metrics = results.get("inspect_case_metrics") or {}

    finding = " ".join(flagged) if flagged else "This case was flagged by the world detector from live anomaly evidence."
    finding = _reject_if_forbidden(finding)

    supporting: list[dict[str, Any]] = []
    for item in observed:
        supporting.append(_evidence_item(item, "inspect_case_metrics", "OBSERVED"))
    for item in derived:
        supporting.append(_evidence_item(item, "inspect_temporal_context", "DERIVED"))
    if temporal.get("available"):
        supporting.append(
            _evidence_item(
                "Neighboring same-world hours are available for comparison.",
                "inspect_temporal_context",
                str(temporal.get("provenance") or "DERIVED"),
            )
        )
    if entities.get("available"):
        names = ", ".join(str(name) for name in (entities.get("groups") or {}))
        supporting.append(
            _evidence_item(
                f"Entity relationships are available for {names}." if names else "Entity relationships are available.",
                "inspect_entities",
                str(entities.get("provenance") or "OBSERVED"),
            )
        )
    if baseline.get("available"):
        supporting.append(
            _evidence_item(
                str(baseline.get("definition") or "A same-world historical baseline is available."),
                "inspect_historical_baseline",
                str(baseline.get("provenance") or "BASELINE"),
            )
        )

    contradictory: list[dict[str, Any]] = []
    if not baseline.get("available"):
        contradictory.append(
            _evidence_item(
                str((baseline.get("limitations") or ["Historical baseline is unavailable."])[0]),
                "inspect_historical_baseline",
                str(baseline.get("provenance") or "BASELINE"),
            )
        )
    for item in uncertain:
        tool = "inspect_classifier_evidence" if "classifier" in item.lower() else "inspect_case_metrics"
        provenance = "EVALUATION" if "label" in item.lower() or "truth" in item.lower() else "DERIVED"
        contradictory.append(_evidence_item(item, tool, provenance))

    uncertainty: list[str] = []
    headline = classifier.get("headline")
    if headline:
        uncertainty.append(f"{headline} — supporting evidence only. Not a fraud confirmation and not an action authorization.")
    for item in classifier.get("limitations") or []:
        if item not in uncertainty:
            uncertainty.append(str(item))
    if not entities.get("available"):
        for item in entities.get("limitations") or ["Entity relationships are unavailable."]:
            uncertainty.append(str(item))
    if metrics.get("limitations"):
        uncertainty.extend(str(item) for item in metrics["limitations"])

    next_check = next_checks[0] if next_checks else "Review the available anomaly evidence before any approval."
    if any(phrase in next_check.lower() for phrase in ("execute", "approve automatically", "block payment")):
        next_check = "Review the available anomaly evidence before any approval."

    evidence_used = [
        {
            "tool": name,
            "summary": (
                "Completed"
                if (results.get(name) or {}).get("status") == "completed"
                else "Unavailable"
            ),
            "limitations": list((results.get(name) or {}).get("limitations") or []),
        }
        for name in PLAN
    ]
    return {
        "finding": finding,
        "supporting_evidence": supporting,
        "contradictory_evidence": contradictory,
        "uncertainty": uncertainty,
        "recommended_next_human_check": next_check,
        "evidence_used": evidence_used,
        "not_a_governance_decision": True,
        "does_not_authorize_action": True,
        "does_not_approve": True,
        "does_not_simulate": True,
        "not_an_llm_paragraph": True,
        "not_a_chatbot": True,
    }


def investigate_with_tools(intelligence: dict[str, Any], *, world: str | None = None) -> dict[str, Any]:
    """Run the fixed read-only tool plan against existing Pass 1 intelligence."""
    payload = intelligence if isinstance(intelligence, dict) else {}
    expected_world = world or str(payload.get("world") or "")
    results: dict[str, dict[str, Any]] = {}
    trace: list[dict[str, Any]] = []
    for name in PLAN:
        result = run_tool(name, payload, world=expected_world or None)
        results[name] = result
        trace.append(
            {
                "tool": name,
                "status": "completed",
                "label": name.replace("_", " "),
            }
        )
    synthesized = synthesize(payload, results)
    return {
        "planner": "deterministic_tool_plan",
        "world": payload.get("world"),
        "case_id": payload.get("case_id"),
        **synthesized,
        "trace": trace,
        "tools": PLAN,
        "read_only": True,
        "not_a_chatbot": True,
        "not_a_governance_decision": True,
    }
