"""Action state. Optional SQLite durability sits behind this same interface."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from agent.actions.models import ActionProposal, Approval, AuditEvent, ExecutionResult

SYNTHETIC_WORLD = "SYNTHETIC SCENARIO"


class ActionStore:
    def __init__(self, db: Any | None = None) -> None:
        self.proposals: dict[str, ActionProposal] = {}
        self.approvals: dict[str, Approval] = {}
        self.executions: dict[str, ExecutionResult] = {}
        self.audit: list[AuditEvent] = []
        self.db = db
        if db is not None:
            self._load()

    def _load(self) -> None:
        snapshot = self.db.load_world(SYNTHETIC_WORLD)
        self.proposals = {
            key: ActionProposal(**payload) for key, payload in snapshot["proposals"].items()
        }
        self.approvals = {
            key: Approval(**payload) for key, payload in snapshot["approvals"].items()
        }
        self.executions = {
            key: ExecutionResult(**payload) for key, payload in snapshot["executions"].items()
        }
        self.audit = [AuditEvent(**payload) for payload in snapshot["audit"]]

    def persist(
        self,
        *,
        proposals: list[ActionProposal] | None = None,
        approvals: list[Approval] | None = None,
        executions: list[ExecutionResult] | None = None,
        audits: list[AuditEvent] | None = None,
    ) -> None:
        if self.db is None:
            return
        self.db.commit_bundle(
            SYNTHETIC_WORLD,
            proposals=[item.to_dict() for item in proposals or []],
            approvals=[item.to_dict() for item in approvals or []],
            executions=[item.to_dict() for item in executions or []],
            audits=[asdict(item) for item in audits or []],
        )

    def put_proposal(self, proposal: ActionProposal) -> ActionProposal:
        self.proposals[proposal.action_id] = proposal
        self.persist(proposals=[proposal])
        return proposal

    def get_proposal(self, action_id: str) -> ActionProposal | None:
        return self.proposals.get(action_id)

    def put_approval(self, approval: Approval) -> Approval:
        self.approvals[approval.action_id] = approval
        self.persist(approvals=[approval])
        return approval

    def get_approval(self, action_id: str) -> Approval | None:
        return self.approvals.get(action_id)

    def put_execution(self, result: ExecutionResult) -> ExecutionResult:
        self.executions[result.action_id] = result
        self.persist(executions=[result])
        return result

    def append_audit(self, event: AuditEvent) -> AuditEvent:
        self.audit.append(event)
        self.persist(audits=[event])
        return event

    def latest_proposal_for_spike(self, spike_id: str) -> ActionProposal | None:
        matching = [item for item in self.proposals.values() if item.spike_id == spike_id]
        if not matching:
            return None
        matching.sort(key=lambda item: item.created_at, reverse=True)
        return matching[0]

    def events_for(self, action_id: str) -> list[AuditEvent]:
        return [event for event in self.audit if event.action_id == action_id]

    def events_for_spike(self, spike_id: str) -> list[AuditEvent]:
        return [event for event in self.audit if event.spike_id == spike_id]
