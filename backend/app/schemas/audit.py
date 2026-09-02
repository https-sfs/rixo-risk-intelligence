from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditEventOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: str
    timestamp: str
    action_id: str
    spike_id: str
    event_type: str
    actor: str
    details: dict[str, Any] = Field(default_factory=dict)


class AuditListOut(BaseModel):
    events: list[AuditEventOut]
    count: int
