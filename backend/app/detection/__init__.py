"""Statistical anomaly and spike detection layer."""

from detection.detector import (
    SpikeRecord,
    compute_hourly_windows,
    detect_spikes,
    spikes_to_frame,
)
from detection.scoring import (
    SPIKE_TYPE_COORDINATED,
    SPIKE_TYPE_FESTIVE,
    SPIKE_TYPE_ORDINARY,
)

__all__ = [
    "SPIKE_TYPE_COORDINATED",
    "SPIKE_TYPE_FESTIVE",
    "SPIKE_TYPE_ORDINARY",
    "SpikeRecord",
    "compute_hourly_windows",
    "detect_spikes",
    "spikes_to_frame",
]
