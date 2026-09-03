"""Investigation report contract. No autonomous payment actions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Verdict = Literal["coordinated_abuse", "likely_festive", "inconclusive"]
ActionType = Literal["review", "tighten_rule", "monitor", "no_action"]
EntityType = Literal["device", "subnet", "pincode", "sku", "account"]

ALLOWED_VERDICTS = frozenset({"coordinated_abuse", "likely_festive", "inconclusive"})
ALLOWED_ACTIONS = frozenset({"review", "tighten_rule", "monitor", "no_action"})
FORBIDDEN_ACTIONS = frozenset(
    {
        "block",
        "block_all",
        "disable_account",
        "disable",
        "refund",
        "move_money",
        "modify_production_rules",
    }
)


@dataclass
class EvidenceCitation:
    fact: str
    source: str


@dataclass
class KeyEntity:
    entity_type: EntityType
    entity_id: str
    reason: str


@dataclass
class RecommendedAction:
    type: ActionType
    scope: str
    reason: str


@dataclass
class InvestigationReport:
    spike_id: str
    verdict: Verdict
    confidence: float
    summary: str
    supporting_evidence: list[EvidenceCitation]
    contradicting_evidence: list[EvidenceCitation]
    key_entities: list[KeyEntity]
    reasoning: str
    recommended_action: RecommendedAction
    human_approval_required: bool = True
    limitations: list[str] = field(default_factory=list)
    provider: str = "deterministic_reasoner"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["human_approval_required"] = True
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> InvestigationReport:
        return cls(
            spike_id=str(payload["spike_id"]),
            verdict=payload["verdict"],
            confidence=float(payload["confidence"]),
            summary=str(payload["summary"]),
            supporting_evidence=[EvidenceCitation(**item) for item in payload["supporting_evidence"]],
            contradicting_evidence=[
                EvidenceCitation(**item) for item in payload["contradicting_evidence"]
            ],
            key_entities=[KeyEntity(**item) for item in payload["key_entities"]],
            reasoning=str(payload["reasoning"]),
            recommended_action=RecommendedAction(**payload["recommended_action"]),
            human_approval_required=True,
            limitations=list(payload.get("limitations") or []),
            provider=str(payload.get("provider") or "deterministic_reasoner"),
        )
