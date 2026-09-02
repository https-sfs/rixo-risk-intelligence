from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ProviderName = Literal["deterministic", "llm"]


class EvidenceItemOut(BaseModel):
    fact: str
    source: str


class KeyEntityOut(BaseModel):
    entity_type: str
    entity_id: str
    reason: str


class RecommendedActionOut(BaseModel):
    type: str
    scope: str
    reason: str


class InvestigationReportOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    spike_id: str
    verdict: str
    confidence: float
    summary: str
    supporting_evidence: list[EvidenceItemOut]
    contradicting_evidence: list[EvidenceItemOut]
    key_entities: list[KeyEntityOut]
    reasoning: str
    recommended_action: RecommendedActionOut
    human_approval_required: bool
    limitations: list[str] = Field(default_factory=list)
    provider: str


class InvestigationOut(BaseModel):
    report: InvestigationReportOut
    evidence_source: str
    provider: str
    classifier: dict[str, Any] | None = None
    investigation_state: dict[str, Any] | None = None
    investigation_intelligence: dict[str, Any] | None = None
    investigation_agent: dict[str, Any] | None = None
