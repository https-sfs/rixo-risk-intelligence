"""Propose, approve, simulate, and verify bounded actions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from agent.actions.audit import record_audit
from agent.actions.errors import ActionError
from agent.actions.gates import assert_scope_unchanged, validate_action_type, validate_proposal_inputs
from agent.actions.models import ActionProposal, Approval, ExecutionResult
from agent.actions.simulate import simulate_action
from agent.actions.store import ActionStore
from agent.schema import InvestigationReport
from app.integrations.sandbox_payments import apply_after_approval, audit_details

_DEFAULT_STORE = ActionStore()


def default_store() -> ActionStore:
    return _DEFAULT_STORE


def bind_default_store(store: ActionStore) -> ActionStore:
    global _DEFAULT_STORE
    _DEFAULT_STORE = store
    return _DEFAULT_STORE


def reset_default_store() -> ActionStore:
    global _DEFAULT_STORE
    _DEFAULT_STORE = ActionStore()
    return _DEFAULT_STORE


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_payload(report: InvestigationReport | dict[str, Any]) -> dict[str, Any]:
    if isinstance(report, InvestigationReport):
        payload = report.to_dict()
        payload["human_approval_required"] = report.human_approval_required
        return payload
    return dict(report)


def investigation_state(spike_id: str, store: ActionStore | None = None) -> dict[str, Any]:
    state = store or default_store()
    proposal = state.latest_proposal_for_spike(spike_id)
    action_id = proposal.action_id if proposal else None
    approval = state.get_approval(action_id) if action_id else None
    execution = state.executions.get(action_id) if action_id else None
    audit = [event.to_dict() for event in state.events_for_spike(spike_id)]
    if approval is not None and approval.approved is True:
        approval_status = "approved"
    elif proposal is not None:
        approval_status = "pending"
    else:
        approval_status = "not_applicable"
    return {
        "decision": (
            {
                "spike_id": proposal.spike_id,
                "recorded_at": proposal.created_at,
                "verdict": proposal.verdict,
                "action_type": proposal.action_type,
                "representation": "proposal_read_model",
            }
            if proposal
            else None
        ),
        "decision_representation": "proposal_read_model",
        "proposal": proposal.to_dict() if proposal else None,
        "approval": approval.to_dict() if approval else None,
        "execution": execution.to_dict() if execution else None,
        "audit": audit,
        "status": {
            "decision": "recorded" if proposal else "not_recorded",
            "approval": approval_status,
            "simulation": "completed" if execution is not None and execution.simulated else "not_simulated",
            "audit_count": len(audit),
        },
    }


def propose_from_report(
    report: InvestigationReport | dict[str, Any],
    store: ActionStore | None = None,
) -> ActionProposal:
    state = store or default_store()
    fields = validate_proposal_inputs(_as_payload(report))
    existing = state.latest_proposal_for_spike(fields["spike_id"])
    if existing is not None:
        return existing
    timestamp = _now()
    proposal = ActionProposal(
        action_id=f"act-{uuid4().hex[:12]}",
        spike_id=fields["spike_id"],
        action_type=fields["action_type"],
        scope=fields["scope"],
        reason=fields["reason"],
        source_provider=fields["source_provider"],
        created_at=timestamp,
        status="proposed",
        human_approval_required=True,
        verdict=fields["verdict"],
        frozen_scope=fields["scope"],
    )
    state.put_proposal(proposal)
    record_audit(
        state,
        kind="DECISION_RECORDED",
        action_id=proposal.action_id,
        spike_id=proposal.spike_id,
        actor="system",
        details={
            "verdict": proposal.verdict,
            "action_type": proposal.action_type,
            "decision_representation": "proposal_read_model",
        },
        timestamp=timestamp,
    )
    record_audit(
        state,
        kind="ACTION_PROPOSED",
        action_id=proposal.action_id,
        spike_id=proposal.spike_id,
        actor="system",
        details={"action_type": proposal.action_type, "scope": proposal.scope},
        timestamp=timestamp,
    )
    return proposal


def propose_manual(payload: dict[str, Any], store: ActionStore | None = None) -> ActionProposal:
    """Reject unsafe hand-built payloads. Used by safety tests."""
    validate_action_type(payload.get("action_type"))
    return propose_from_report(
        {
            "spike_id": payload.get("spike_id") or "spk-unknown",
            "verdict": payload.get("verdict") or "inconclusive",
            "recommended_action": {
                "type": payload.get("action_type"),
                "scope": payload.get("scope"),
                "reason": payload.get("reason") or "manual construction",
            },
            "human_approval_required": payload.get("human_approval_required", True),
            "provider": payload.get("source_provider") or "manual",
        },
        store=store,
    )


def approve_action(
    action_id: str,
    approved_by: str,
    note: str = "",
    store: ActionStore | None = None,
) -> Approval:
    state = store or default_store()
    proposal = state.get_proposal(action_id)
    if proposal is None:
        raise ActionError(f"Unknown action_id: {action_id}")
    if not approved_by.strip():
        raise ActionError("approved_by is required")
    timestamp = _now()
    approval = Approval(
        action_id=action_id,
        approved=True,
        approved_by=approved_by.strip(),
        approved_at=timestamp,
        note=note,
    )
    proposal.status = "approved"
    proposal.scope_at_approval = proposal.frozen_scope
    state.put_proposal(proposal)
    state.put_approval(approval)
    record_audit(
        state,
        kind="ACTION_APPROVED",
        action_id=action_id,
        spike_id=proposal.spike_id,
        actor=approval.approved_by,
        details={"note": note, "scope": proposal.frozen_scope},
        timestamp=timestamp,
    )
    return approval


def execute_action(action_id: str, store: ActionStore | None = None) -> ExecutionResult:
    state = store or default_store()
    proposal = state.get_proposal(action_id)
    if proposal is None:
        raise ActionError(f"Unknown action_id: {action_id}")
    approval = state.get_approval(action_id)
    if approval is None or approval.approved is not True or proposal.status != "approved":
        raise ActionError("Action has not been explicitly approved")
    assert_scope_unchanged(proposal.scope, proposal.frozen_scope)
    if proposal.scope_at_approval is not None:
        assert_scope_unchanged(proposal.scope, proposal.scope_at_approval)
    validate_action_type(proposal.action_type)
    timestamp = _now()
    message = simulate_action(proposal.action_type, proposal.scope)
    sandbox = apply_after_approval(
        action_id=action_id,
        case_id=proposal.spike_id,
        action_type=proposal.action_type,
        scope=proposal.scope,
    )
    sandbox_ok = sandbox.get("status") not in {"failed", "blocked"}
    if sandbox.get("status") == "completed":
        message = f"{message} {sandbox.get('message', '')}".strip()
    elif sandbox.get("status") == "unavailable":
        message = f"{message} {sandbox.get('message', '')}".strip()
    else:
        message = str(sandbox.get("message") or "Sandbox test simulation failed.")
    if sandbox_ok:
        simulated_event = record_audit(
            state,
            kind="ACTION_SIMULATED",
            action_id=action_id,
            spike_id=proposal.spike_id,
            actor="simulator",
            details={"message": message, "scope": proposal.scope, "production_api_called": False},
            timestamp=timestamp,
        )
        if sandbox.get("status") == "completed":
            record_audit(
                state,
                kind="ACTION_SANDBOX_TEST_SIMULATED",
                action_id=action_id,
                spike_id=proposal.spike_id,
                actor="simulator",
                details=audit_details(sandbox),
                timestamp=timestamp,
            )
    else:
        simulated_event = record_audit(
            state,
            kind="ACTION_SANDBOX_TEST_FAILED",
            action_id=action_id,
            spike_id=proposal.spike_id,
            actor="simulator",
            details=audit_details(sandbox),
            timestamp=timestamp,
        )
    verification = {
        "action_existed": True,
        "action_approved": True,
        "action_type_allowed": True,
        "scope_unchanged": True,
        "execution_simulated": sandbox_ok,
        "production_api_called": False,
        "audit_event_created": True,
        "message": "Simulation verified." if sandbox_ok else message,
        "sandbox_test": sandbox,
    }
    audit_event_id = simulated_event.event_id
    if sandbox_ok:
        verified_event = record_audit(
            state,
            kind="ACTION_VERIFIED",
            action_id=action_id,
            spike_id=proposal.spike_id,
            actor="verifier",
            details={key: value for key, value in verification.items() if key != "sandbox_test"},
            timestamp=timestamp,
        )
        audit_event_id = verified_event.event_id
    result = ExecutionResult(
        action_id=action_id,
        status="simulated" if sandbox_ok else "simulation_failed",
        simulated=sandbox_ok,
        affected_scope=proposal.scope,
        message=message,
        verification=verification,
        audit_event_id=audit_event_id,
    )
    if sandbox_ok:
        proposal.status = "simulated"
        state.put_proposal(proposal)
    state.put_execution(result)
    _ = simulated_event
    return result


def get_audit_trail(action_id: str | None = None, store: ActionStore | None = None) -> list[dict[str, Any]]:
    state = store or default_store()
    events = state.events_for(action_id) if action_id else state.audit
    return [event.to_dict() for event in events]


def run_approved_simulation(
    report: InvestigationReport | dict[str, Any],
    approved_by: str,
    note: str = "operator demonstration",
    store: ActionStore | None = None,
) -> dict[str, Any]:
    state = store or default_store()
    proposal = propose_from_report(report, store=state)
    approval = approve_action(proposal.action_id, approved_by=approved_by, note=note, store=state)
    result = execute_action(proposal.action_id, store=state)
    return {
        "proposal": proposal.to_dict(),
        "approval": approval.to_dict(),
        "execution": result.to_dict(),
        "audit": get_audit_trail(proposal.action_id, store=state),
    }
