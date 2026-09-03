"""Custom-data governed simulation. Isolated from IEEE, January 2026, and synthetic actions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from evaluation.custom_data import DATASET_NAME, WORLD

ALLOWED_ACTION_TYPES = frozenset(
    {
        "review_transactions",
        "review_time_window",
        "monitor_only",
        "flag_for_human_review",
    }
)
FORBIDDEN_ACTION_TYPES = frozenset(
    {
        "block_payment",
        "block_transaction",
        "chargeback",
        "tighten_rule",
        "notify_razorpay",
        "live_block",
        "review_hour",
        "flag_high_risk_transactions",
        "take_no_simulated_action",
    }
)
ALLOWED_VERDICTS = frozenset({"review_recommended", "monitor_only"})
LIVE_DECISION_FORBIDDEN = frozenset(
    {
        "is_fraud",
        "fraud_label",
        "evaluation_overlay",
        "delayed_ground_truth",
        "labelled_fraud_rate",
        "fraud_rate",
    }
)


class CustomGovernanceError(ValueError):
    """Bring Your Data governance contract violation."""


class CustomActionStore:
    def __init__(self) -> None:
        self.decisions: dict[str, dict[str, Any]] = {}
        self.proposals: dict[str, dict[str, Any]] = {}
        self.approvals: dict[str, dict[str, Any]] = {}
        self.executions: dict[str, dict[str, Any]] = {}
        self.audit: list[dict[str, Any]] = []


_STORES: dict[str, CustomActionStore] = {}


def store_for(session_id: str) -> CustomActionStore:
    if session_id not in _STORES:
        _STORES[session_id] = CustomActionStore()
    return _STORES[session_id]


def reset_store(session_id: str | None = None) -> None:
    if session_id is None:
        _STORES.clear()
        return
    _STORES.pop(session_id, None)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _audit(
    store: CustomActionStore,
    kind: str,
    anomaly_id: str,
    action_id: str | None,
    details: dict[str, Any],
    session_id: str,
) -> dict[str, Any]:
    event = {
        "audit_event_id": f"caud-{uuid4().hex[:12]}",
        "kind": kind,
        "world": WORLD,
        "dataset": DATASET_NAME,
        "session_id": session_id,
        "anomaly_id": anomaly_id,
        "action_id": action_id,
        "timestamp": _now(),
        "simulation_only": True,
        "not_a_live_payment_action": True,
        "details": details,
    }
    store.audit.append(event)
    return event


def decide_from_investigation(
    anomaly: dict[str, Any],
    evidence: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    signals = list(anomaly.get("signals") or evidence.get("signals") or [])
    hour = evidence.get("hour_start") or anomaly.get("hour_start")
    model = evidence.get("model_prediction") or {}
    classifier = evidence.get("classifier") or {}
    # Classifier high_risk_count is supporting evidence only. User-provided labels
    # are never live inputs.
    if "elevated transaction amount" in signals:
        verdict = "review_recommended"
        action_type = "flag_for_human_review"
        reason = (
            f"User-dataset window {hour} is an independent amount-concentration anomaly. "
            "Classifier output is supporting evidence and was not used to select this action. "
            "User-provided labels were not live decision inputs."
        )
    elif "elevated transaction volume" in signals or any("concentration" in item for item in signals):
        verdict = "review_recommended"
        action_type = "review_time_window"
        reason = (
            f"User-dataset window {hour} is an independent temporal or concentration anomaly. "
            "Classifier output is supporting evidence and was not used to select this action. "
            "User-provided labels were not live decision inputs."
        )
    else:
        verdict = "monitor_only"
        action_type = "monitor_only"
        reason = (
            f"User-dataset window {hour} can be monitored. "
            "Classifier output is supporting evidence and was not used to select this action. "
            "User-provided labels were not live decision inputs."
        )
    live_inputs = {
        "anomaly_signals": signals,
        "anomaly_live_score": anomaly.get("live_score"),
    }
    leaked = [name for name in live_inputs if name in LIVE_DECISION_FORBIDDEN]
    if leaked:
        raise CustomGovernanceError(
            "User-provided labels cannot be live custom-data decision inputs: " + ", ".join(leaked)
        )
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "anomaly_id": evidence.get("anomaly_id") or anomaly.get("anomaly_id"),
        "hour_start": hour,
        "verdict": verdict,
        "recommended_action": {
            "type": action_type,
            "scope": f"user-dataset window {hour} / anomaly {anomaly.get('anomaly_id')}",
            "reason": reason,
        },
        "live_inputs": live_inputs,
        "supporting_classifier_evidence": {
            "high_risk_count": int(model.get("high_risk_count") or classifier.get("high_risk_count") or 0)
            if (model or classifier)
            else None,
            "provenance": model.get("label") or classifier.get("model"),
            "used_for_action_selection": False,
        }
        if (model or classifier)
        else None,
        "delayed_ground_truth_used": False,
        "human_approval_required": True,
        "simulation_only": True,
        "not_a_live_payment_action": True,
        "not_money_saved": True,
        "model_is_not_llm": True,
        "reasoning_summary": report.get("summary"),
        "reasoning_provider": report.get("provider"),
    }


def record_decision(
    session_id: str,
    decision: dict[str, Any],
) -> dict[str, Any]:
    state = store_for(session_id)
    anomaly_id = str(decision.get("anomaly_id") or "")
    existing = state.decisions.get(anomaly_id) if anomaly_id else None
    if existing:
        return existing
    payload = {**decision, "session_id": session_id, "recorded_at": _now()}
    state.decisions[anomaly_id] = payload
    _audit(
        state,
        "CUSTOM_DECISION_RECORDED",
        anomaly_id,
        None,
        {
            "verdict": payload["verdict"],
            "recommended_action": payload["recommended_action"],
            "delayed_ground_truth_used": False,
        },
        session_id,
    )
    return payload


def _latest_proposal(state: CustomActionStore, anomaly_id: str) -> dict[str, Any] | None:
    matching = [item for item in state.proposals.values() if item.get("anomaly_id") == anomaly_id]
    if not matching:
        return None
    matching.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return matching[0]


def investigation_state(session_id: str, anomaly_id: str) -> dict[str, Any]:
    state = store_for(session_id)
    decision = state.decisions.get(anomaly_id)
    proposal = _latest_proposal(state, anomaly_id)
    action_id = proposal.get("action_id") if proposal else None
    approval = state.approvals.get(action_id) if action_id else None
    execution = state.executions.get(action_id) if action_id else None
    audit = [item for item in state.audit if item.get("anomaly_id") == anomaly_id]
    if approval and approval.get("approved") is True:
        approval_status = "approved"
    elif approval and approval.get("approved") is False:
        approval_status = "rejected"
    elif proposal:
        approval_status = "pending"
    else:
        approval_status = "not_applicable"
    return {
        "decision": decision,
        "proposal": proposal,
        "approval": approval,
        "execution": execution,
        "audit": audit,
        "status": {
            "decision": "recorded" if decision else "not_recorded",
            "approval": approval_status,
            "simulation": "completed" if execution and execution.get("simulated") else "not_simulated",
            "audit_count": len(audit),
        },
    }


def investigation_summary(session_id: str, anomaly_id: str) -> dict[str, Any]:
    full = investigation_state(session_id, anomaly_id)
    proposal = full.get("proposal") or {}
    return {
        **full["status"],
        "action_id": proposal.get("action_id") if isinstance(proposal, dict) else None,
    }


def propose_action(session_id: str, decision: dict[str, Any]) -> dict[str, Any]:
    state = store_for(session_id)
    anomaly_id = str(decision.get("anomaly_id") or "")
    existing = _latest_proposal(state, anomaly_id) if anomaly_id else None
    if existing:
        return existing
    recommended = decision.get("recommended_action") or {}
    action_type = recommended.get("type")
    if action_type in FORBIDDEN_ACTION_TYPES:
        raise CustomGovernanceError(f"Forbidden custom-data action type: {action_type}")
    if action_type not in ALLOWED_ACTION_TYPES:
        raise CustomGovernanceError(f"Unsupported custom-data action type: {action_type}")
    if decision.get("verdict") not in ALLOWED_VERDICTS:
        raise CustomGovernanceError("Custom-data investigation verdict is not valid.")
    if decision.get("human_approval_required") is not True:
        raise CustomGovernanceError("human_approval_required must be true.")
    if decision.get("delayed_ground_truth_used"):
        raise CustomGovernanceError("User-provided labels cannot drive a custom-data action.")
    action_id = f"cact-{uuid4().hex[:12]}"
    proposal = {
        "action_id": action_id,
        "session_id": session_id,
        "world": WORLD,
        "anomaly_id": anomaly_id,
        "action_type": action_type,
        "scope": recommended.get("scope"),
        "reason": recommended.get("reason"),
        "verdict": decision["verdict"],
        "status": "proposed",
        "human_approval_required": True,
        "simulation_only": True,
        "not_a_live_payment_action": True,
        "delayed_ground_truth_used": False,
        "live_inputs": decision.get("live_inputs"),
        "created_at": _now(),
    }
    state.proposals[action_id] = proposal
    _audit(
        state,
        "CUSTOM_ACTION_PROPOSED",
        anomaly_id,
        action_id,
        {"action_type": action_type, "simulation_only": True},
        session_id,
    )
    return proposal


def approve_action(
    session_id: str,
    action_id: str,
    approved_by: str,
    note: str | None = None,
) -> dict[str, Any]:
    state = store_for(session_id)
    proposal = state.proposals.get(action_id)
    if proposal is None:
        raise CustomGovernanceError(f"Unknown custom-data action_id: {action_id}")
    if not approved_by.strip():
        raise CustomGovernanceError("approved_by is required.")
    approval = {
        "action_id": action_id,
        "anomaly_id": proposal["anomaly_id"],
        "approved": True,
        "approved_by": approved_by.strip(),
        "approved_at": _now(),
        "note": note,
        "human_approval_required": True,
    }
    state.approvals[action_id] = approval
    proposal["status"] = "approved"
    _audit(
        state,
        "CUSTOM_ACTION_APPROVED",
        proposal["anomaly_id"],
        action_id,
        {"approved_by": approval["approved_by"], "simulation_only": True},
        session_id,
    )
    return approval


def simulate_action(session_id: str, action_id: str) -> dict[str, Any]:
    state = store_for(session_id)
    proposal = state.proposals.get(action_id)
    if proposal is None:
        raise CustomGovernanceError(f"Unknown custom-data action_id: {action_id}")
    approval = state.approvals.get(action_id)
    if not approval or not approval.get("approved"):
        raise CustomGovernanceError("Custom-data action has not been explicitly approved.")
    from app.integrations.sandbox_payments import (
        apply_after_approval,
        attach_to_execution,
        audit_details,
        internal_result,
    )

    execution = {
        "action_id": action_id,
        "anomaly_id": proposal["anomaly_id"],
        "simulated": True,
        "status": "simulated",
        "executed_at": _now(),
        "not_a_live_payment_action": True,
        "not_production_fraud_prevention": True,
        "result": internal_result(proposal["action_type"], proposal["scope"]),
    }
    sandbox = apply_after_approval(
        action_id=action_id,
        case_id=proposal["anomaly_id"],
        action_type=proposal["action_type"],
        scope=proposal["scope"],
    )
    attach_to_execution(execution, sandbox)
    state.executions[action_id] = execution
    if execution.get("simulated"):
        proposal["status"] = "simulated"
        _audit(
            state,
            "CUSTOM_ACTION_SIMULATED",
            proposal["anomaly_id"],
            action_id,
            {"action_type": proposal["action_type"], "simulation_only": True},
            session_id,
        )
        if sandbox.get("status") == "completed":
            _audit(
                state,
                "CUSTOM_RAZORPAY_TEST_SIMULATED",
                proposal["anomaly_id"],
                action_id,
                audit_details(sandbox),
                session_id,
            )
    else:
        _audit(
            state,
            "CUSTOM_RAZORPAY_TEST_FAILED",
            proposal["anomaly_id"],
            action_id,
            audit_details(sandbox),
            session_id,
        )
    return execution


def get_action(session_id: str, action_id: str) -> dict[str, Any]:
    state = store_for(session_id)
    proposal = state.proposals.get(action_id)
    if proposal is None:
        raise CustomGovernanceError(f"Unknown custom-data action_id: {action_id}")
    return {
        "proposal": proposal,
        "approval": state.approvals.get(action_id),
        "execution": state.executions.get(action_id),
        "decision": state.decisions.get(proposal["anomaly_id"]),
    }


def list_audit(session_id: str, anomaly_id: str | None = None) -> dict[str, Any]:
    state = store_for(session_id)
    events = list(state.audit)
    if anomaly_id:
        events = [item for item in events if item.get("anomaly_id") == anomaly_id]
    return {"world": WORLD, "session_id": session_id, "count": len(events), "events": events}
