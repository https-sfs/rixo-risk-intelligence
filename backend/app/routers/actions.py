from fastapi import APIRouter

from agent.actions.errors import ActionError
from agent.actions.service import (
    approve_action,
    default_store,
    execute_action,
    propose_from_report,
)
from app.schemas.actions import (
    ActionProposalOut,
    ActionStateOut,
    ApprovalIn,
    ApprovalOut,
    ExecutionOut,
    InvestigationRecommendIn,
)

router = APIRouter(prefix="/api/actions", tags=["actions"])


def _proposal_out(payload: dict) -> ActionProposalOut:
    return ActionProposalOut(
        action_id=payload["action_id"],
        spike_id=payload["spike_id"],
        action_type=payload["action_type"],
        scope=payload["scope"],
        reason=payload["reason"],
        source_provider=payload["source_provider"],
        created_at=payload["created_at"],
        status=payload["status"],
        human_approval_required=payload["human_approval_required"],
        verdict=payload["verdict"],
    )


@router.post("/propose", response_model=ActionProposalOut)
def propose(body: InvestigationRecommendIn) -> ActionProposalOut:
    proposal = propose_from_report(body.model_dump())
    return _proposal_out(proposal.to_dict())


@router.post("/{action_id}/approve", response_model=ApprovalOut)
def approve(action_id: str, body: ApprovalIn) -> ApprovalOut:
    approval = approve_action(action_id, approved_by=body.approved_by, note=body.note)
    return ApprovalOut.model_validate(approval.to_dict())


@router.post("/{action_id}/execute", response_model=ExecutionOut)
def execute(action_id: str) -> ExecutionOut:
    result = execute_action(action_id)
    return ExecutionOut.model_validate(result.to_dict())


@router.get("/{action_id}", response_model=ActionStateOut)
def get_action(action_id: str) -> ActionStateOut:
    store = default_store()
    proposal = store.get_proposal(action_id)
    if proposal is None:
        raise ActionError(f"Unknown action_id: {action_id}")
    approval = store.get_approval(action_id)
    execution = store.executions.get(action_id)
    return ActionStateOut(
        proposal=_proposal_out(proposal.to_dict()),
        approval=ApprovalOut.model_validate(approval.to_dict()) if approval else None,
        execution=ExecutionOut.model_validate(execution.to_dict()) if execution else None,
        verification=execution.verification if execution else None,
    )
