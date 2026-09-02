from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CounterfactualIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    world: str = Field(description="Must be SYNTHETIC SCENARIO")
    spike_id: str
    action_type: str
    scope: str
