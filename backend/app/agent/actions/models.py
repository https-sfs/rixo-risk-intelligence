"""Action governance contracts. Simulation only; no production payment fields."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ALLOWED_ACTION_TYPES = frozenset({"review", "monitor", "tighten_rule", "no_action"})
FORBIDDEN_ACTION_TYPES = frozenset(
    {
        "block",
        "block_all",
        "blanket_block",
        "disable_account",
        "disable",
        "refund",
        "capture",
        "move_money",
        "change_payout",
        "change_payment_route",
        "production_rule_update",
        "modify_production_rules",
        "delete_customer",
        "modify_transaction",
        "arbitrary_api_call",
    }
)
BROAD_SCOPE_PHRASES = (
    "all customers",
    "all transactions",
    "entire merchant",
    "all payments",
    "everything",
    "all devices",
    "all skus",
    "all accounts",
    "all subnets",
)

ProposalStatus = Literal["proposed", "approved", "rejected", "simulated"]
AuditEventType = Literal[
    "DECISION_RECORDED",
    "ACTION_PROPOSED",
    "ACTION_APPROVED",
    "ACTION_SIMULATED",
    "ACTION_VERIFIED",
    "ACTION_SANDBOX_TEST_SIMULATED",
    "ACTION_SANDBOX_TEST_FAILED",
]


@dataclass
class ActionProposal:
    action_id: str
    spike_id: str
    action_type: str
    scope: str
    reason: str
    source_provider: str
    created_at: str
    status: ProposalStatus
    human_approval_required: bool
    verdict: str
    frozen_scope: str
    scope_at_approval: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Approval:
    action_id: str
    approved: bool
    approved_by: str
    approved_at: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionResult:
    action_id: str
    status: str
    simulated: bool
    affected_scope: str
    message: str
    verification: dict[str, Any]
    audit_event_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditEvent:
    event_id: str
    timestamp: str
    action_id: str
    spike_id: str
    kind: AuditEventType
    actor: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["event" + "_type"] = payload.pop("kind")
        return payload
