"""Strict parsing and citation checks for LLM investigation output."""

from __future__ import annotations

import json
from typing import Any

from agent.errors import LLMOutputError
from agent.schema import (
    ALLOWED_ACTIONS,
    ALLOWED_VERDICTS,
    FORBIDDEN_ACTIONS,
    EvidenceCitation,
    InvestigationReport,
    KeyEntity,
    RecommendedAction,
)

REQUIRED_KEYS = (
    "spike_id",
    "verdict",
    "confidence",
    "summary",
    "supporting_evidence",
    "contradicting_evidence",
    "key_entities",
    "reasoning",
    "recommended_action",
    "human_approval_required",
    "limitations",
)
ALLOWED_ENTITY_TYPES = frozenset({"device", "subnet", "pincode", "sku", "account"})


def parse_model_json(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise LLMOutputError("Model returned empty output")
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise LLMOutputError("Model returned malformed JSON") from exc
    if not isinstance(payload, dict):
        raise LLMOutputError("Model JSON must be an object")
    return payload


def resolve_source(facts: dict[str, Any], source: str) -> Any:
    if not isinstance(source, str) or not source.strip():
        raise LLMOutputError("Citation source is missing")
    current: Any = facts
    for part in source.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise LLMOutputError(f"Citation source does not exist: {source}")
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            if index < 0 or index >= len(current):
                raise LLMOutputError(f"Citation source does not exist: {source}")
            current = current[index]
        else:
            raise LLMOutputError(f"Citation source does not exist: {source}")
    return current


def collect_string_values(payload: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        for value in payload.values():
            found |= collect_string_values(value)
    elif isinstance(payload, list):
        for value in payload:
            found |= collect_string_values(value)
    elif isinstance(payload, str):
        found.add(payload)
    return found


def _citations(items: Any, field_name: str, facts: dict[str, Any]) -> list[EvidenceCitation]:
    if not isinstance(items, list):
        raise LLMOutputError(f"{field_name} must be a list")
    citations: list[EvidenceCitation] = []
    known = collect_string_values(facts)
    for item in items:
        if not isinstance(item, dict) or "fact" not in item or "source" not in item:
            raise LLMOutputError(f"{field_name} entries must have fact and source")
        fact = item["fact"]
        source = item["source"]
        if not isinstance(fact, str) or not fact.strip():
            raise LLMOutputError(f"{field_name} fact must be a non-empty string")
        resolve_source(facts, source)
        for token in _entity_tokens(fact):
            if token not in known:
                raise LLMOutputError(f"Citation references an unknown entity: {token}")
        citations.append(EvidenceCitation(fact=fact, source=source))
    return citations


def _entity_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in text.replace(",", " ").split():
        cleaned = raw.strip(".:;()[]{}\"'")
        if cleaned.startswith(("dev_", "sku_", "acc_")):
            tokens.append(cleaned)
        elif "/" in cleaned and cleaned[0].isdigit():
            tokens.append(cleaned)
    return tokens


def _key_entities(items: Any, facts: dict[str, Any]) -> list[KeyEntity]:
    if not isinstance(items, list):
        raise LLMOutputError("key_entities must be a list")
    known = collect_string_values(facts)
    entities: list[KeyEntity] = []
    for item in items:
        if not isinstance(item, dict):
            raise LLMOutputError("key_entities entries must be objects")
        entity_type = item.get("entity_type")
        entity_id = item.get("entity_id")
        reason = item.get("reason")
        if entity_type not in ALLOWED_ENTITY_TYPES:
            raise LLMOutputError("key_entities entity_type is not allowed")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise LLMOutputError("key_entities entity_id is missing")
        if entity_id not in known:
            raise LLMOutputError(f"key_entities entity_id does not exist in evidence: {entity_id}")
        if not isinstance(reason, str) or not reason.strip():
            raise LLMOutputError("key_entities reason is missing")
        entities.append(
            KeyEntity(entity_type=entity_type, entity_id=entity_id, reason=reason)
        )
    return entities


def _recommended_action(payload: Any) -> RecommendedAction:
    if not isinstance(payload, dict):
        raise LLMOutputError("recommended_action must be an object")
    action_type = payload.get("type")
    if action_type in FORBIDDEN_ACTIONS:
        raise LLMOutputError("Unsupported action is not allowed")
    if action_type not in ALLOWED_ACTIONS:
        raise LLMOutputError("Unsupported action is not allowed")
    scope = payload.get("scope")
    reason = payload.get("reason")
    if not isinstance(scope, str) or not scope.strip():
        raise LLMOutputError("recommended_action.scope is missing")
    if not isinstance(reason, str) or not reason.strip():
        raise LLMOutputError("recommended_action.reason is missing")
    return RecommendedAction(type=action_type, scope=scope, reason=reason)


def validate_llm_report(payload: dict[str, Any], facts: dict[str, Any]) -> InvestigationReport:
    missing = [key for key in REQUIRED_KEYS if key not in payload]
    if missing:
        raise LLMOutputError(f"Model JSON is missing required keys: {', '.join(missing)}")

    spike_id = payload["spike_id"]
    if spike_id != facts.get("spike_id"):
        raise LLMOutputError("spike_id does not match the supplied facts")

    verdict = payload["verdict"]
    if verdict not in ALLOWED_VERDICTS:
        raise LLMOutputError("Invalid verdict")

    confidence = payload["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise LLMOutputError("confidence must be a number between 0 and 1")
    confidence_value = float(confidence)
    if confidence_value < 0.0 or confidence_value > 1.0:
        raise LLMOutputError("confidence must be a number between 0 and 1")

    if not isinstance(payload["summary"], str) or not payload["summary"].strip():
        raise LLMOutputError("summary must be a non-empty string")
    if not isinstance(payload["reasoning"], str) or not payload["reasoning"].strip():
        raise LLMOutputError("reasoning must be a non-empty string")
    if not isinstance(payload["limitations"], list) or not all(
        isinstance(item, str) for item in payload["limitations"]
    ):
        raise LLMOutputError("limitations must be a list of strings")

    if payload["human_approval_required"] is not True:
        raise LLMOutputError("human_approval_required must be true")

    return InvestigationReport(
        spike_id=str(spike_id),
        verdict=verdict,
        confidence=confidence_value,
        summary=payload["summary"],
        supporting_evidence=_citations(payload["supporting_evidence"], "supporting_evidence", facts),
        contradicting_evidence=_citations(
            payload["contradicting_evidence"], "contradicting_evidence", facts
        ),
        key_entities=_key_entities(payload["key_entities"], facts),
        reasoning=payload["reasoning"],
        recommended_action=_recommended_action(payload["recommended_action"]),
        human_approval_required=True,
        limitations=list(payload["limitations"]),
        provider="llm",
    )


def parse_and_validate_llm_report(text: str, facts: dict[str, Any]) -> InvestigationReport:
    return validate_llm_report(parse_model_json(text), facts)
