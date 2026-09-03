"""Safety gates for proposals. Code-enforced; not prompt-only."""

from __future__ import annotations

from typing import Any

from agent.actions.errors import ActionError
from agent.actions.models import ALLOWED_ACTION_TYPES, BROAD_SCOPE_PHRASES, FORBIDDEN_ACTION_TYPES
from agent.schema import ALLOWED_VERDICTS


def _text(value: Any) -> str:
    return str(value or "").strip()


def validate_action_type(action_type: Any) -> str:
    normalized = _text(action_type)
    if normalized in FORBIDDEN_ACTION_TYPES:
        raise ActionError(f"Forbidden action type is not allowed: {normalized}")
    if normalized not in ALLOWED_ACTION_TYPES:
        raise ActionError(f"Unsupported action type is not allowed: {normalized}")
    return normalized


def validate_scope(scope: Any, spike_id: str) -> str:
    cleaned = _text(scope)
    if not cleaned:
        raise ActionError("Action scope is missing")
    lowered = cleaned.lower()
    for phrase in BROAD_SCOPE_PHRASES:
        if phrase in lowered:
            raise ActionError(f"Action scope is too broad: {cleaned}")
    if "all " in lowered and any(token in lowered for token in ("customer", "transaction", "payment", "device", "sku")):
        raise ActionError(f"Action scope is too broad: {cleaned}")
    if spike_id and spike_id not in cleaned and "window" not in lowered and "spike" not in lowered:
        cleaned = f"{cleaned} within spike {spike_id}"
    return cleaned


def validate_proposal_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    spike_id = _text(payload.get("spike_id"))
    if not spike_id:
        raise ActionError("spike_id is missing")
    verdict = _text(payload.get("verdict"))
    if verdict not in ALLOWED_VERDICTS:
        raise ActionError("Investigation verdict is not valid")
    recommendation = payload.get("recommended_action") or {}
    if not isinstance(recommendation, dict):
        raise ActionError("recommended_action must be an object")
    action_type = validate_action_type(recommendation.get("type") or payload.get("action_type"))
    scope = validate_scope(recommendation.get("scope") or payload.get("scope"), spike_id)
    reason = _text(recommendation.get("reason") or payload.get("reason"))
    if not reason:
        raise ActionError("Action reason is missing")
    if payload.get("human_approval_required") is not True:
        raise ActionError("human_approval_required must be true")
    if verdict == "likely_festive" and action_type == "tighten_rule":
        raise ActionError("likely_festive traffic cannot generate a tighten_rule action")
    return {
        "spike_id": spike_id,
        "verdict": verdict,
        "action_type": action_type,
        "scope": scope,
        "reason": reason,
        "source_provider": _text(payload.get("provider") or payload.get("source_provider"))
        or "unknown",
    }


def assert_scope_unchanged(proposal_scope: str, frozen_scope: str) -> None:
    if proposal_scope != frozen_scope:
        raise ActionError("Action scope cannot change between approval and execution")
