"""January 2026 governed simulation: decide → approve → simulate → audit.

Isolated from IEEE governance and locked synthetic agent.actions.
Not a payment API. Source-model outputs and is_fraud are not live inputs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from evaluation.recent_data.mapper import DATASET_NAME, SOURCE_MODEL_OUTPUTS, WORLD

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
        *SOURCE_MODEL_OUTPUTS,
    }
)


class RecentGovernanceError(ValueError):
    """January 2026 governance contract violation."""


class RecentActionStore:
    def __init__(self, db: Any | None = None) -> None:
        self.decisions: dict[str, dict[str, Any]] = {}
        self.proposals: dict[str, dict[str, Any]] = {}
        self.approvals: dict[str, dict[str, Any]] = {}
        self.executions: dict[str, dict[str, Any]] = {}
        self.audit: list[dict[str, Any]] = []
        self.db = db
        if db is not None:
            snapshot = db.load_world(WORLD)
            self.decisions = snapshot["decisions"]
            self.proposals = snapshot["proposals"]
            self.approvals = snapshot["approvals"]
            self.executions = snapshot["executions"]
            self.audit = snapshot["audit"]

    def persist(
        self,
        *,
        decisions: list[dict[str, Any]] | None = None,
        proposals: list[dict[str, Any]] | None = None,
        approvals: list[dict[str, Any]] | None = None,
        executions: list[dict[str, Any]] | None = None,
        audits: list[dict[str, Any]] | None = None,
    ) -> None:
        if self.db is None:
            return
        self.db.commit_bundle(
            WORLD,
            decisions=decisions,
            proposals=proposals,
            approvals=approvals,
            executions=executions,
            audits=audits,
        )


_STORE = RecentActionStore()


def default_store() -> RecentActionStore:
    return _STORE


def bind_store(store: RecentActionStore) -> RecentActionStore:
    global _STORE
    _STORE = store
    return _STORE


def reset_store() -> RecentActionStore:
    global _STORE
    _STORE = RecentActionStore()
    return _STORE


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _audit(
    store: RecentActionStore,
    kind: str,
    anomaly_id: str,
    action_id: str | None,
    details: dict[str, Any],
) -> dict[str, Any]:
    event = {
        "audit_event_id": f"naud-{uuid4().hex[:12]}",
        "kind": kind,
        "world": WORLD,
        "dataset": DATASET_NAME,
        "anomaly_id": anomaly_id,
        "action_id": action_id,
        "timestamp": _now(),
        "simulation_only": True,
        "not_a_live_payment_action": True,
        "details": details,
    }
    store.audit.append(event)
    return event


def _assert_no_live_ground_truth(payload: dict[str, Any]) -> None:
    leaked = [name for name in payload if name in LIVE_DECISION_FORBIDDEN]
    if leaked:
        raise RecentGovernanceError(
            "Delayed ground truth and source-model outputs cannot be live January 2026 "
            "decision inputs: " + ", ".join(leaked)
        )


def decide_from_investigation(
    anomaly: dict[str, Any],
    evidence: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    """Recommend a simulated action from live January anomalies only.

    Classifier ``high_risk_count`` is not a January decision input. The shared
    classifier is supporting evidence in every world and does not select actions.
    """
    live = evidence.get("live_evidence") or {}
    signals = list(anomaly.get("signals") or [])
    hour = evidence.get("hour_start") or anomaly.get("hour_start")
    amount_hit = "elevated transaction amount" in signals
    volume_hit = "elevated transaction volume" in signals
    if amount_hit:
        verdict = "review_recommended"
        action_type = "flag_for_human_review"
        reason = (
            f"January 2026 hour {hour} is an independent amount-concentration anomaly. "
            "Source-model outputs and is_fraud were not used as live decision inputs."
        )
    elif volume_hit:
        verdict = "review_recommended"
        action_type = "review_time_window"
        reason = (
            f"January 2026 hour {hour} is an independent temporal-volume anomaly. "
            "Source-model outputs and is_fraud were not used as live decision inputs."
        )
    else:
        verdict = "monitor_only"
        action_type = "monitor_only"
        reason = (
            f"January 2026 hour {hour} is a recent-data anomaly without a stronger "
            "live amount or volume signal. Continue monitoring. "
            "Source-model outputs and is_fraud were not used as live decision inputs."
        )
    decision = {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "anomaly_id": evidence.get("anomaly_id") or anomaly.get("anomaly_id"),
        "hour_start": hour,
        "verdict": verdict,
        "recommended_action": {
            "type": action_type,
            "scope": f"January 2026 hour {hour} / anomaly {anomaly.get('anomaly_id')}",
            "reason": reason,
        },
        "live_inputs": {
            "anomaly_signals": signals,
            "anomaly_live_score": anomaly.get("live_score"),
            "transaction_count": (live.get("transaction_count") or {}).get("value"),
            "amount_usd": (live.get("amount_usd") or {}).get("value"),
        },
        "delayed_ground_truth_used": False,
        "source_model_used": False,
        "ieee_model_used": False,
        "human_approval_required": True,
        "simulation_only": True,
        "not_a_live_payment_action": True,
        "not_money_saved": True,
        "model_is_not_llm": True,
        "reasoning_summary": report.get("summary"),
        "reasoning_provider": report.get("provider"),
    }
    _assert_no_live_ground_truth(decision["live_inputs"])
    return decision


def record_decision(decision: dict[str, Any], store: RecentActionStore | None = None) -> dict[str, Any]:
    state = store or default_store()
    anomaly_id = str(decision.get("anomaly_id") or "")
    existing = state.decisions.get(anomaly_id) if anomaly_id else None
    if existing:
        return existing
    payload = {**decision, "recorded_at": _now()}
    state.decisions[anomaly_id] = payload
    event = _audit(
        state,
        "RECENT_DECISION_RECORDED",
        anomaly_id,
        None,
        {
            "verdict": payload["verdict"],
            "recommended_action": payload["recommended_action"],
            "delayed_ground_truth_used": False,
            "source_model_used": False,
            "ieee_model_used": False,
            "evidence_provenance": {
                "anomaly": "OBSERVED",
                "reasoning": payload.get("reasoning_provider"),
            },
        },
    )
    state.persist(decisions=[payload], audits=[event])
    return payload


def _latest_proposal(state: RecentActionStore, anomaly_id: str) -> dict[str, Any] | None:
    matching = [item for item in state.proposals.values() if item.get("anomaly_id") == anomaly_id]
    if not matching:
        return None
    matching.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return matching[0]


def investigation_state(anomaly_id: str, store: RecentActionStore | None = None) -> dict[str, Any]:
    state = store or default_store()
    decision = state.decisions.get(anomaly_id)
    proposal = _latest_proposal(state, anomaly_id)
    action_id = proposal.get("action_id") if proposal else None
    approval = state.approvals.get(action_id) if action_id else None
    execution = state.executions.get(action_id) if action_id else None
    audit = [item for item in state.audit if item.get("anomaly_id") == anomaly_id]
    if approval and approval.get("approved") is True:
        approval_status = "approved"
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


def propose_action(decision: dict[str, Any], store: RecentActionStore | None = None) -> dict[str, Any]:
    state = store or default_store()
    anomaly_id = str(decision.get("anomaly_id") or "")
    existing = _latest_proposal(state, anomaly_id) if anomaly_id else None
    if existing:
        return existing
    recommended = decision.get("recommended_action") or {}
    action_type = recommended.get("type")
    if action_type in FORBIDDEN_ACTION_TYPES:
        raise RecentGovernanceError(f"Forbidden January 2026 action type: {action_type}")
    if action_type not in ALLOWED_ACTION_TYPES:
        raise RecentGovernanceError(f"Unsupported January 2026 action type: {action_type}")
    if decision.get("verdict") not in ALLOWED_VERDICTS:
        raise RecentGovernanceError("January 2026 investigation verdict is not valid.")
    if decision.get("human_approval_required") is not True:
        raise RecentGovernanceError("human_approval_required must be true.")
    if decision.get("delayed_ground_truth_used") or decision.get("source_model_used"):
        raise RecentGovernanceError(
            "Delayed ground truth and source-model outputs cannot drive a January 2026 action."
        )
    if decision.get("ieee_model_used"):
        raise RecentGovernanceError("The IEEE-CIS classifier cannot drive a January 2026 action.")
    action_id = f"nact-{uuid4().hex[:12]}"
    proposal = {
        "action_id": action_id,
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
        "source_model_used": False,
        "ieee_model_used": False,
        "live_inputs": decision.get("live_inputs"),
        "evidence_provenance": {
            "anomaly": "OBSERVED",
            "reasoning": decision.get("reasoning_provider"),
        },
        "created_at": _now(),
    }
    state.proposals[action_id] = proposal
    event = _audit(
        state,
        "RECENT_ACTION_PROPOSED",
        anomaly_id,
        action_id,
        {
            "action_type": action_type,
            "scope": proposal["scope"],
            "simulation_only": True,
        },
    )
    state.persist(proposals=[proposal], audits=[event])
    return proposal


def approve_action(
    action_id: str,
    approved_by: str,
    note: str | None = None,
    store: RecentActionStore | None = None,
) -> dict[str, Any]:
    state = store or default_store()
    proposal = state.proposals.get(action_id)
    if proposal is None:
        raise RecentGovernanceError(f"Unknown January 2026 action_id: {action_id}")
    if not approved_by.strip():
        raise RecentGovernanceError("approved_by is required.")
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
    event = _audit(
        state,
        "RECENT_ACTION_APPROVED",
        proposal["anomaly_id"],
        action_id,
        {"approved_by": approval["approved_by"], "simulation_only": True},
    )
    state.persist(proposals=[proposal], approvals=[approval], audits=[event])
    return approval


def simulate_action(action_id: str, store: RecentActionStore | None = None) -> dict[str, Any]:
    state = store or default_store()
    proposal = state.proposals.get(action_id)
    if proposal is None:
        raise RecentGovernanceError(f"Unknown January 2026 action_id: {action_id}")
    approval = state.approvals.get(action_id)
    if not approval or not approval.get("approved"):
        raise RecentGovernanceError("January 2026 action has not been explicitly approved.")
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
    events: list[dict[str, Any]] = []
    if execution.get("simulated"):
        proposal["status"] = "simulated"
        events.append(
            _audit(
                state,
                "RECENT_ACTION_SIMULATED",
                proposal["anomaly_id"],
                action_id,
                {
                    "action_type": proposal["action_type"],
                    "simulation_only": True,
                    "not_a_live_payment_action": True,
                },
            )
        )
        if sandbox.get("status") == "completed":
            events.append(
                _audit(
                    state,
                    "RECENT_RAZORPAY_TEST_SIMULATED",
                    proposal["anomaly_id"],
                    action_id,
                    audit_details(sandbox),
                )
            )
    else:
        events.append(
            _audit(
                state,
                "RECENT_RAZORPAY_TEST_FAILED",
                proposal["anomaly_id"],
                action_id,
                audit_details(sandbox),
            )
        )
    state.persist(proposals=[proposal], executions=[execution], audits=events)
    return execution


def get_action(action_id: str, store: RecentActionStore | None = None) -> dict[str, Any]:
    state = store or default_store()
    proposal = state.proposals.get(action_id)
    if proposal is None:
        raise RecentGovernanceError(f"Unknown January 2026 action_id: {action_id}")
    return {
        "proposal": proposal,
        "approval": state.approvals.get(action_id),
        "execution": state.executions.get(action_id),
        "decision": state.decisions.get(proposal["anomaly_id"]),
    }


def list_audit(anomaly_id: str | None = None, store: RecentActionStore | None = None) -> dict[str, Any]:
    state = store or default_store()
    events = list(state.audit)
    if anomaly_id:
        events = [item for item in events if item.get("anomaly_id") == anomaly_id]
    return {"world": WORLD, "count": len(events), "events": events}
