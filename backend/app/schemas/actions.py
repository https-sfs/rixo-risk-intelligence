from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class InvestigationRecommendIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    spike_id: str
    verdict: str
    recommended_action: dict[str, Any]
    human_approval_required: bool = True
    provider: str | None = None
    summary: str | None = None
    confidence: float | None = None
    supporting_evidence: list[dict[str, Any]] | None = None
    contradicting_evidence: list[dict[str, Any]] | None = None
    key_entities: list[dict[str, Any]] | None = None
    reasoning: str | None = None
    limitations: list[str] | None = None


class ActionProposalOut(BaseModel):
    action_id: str
    spike_id: str
    action_type: str
    scope: str
    reason: str
    source_provider: str
    created_at: str
    status: str
    human_approval_required: bool
    verdict: str


class ApprovalIn(BaseModel):
    approved_by: str = Field(min_length=1)
    note: str = ""


class ApprovalOut(BaseModel):
    action_id: str
    approved: bool
    approved_by: str
    approved_at: str
    note: str


class ExecutionOut(BaseModel):
    action_id: str
    status: str
    simulated: bool
    affected_scope: str
    message: str
    verification: dict[str, Any]
    audit_event_id: str


class ActionStateOut(BaseModel):
    proposal: ActionProposalOut
    approval: ApprovalOut | None = None
    execution: ExecutionOut | None = None
    verification: dict[str, Any] | None = None
