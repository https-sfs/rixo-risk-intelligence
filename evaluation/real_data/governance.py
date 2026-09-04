"""IEEE-CIS governed simulation: decide → approve → simulate → audit.

Isolated from locked synthetic agent.actions. Not a payment API.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from evaluation.real_data.mapper import DATASET_NAME, WORLD
from models.ieee_fraud import PROVENANCE

ALLOWED_ACTION_TYPES = frozenset(
    {
        "review_hour",
        "flag_high_risk_transactions",
        "take_no_simulated_action",
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
    }
)
ALLOWED_VERDICTS = frozenset({"review_recommended", "monitor_only"})
LIVE_DECISION_FORBIDDEN = frozenset(
    {
        "isFraud",
        "fraud_label",
        "evaluation_overlay",
        "delayed_ground_truth",
        "labelled_fraud_rate",
        "fraud_rate",
    }
)


class RealGovernanceError(ValueError):
    """IEEE governance contract violation."""


class RealActionStore:
    def __init__(self, db: Any | None = None) -> None:
        self.decisions: dict[str, dict[str, Any]] = {}
        self.proposals: dict[str, dict[str, Any]] = {}
        self.approvals: dict[str, dict[str, Any]] = {}
        self.executions: dict[str, dict[str, Any]] = {}
        self.audit: list[dict[str, Any]] = []
        # IEEE-only propose keys. Same store, optional SQLite durability.
        self.idempotency: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.db = db
        if db is not None:
            snapshot = db.load_world(WORLD)
            self.decisions = snapshot["decisions"]
            self.proposals = snapshot["proposals"]
            self.approvals = snapshot["approvals"]
            self.executions = snapshot["executions"]
            self.audit = snapshot["audit"]
            self.idempotency = snapshot["idempotency"]

    def persist(
        self,
        *,
        decisions: list[dict[str, Any]] | None = None,
        proposals: list[dict[str, Any]] | None = None,
        approvals: list[dict[str, Any]] | None = None,
        executions: list[dict[str, Any]] | None = None,
        audits: list[dict[str, Any]] | None = None,
        idempotency: list[tuple[str, dict[str, Any]]] | None = None,
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
            idempotency=idempotency,
        )

    def _reload(self) -> None:
        if self.db is None:
            return
        snapshot = self.db.load_world(WORLD)
        self.decisions.update(snapshot["decisions"])
        self.proposals.update(snapshot["proposals"])
        self.approvals.update(snapshot["approvals"])
        self.executions.update(snapshot["executions"])
        self.idempotency.update(snapshot["idempotency"])
        known = {item.get("audit_event_id") for item in self.audit}
        for event in snapshot["audit"]:
            if event.get("audit_event_id") not in known:
                self.audit.append(event)

    def get_proposal(self, action_id: str) -> dict[str, Any] | None:
        found = self.proposals.get(action_id)
        if found is not None or self.db is None:
            return found
        self._reload()
        return self.proposals.get(action_id)


_STORE = RealActionStore()


def default_store() -> RealActionStore:
    return _STORE


def bind_store(store: RealActionStore) -> RealActionStore:
    global _STORE
    _STORE = store
    return _STORE


def reset_store() -> RealActionStore:
    global _STORE
    _STORE = RealActionStore()
    return _STORE


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _audit(
    store: RealActionStore,
    kind: str,
    anomaly_id: str,
    action_id: str | None,
    details: dict[str, Any],
) -> dict[str, Any]:
    event = {
        "audit_event_id": f"raud-{uuid4().hex[:12]}",
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
        raise RealGovernanceError(
            "Delayed ground truth cannot be a live IEEE decision input: " + ", ".join(leaked)
        )


def decide_from_investigation(
    anomaly: dict[str, Any],
    evidence: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    """Recommend a simulated action from live IEEE-CIS anomaly evidence only.

    Classifier ``high_risk_count`` is supporting MODEL PREDICTION evidence. It
    is not an action-selection input. Delayed ground truth is never a live input.
    """
    live = evidence.get("live_evidence") or {}
    model = evidence.get("model_prediction") or {}
    temporal = ((live.get("temporal_anomaly") or {}).get("value")) or {}
    signals = list(temporal.get("signals") or anomaly.get("signals") or [])
    hour = evidence.get("relative_hour_bucket") or anomaly.get("relative_hour_bucket")
    amount_hit = "elevated transaction amount" in signals
    if amount_hit:
        verdict = "review_recommended"
        action_type = "flag_high_risk_transactions"
        reason = (
            f"Relative hour {hour} is a live IEEE-CIS amount-concentration anomaly. "
            "The recommended action is based on hour-level anomaly evidence. "
            "Classifier overlay is supporting evidence and was not used to select this action. "
            "Delayed ground truth was not used as a live decision input."
        )
    elif signals:
        verdict = "monitor_only"
        action_type = "review_hour"
        reason = (
            f"Relative hour {hour} is a live IEEE-CIS anomaly "
            f"({', '.join(signals)}). "
            "The recommended action is based on hour-level anomaly evidence. "
            "Classifier overlay is supporting evidence and was not used to select this action. "
            "Delayed ground truth was not used as a live decision input."
        )
    else:
        verdict = "monitor_only"
        action_type = "take_no_simulated_action"
        reason = (
            f"Relative hour {hour} has no stronger live IEEE-CIS anomaly signal. "
            "Classifier overlay is supporting evidence and was not used to select this action. "
            "Delayed ground truth was not used as a live decision input."
        )
    decision = {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "anomaly_id": evidence.get("anomaly_id") or anomaly.get("anomaly_id"),
        "relative_hour_bucket": hour,
        "verdict": verdict,
        "recommended_action": {
            "type": action_type,
            "scope": f"IEEE-CIS relative hour bucket {hour} / anomaly {anomaly.get('anomaly_id')}",
            "reason": reason,
        },
        "live_inputs": {
            "anomaly_signals": signals,
            "anomaly_live_score": anomaly.get("live_score") or temporal.get("live_score"),
        },
        "supporting_classifier_evidence": {
            "high_risk_count": int(model.get("high_risk_count") or 0),
            "threshold": model.get("threshold"),
            "sample_scope": model.get("sample_scope"),
            "provenance": PROVENANCE,
            "used_for_action_selection": False,
        }
        if model
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
    return decision


def record_decision(decision: dict[str, Any], store: RealActionStore | None = None) -> dict[str, Any]:
    state = store or default_store()
    anomaly_id = str(decision.get("anomaly_id") or "")
    existing = state.decisions.get(anomaly_id) if anomaly_id else None
    if existing:
        return existing
    payload = {**decision, "recorded_at": _now()}
    state.decisions[anomaly_id] = payload
    event = _audit(
        state,
        "IEEE_DECISION_RECORDED",
        anomaly_id,
        None,
        {
            "verdict": payload["verdict"],
            "recommended_action": payload["recommended_action"],
            "delayed_ground_truth_used": False,
            "evidence_provenance": {
                "anomaly": "OBSERVED",
                "model_prediction": PROVENANCE,
                "reasoning": payload.get("reasoning_provider"),
            },
        },
    )
    state.persist(decisions=[payload], audits=[event])
    return payload


def fingerprint_ieee_propose(anomaly_id: str, provider: str = "auto") -> dict[str, str]:
    """Logical IEEE propose request. Keys are not hashed request bodies."""
    return {
        "world": WORLD,
        "anomaly_id": str(anomaly_id or "").strip(),
        "provider": str(provider or "auto").strip() or "auto",
    }


def _create_proposal(decision: dict[str, Any], state: RealActionStore, *, persist: bool = True) -> dict[str, Any]:
    recommended = decision.get("recommended_action") or {}
    action_type = recommended.get("type")
    if action_type in FORBIDDEN_ACTION_TYPES:
        raise RealGovernanceError(f"Forbidden IEEE action type: {action_type}")
    if action_type not in ALLOWED_ACTION_TYPES:
        raise RealGovernanceError(f"Unsupported IEEE action type: {action_type}")
    if decision.get("verdict") not in ALLOWED_VERDICTS:
        raise RealGovernanceError("IEEE investigation verdict is not valid.")
    if decision.get("human_approval_required") is not True:
        raise RealGovernanceError("human_approval_required must be true.")
    if decision.get("delayed_ground_truth_used"):
        raise RealGovernanceError("Delayed ground truth cannot drive an IEEE action.")
    action_id = f"ract-{uuid4().hex[:12]}"
    proposal = {
        "action_id": action_id,
        "world": WORLD,
        "anomaly_id": decision["anomaly_id"],
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
        "evidence_provenance": {
            "anomaly": "OBSERVED",
            "model_prediction": PROVENANCE,
            "reasoning": decision.get("reasoning_provider"),
        },
        "created_at": _now(),
    }
    state.proposals[action_id] = proposal
    event = _audit(
        state,
        "IEEE_ACTION_PROPOSED",
        decision["anomaly_id"],
        action_id,
        {
            "action_type": action_type,
            "scope": proposal["scope"],
            "simulation_only": True,
        },
    )
    if persist:
        state.persist(proposals=[proposal], audits=[event])
    return proposal


def propose_action(
    decision: dict[str, Any],
    store: RealActionStore | None = None,
    *,
    idempotency_key: str | None = None,
    provider: str = "auto",
) -> dict[str, Any]:
    """Create an IEEE proposal. Optional idempotency_key is IEEE-scoped only.

    Requests without a key keep the existing create-a-new-proposal behavior.
    Same key + same anomaly_id/provider returns the original proposal.
    Same key + a different logical request is an idempotency-key conflict.
    In-process lock prevents a check-then-create race in this single process.
    """
    state = store or default_store()
    key = str(idempotency_key or "").strip()
    if not key:
        return _create_proposal(decision, state)
    fingerprint = fingerprint_ieee_propose(str(decision.get("anomaly_id") or ""), provider)
    with state.lock:
        recorded = state.idempotency.get(key)
        if recorded:
            if recorded.get("fingerprint") != fingerprint:
                raise RealGovernanceError(
                    "IEEE idempotency-key conflict: this key already belongs to a "
                    "different IEEE proposal request."
                )
            existing = state.proposals.get(str(recorded.get("action_id") or ""))
            if existing is None:
                raise RealGovernanceError("IEEE idempotency key points to an unknown proposal.")
            return existing
        proposal = _create_proposal(decision, state, persist=False)
        record = {
            "action_id": proposal["action_id"],
            "fingerprint": fingerprint,
            "world": WORLD,
        }
        state.idempotency[key] = record
        event = state.audit[-1] if state.audit else None
        state.persist(
            proposals=[proposal],
            audits=[event] if event else None,
            idempotency=[(key, record)],
        )
        return proposal


def approve_action(
    action_id: str,
    approved_by: str,
    note: str | None = None,
    store: RealActionStore | None = None,
) -> dict[str, Any]:
    state = store or default_store()
    proposal = state.get_proposal(action_id)
    if proposal is None:
        raise RealGovernanceError(f"Unknown IEEE action_id: {action_id}")
    if not approved_by.strip():
        raise RealGovernanceError("approved_by is required.")
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
        "IEEE_ACTION_APPROVED",
        proposal["anomaly_id"],
        action_id,
        {"approved_by": approval["approved_by"], "simulation_only": True},
    )
    state.persist(proposals=[proposal], approvals=[approval], audits=[event])
    return approval


def simulate_action(action_id: str, store: RealActionStore | None = None) -> dict[str, Any]:
    state = store or default_store()
    proposal = state.get_proposal(action_id)
    if proposal is None:
        raise RealGovernanceError(f"Unknown IEEE action_id: {action_id}")
    approval = state.approvals.get(action_id)
    if not approval or not approval.get("approved"):
        raise RealGovernanceError("IEEE action has not been explicitly approved.")
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
                "IEEE_ACTION_SIMULATED",
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
                    "IEEE_RAZORPAY_TEST_SIMULATED",
                    proposal["anomaly_id"],
                    action_id,
                    audit_details(sandbox),
                )
            )
    else:
        events.append(
            _audit(
                state,
                "IEEE_RAZORPAY_TEST_FAILED",
                proposal["anomaly_id"],
                action_id,
                audit_details(sandbox),
            )
        )
    state.persist(proposals=[proposal], executions=[execution], audits=events)
    return execution


def get_action(action_id: str, store: RealActionStore | None = None) -> dict[str, Any]:
    state = store or default_store()
    proposal = state.get_proposal(action_id)
    if proposal is None:
        raise RealGovernanceError(f"Unknown IEEE action_id: {action_id}")
    return {
        "proposal": proposal,
        "approval": state.approvals.get(action_id),
        "execution": state.executions.get(action_id),
        "decision": state.decisions.get(proposal["anomaly_id"]),
    }


def list_audit(anomaly_id: str | None = None, store: RealActionStore | None = None) -> dict[str, Any]:
    state = store or default_store()
    events = list(state.audit)
    if anomaly_id:
        events = [item for item in events if item.get("anomaly_id") == anomaly_id]
    return {"world": WORLD, "count": len(events), "events": events}


def _latest_proposal(state: RealActionStore, anomaly_id: str) -> dict[str, Any] | None:
    matching = [item for item in state.proposals.values() if item.get("anomaly_id") == anomaly_id]
    if not matching:
        return None
    matching.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return matching[0]


def investigation_state(anomaly_id: str, store: RealActionStore | None = None) -> dict[str, Any]:
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
