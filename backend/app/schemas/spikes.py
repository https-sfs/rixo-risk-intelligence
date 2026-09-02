from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class SpikeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spike_id: str
    window_start: str
    window_end: str
    spike_type: str
    severity: str
    volume: int
    baseline_volume: float | None
    volume_change_ratio: float | None
    fraud_rate: float
    baseline_fraud_rate: float | None
    failure_rate: float
    unique_accounts: int
    unique_devices: int
    unique_ip_subnets: int
    unique_pincodes: int
    top_skus: Any
    anomaly_reasons: Any
    anomaly_score: float
    coordination_score: float


class SpikeListOut(BaseModel):
    spikes: list[SpikeOut]
    count: int
    heldout_detection: dict[str, Any] | None = None
    heldout_investigation: dict[str, Any] | None = None
