from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.actions.errors import ActionError
from agent.actions.models import ALLOWED_ACTION_TYPES, FORBIDDEN_ACTION_TYPES
from agent.actions.service import (
    approve_action,
    execute_action,
    get_audit_trail,
    propose_from_report,
    propose_manual,
)
from agent.actions.store import ActionStore
from agent.investigate import investigate_spike
from agent.providers.deterministic import DeterministicReasoner
from agent.providers.llm import LLMInvestigationProvider
from tests.test_llm_provider import FakeLLMClient, _facts, _valid_payload

SPIKE_ABUSE = "spk-coord-20260118-02"
SPIKE_FESTIVE = "spk-fest-20260114-18"
ACTIONS_DIR = Path(__file__).resolve().parents[1] / "agent" / "actions"


def _audit_kinds(store: ActionStore, action_id: str) -> list[str]:
    return [item["event" + "_type"] for item in get_audit_trail(action_id, store=store)]


def test_valid_recommendation_creates_proposal() -> None:
    store = ActionStore()
    result = investigate_spike(SPIKE_ABUSE, provider=DeterministicReasoner())
    proposal = propose_from_report(result["report"], store=store)
    assert proposal.action_type in ALLOWED_ACTION_TYPES
    assert proposal.spike_id == SPIKE_ABUSE
    assert proposal.status == "proposed"
    assert proposal.human_approval_required is True
    kinds = _audit_kinds(store, proposal.action_id)
    assert kinds[0] == "DECISION_RECORDED"
    assert "ACTION_PROPOSED" in kinds
    again = propose_from_report(result["report"], store=store)
    assert again.action_id == proposal.action_id
    assert _audit_kinds(store, proposal.action_id).count("DECISION_RECORDED") == 1


def test_invalid_action_type_is_rejected() -> None:
    store = ActionStore()
    with pytest.raises(ActionError, match="Unsupported action type"):
        propose_manual(
            {
                "action_type": "freeze_cards",
                "scope": f"device dev_5007 within spike {SPIKE_ABUSE}",
                "verdict": "coordinated_abuse",
                "spike_id": SPIKE_ABUSE,
            },
            store=store,
        )
    assert store.proposals == {}


def test_missing_scope_is_rejected() -> None:
    store = ActionStore()
    with pytest.raises(ActionError, match="scope"):
        propose_from_report(
            {
                "spike_id": SPIKE_ABUSE,
                "verdict": "coordinated_abuse",
                "recommended_action": {"type": "review", "reason": "check device"},
                "human_approval_required": True,
                "provider": "deterministic_reasoner",
            },
            store=store,
        )


def test_blank_scope_is_rejected() -> None:
    store = ActionStore()
    with pytest.raises(ActionError, match="scope"):
        propose_from_report(
            {
                "spike_id": SPIKE_ABUSE,
                "verdict": "coordinated_abuse",
                "recommended_action": {"type": "review", "scope": "   ", "reason": "check"},
                "human_approval_required": True,
                "provider": "deterministic_reasoner",
            },
            store=store,
        )


def test_broad_scope_all_customers_is_rejected() -> None:
    store = ActionStore()
    with pytest.raises(ActionError, match="too broad"):
        propose_from_report(
            {
                "spike_id": SPIKE_ABUSE,
                "verdict": "coordinated_abuse",
                "recommended_action": {
                    "type": "review",
                    "scope": "all customers",
                    "reason": "too wide",
                },
                "human_approval_required": True,
                "provider": "deterministic_reasoner",
            },
            store=store,
        )


def test_human_approval_required_false_is_rejected() -> None:
    store = ActionStore()
    with pytest.raises(ActionError, match="human_approval_required"):
        propose_from_report(
            {
                "spike_id": SPIKE_ABUSE,
                "verdict": "coordinated_abuse",
                "recommended_action": {
                    "type": "review",
                    "scope": f"device dev_5007 within spike {SPIKE_ABUSE}",
                    "reason": "review device",
                },
                "human_approval_required": False,
                "provider": "deterministic_reasoner",
            },
            store=store,
        )


def test_execution_without_approval_is_rejected() -> None:
    store = ActionStore()
    result = investigate_spike(SPIKE_ABUSE)
    proposal = propose_from_report(result["report"], store=store)
    with pytest.raises(ActionError, match="not been explicitly approved"):
        execute_action(proposal.action_id, store=store)
    assert proposal.action_id not in store.executions
    assert proposal.status == "proposed"
    assert "ACTION_SIMULATED" not in _audit_kinds(store, proposal.action_id)


def test_explicit_approval_succeeds() -> None:
    store = ActionStore()
    proposal = propose_from_report(investigate_spike(SPIKE_ABUSE)["report"], store=store)
    approval = approve_action(proposal.action_id, approved_by="analyst", note="ok", store=store)
    assert approval.approved is True
    assert approval.approved_by == "analyst"
    assert store.get_proposal(proposal.action_id).status == "approved"
    assert "ACTION_APPROVED" in _audit_kinds(store, proposal.action_id)


@pytest.mark.parametrize(
    ("action_type", "needle"),
    [
        ("review", "queued for human review"),
        ("monitor", "monitoring policy attached"),
        ("tighten_rule", "narrowed review/risk rule"),
        ("no_action", "no intervention applied"),
    ],
)
def test_approved_actions_execute_in_simulation(action_type: str, needle: str) -> None:
    store = ActionStore()
    proposal = propose_from_report(
        {
            "spike_id": SPIKE_ABUSE,
            "verdict": "coordinated_abuse" if action_type != "monitor" else "inconclusive",
            "recommended_action": {
                "type": action_type,
                "scope": f"device dev_5007 within spike {SPIKE_ABUSE}",
                "reason": "bounded demonstration",
            },
            "human_approval_required": True,
            "provider": "deterministic_reasoner",
        },
        store=store,
    )
    approve_action(proposal.action_id, approved_by="analyst", store=store)
    result = execute_action(proposal.action_id, store=store)
    assert result.simulated is True
    assert result.status == "simulated"
    assert needle in result.message
    assert result.message.startswith("SIMULATED:")
    assert result.verification["message"] == "Simulation verified."
    assert result.verification["production_api_called"] is False
    kinds = _audit_kinds(store, proposal.action_id)
    assert "ACTION_SIMULATED" in kinds
    assert "ACTION_VERIFIED" in kinds


@pytest.mark.parametrize("action_type", ["block_all", "disable_account", "refund"])
def test_forbidden_actions_are_rejected(action_type: str) -> None:
    store = ActionStore()
    with pytest.raises(ActionError, match="Forbidden action type"):
        propose_manual(
            {
                "action_type": action_type,
                "scope": "all customers",
                "spike_id": SPIKE_ABUSE,
                "verdict": "coordinated_abuse",
            },
            store=store,
        )


def test_hand_built_block_all_all_customers_is_rejected() -> None:
    with pytest.raises(ActionError):
        propose_manual({"action_type": "block_all", "scope": "all customers"})


def test_tighten_rule_all_transactions_is_rejected() -> None:
    with pytest.raises(ActionError, match="too broad"):
        propose_manual(
            {
                "action_type": "tighten_rule",
                "scope": "all transactions",
                "spike_id": SPIKE_ABUSE,
                "verdict": "coordinated_abuse",
                "reason": "unsafe broadening",
            }
        )


def test_simulation_source_has_no_external_api() -> None:
    for path in ACTIONS_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "httpx" not in source
        assert "requests" not in source
        assert "razorpay" not in source
        assert "openai" not in source
        assert "LLM_API_KEY" not in source


def test_scope_cannot_change_between_approval_and_execution() -> None:
    store = ActionStore()
    proposal = propose_from_report(investigate_spike(SPIKE_ABUSE)["report"], store=store)
    approve_action(proposal.action_id, approved_by="analyst", store=store)
    stored = store.get_proposal(proposal.action_id)
    stored.scope = "all customers"
    with pytest.raises(ActionError, match="cannot change"):
        execute_action(proposal.action_id, store=store)
    assert proposal.action_id not in store.executions


def test_festive_investigation_prefers_monitor_or_no_action() -> None:
    store = ActionStore()
    result = investigate_spike(SPIKE_FESTIVE, provider=DeterministicReasoner())
    assert result["report"]["verdict"] == "likely_festive"
    proposal = propose_from_report(result["report"], store=store)
    assert proposal.action_type in {"monitor", "no_action"}
    with pytest.raises(ActionError, match="likely_festive"):
        propose_from_report(
            {
                "spike_id": SPIKE_FESTIVE,
                "verdict": "likely_festive",
                "recommended_action": {
                    "type": "tighten_rule",
                    "scope": f"window-level monitoring for {SPIKE_FESTIVE}",
                    "reason": "volume only",
                },
                "human_approval_required": True,
                "provider": "deterministic_reasoner",
            },
            store=store,
        )


def test_coordinated_investigation_can_produce_narrow_tighten_rule() -> None:
    store = ActionStore()
    result = investigate_spike(SPIKE_ABUSE, provider=DeterministicReasoner())
    proposal = propose_from_report(result["report"], store=store)
    assert proposal.action_type in {"review", "tighten_rule"}
    assert SPIKE_ABUSE in proposal.scope
    assert "all customers" not in proposal.scope.lower()
    assert "all transactions" not in proposal.scope.lower()


def test_deterministic_provider_remains_compatible() -> None:
    store = ActionStore()
    result = investigate_spike(SPIKE_ABUSE)
    assert result["provider"] == "deterministic_reasoner"
    proposal = propose_from_report(result["report"], store=store)
    assert proposal.source_provider == "deterministic_reasoner"


def test_llm_provider_remains_compatible() -> None:
    store = ActionStore()
    facts = _facts(SPIKE_ABUSE)
    provider = LLMInvestigationProvider(client=FakeLLMClient(_valid_payload(facts)))
    result = investigate_spike(SPIKE_ABUSE, provider=provider)
    assert result["provider"] == "llm"
    proposal = propose_from_report(result["report"], store=store)
    assert proposal.source_provider == "llm"
    approve_action(proposal.action_id, approved_by="analyst", store=store)
    execution = execute_action(proposal.action_id, store=store)
    assert execution.simulated is True


def test_audit_covers_full_lifecycle() -> None:
    store = ActionStore()
    proposal = propose_from_report(investigate_spike(SPIKE_ABUSE)["report"], store=store)
    approve_action(proposal.action_id, approved_by="analyst", store=store)
    execute_action(proposal.action_id, store=store)
    kinds = _audit_kinds(store, proposal.action_id)
    assert kinds == [
        "DECISION_RECORDED",
        "ACTION_PROPOSED",
        "ACTION_APPROVED",
        "ACTION_SIMULATED",
        "ACTION_VERIFIED",
    ]


def test_forbidden_set_includes_required_names() -> None:
    for name in (
        "block_all",
        "blanket_block",
        "disable_account",
        "refund",
        "capture",
        "move_money",
        "production_rule_update",
    ):
        assert name in FORBIDDEN_ACTION_TYPES
