"""Read-only investigation tools over Pass 1 intelligence. No ledger scans."""

from __future__ import annotations

from typing import Any, Callable

from evaluation.intelligence import (
    BYOD_WORLD,
    IEEE_WORLD,
    JANUARY_WORLD,
    SYNTHETIC_WORLD,
    _as_record,
)

TOOL_NAMES = (
    "inspect_case_metrics",
    "inspect_temporal_context",
    "inspect_entities",
    "inspect_historical_baseline",
    "inspect_classifier_evidence",
)

KNOWN_WORLDS = frozenset({SYNTHETIC_WORLD, JANUARY_WORLD, IEEE_WORLD, BYOD_WORLD})


class InvestigatorToolError(ValueError):
    """Unknown tool, world mismatch, or invalid tool input."""


def _world(intelligence: dict[str, Any]) -> str:
    return str(intelligence.get("world") or "")


def _case_id(intelligence: dict[str, Any]) -> str:
    return str(intelligence.get("case_id") or "")


def _require_world(intelligence: dict[str, Any], world: str | None) -> None:
    actual = _world(intelligence)
    if world and actual and actual != world:
        raise InvestigatorToolError(
            f"Tool requested {world} but the loaded evidence belongs to {actual}."
        )
    if actual and actual not in KNOWN_WORLDS:
        raise InvestigatorToolError(f"Unknown investigation world: {actual}")


def inspect_case_metrics(intelligence: dict[str, Any], *, world: str | None = None) -> dict[str, Any]:
    _require_world(intelligence, world)
    metrics = list(intelligence.get("case_metrics") or [])
    return {
        "tool": "inspect_case_metrics",
        "status": "completed",
        "world": _world(intelligence),
        "case_id": _case_id(intelligence),
        "metrics": metrics,
        "provenance": [item.get("provenance") for item in metrics if isinstance(item, dict)],
        "limitations": (
            ["No case metrics were attached to this intelligence payload."] if not metrics else []
        ),
        "read_only": True,
    }


def inspect_temporal_context(intelligence: dict[str, Any], *, world: str | None = None) -> dict[str, Any]:
    _require_world(intelligence, world)
    temporal = _as_record(intelligence.get("temporal"))
    available = bool(temporal.get("available"))
    return {
        "tool": "inspect_temporal_context",
        "status": "completed",
        "world": _world(intelligence),
        "case_id": _case_id(intelligence),
        "available": available,
        "selected": temporal.get("selected"),
        "neighbors": temporal.get("neighbors") or [],
        "baseline_note": temporal.get("baseline_note"),
        "count_kind": temporal.get("count_kind"),
        "amount_kind": temporal.get("amount_kind"),
        "intensity_kind": temporal.get("intensity_kind"),
        "provenance": temporal.get("provenance"),
        "source": temporal.get("source"),
        "limitations": [] if available else [str(temporal.get("reason") or "Temporal comparison is unavailable.")],
        "read_only": True,
    }


def inspect_entities(intelligence: dict[str, Any], *, world: str | None = None) -> dict[str, Any]:
    _require_world(intelligence, world)
    entities = _as_record(intelligence.get("entities"))
    groups = entities.get("groups") if isinstance(entities.get("groups"), dict) else {}
    missing = list(entities.get("missing") or [])
    available = bool(entities.get("available") and groups)
    limitations = []
    if not available:
        limitations.append(str(entities.get("note") or "Entity relationships are unavailable."))
    if missing:
        limitations.append("Unavailable identifiers: " + ", ".join(str(item) for item in missing) + ".")
    return {
        "tool": "inspect_entities",
        "status": "completed",
        "world": _world(intelligence),
        "case_id": _case_id(intelligence),
        "available": available,
        "groups": groups,
        "missing": missing,
        "note": entities.get("note"),
        "provenance": entities.get("provenance"),
        "limitations": limitations,
        "read_only": True,
    }


def inspect_historical_baseline(intelligence: dict[str, Any], *, world: str | None = None) -> dict[str, Any]:
    _require_world(intelligence, world)
    baseline = _as_record(intelligence.get("baseline"))
    available = bool(baseline.get("available"))
    return {
        "tool": "inspect_historical_baseline",
        "status": "completed",
        "world": _world(intelligence),
        "case_id": _case_id(intelligence),
        "available": available,
        "current": baseline.get("current"),
        "baseline": baseline.get("baseline"),
        "deviation": baseline.get("deviation"),
        "definition": baseline.get("definition"),
        "provenance": baseline.get("provenance"),
        "limitations": [] if available else [str(baseline.get("reason") or "Historical baseline is unavailable.")],
        "same_world_only": True,
        "read_only": True,
    }


def inspect_classifier_evidence(intelligence: dict[str, Any], *, world: str | None = None) -> dict[str, Any]:
    _require_world(intelligence, world)
    status = _as_record(intelligence.get("classifier_status"))
    limitations = [
        str(status.get("detail") or "Classifier evidence is supporting only."),
        "Classifier evidence is not a fraud confirmation and does not select an action.",
    ]
    return {
        "tool": "inspect_classifier_evidence",
        "status": "completed",
        "world": _world(intelligence),
        "case_id": _case_id(intelligence),
        "classifier_status": status,
        "score": status.get("fraud_risk_score"),
        "classification": status.get("classification"),
        "model": status.get("model"),
        "model_version": status.get("model_version"),
        "coverage": status.get("feature_coverage"),
        "feature_coverage": status.get("feature_coverage"),
        "scored_rows": status.get("scored_rows"),
        "high_risk_count": status.get("high_risk_count"),
        "evidence_quality": status.get("status"),
        "evidence_status": status.get("status"),
        "headline": status.get("headline"),
        "used_for_action_selection": bool(status.get("used_for_action_selection")),
        "kind": status.get("kind") or "evidence_quality",
        "not_fraud_confirmed": True,
        "provenance": status.get("provenance") or "MODEL PREDICTION",
        "limitations": limitations,
        "read_only": True,
    }


TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "inspect_case_metrics": inspect_case_metrics,
    "inspect_temporal_context": inspect_temporal_context,
    "inspect_entities": inspect_entities,
    "inspect_historical_baseline": inspect_historical_baseline,
    "inspect_classifier_evidence": inspect_classifier_evidence,
}


def run_tool(name: str, intelligence: dict[str, Any], *, world: str | None = None) -> dict[str, Any]:
    handler = TOOLS.get(name)
    if handler is None:
        raise InvestigatorToolError(f"Unknown investigation tool: {name}")
    return handler(intelligence, world=world)
