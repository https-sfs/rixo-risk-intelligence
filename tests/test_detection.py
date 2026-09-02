from __future__ import annotations

from datetime import datetime

import pandas as pd

from data.generate_dataset import generate_transactions
from data.scenarios import ATTACKS, FESTIVE_END, FESTIVE_START
from detection.detector import detect_spikes
from detection.scoring import SPIKE_TYPE_COORDINATED, SPIKE_TYPE_FESTIVE


def _overlaps(window_start: str, window_end: str, start: datetime, end: datetime) -> bool:
    left = pd.Timestamp(window_start)
    right = pd.Timestamp(window_end)
    return left < pd.Timestamp(end) and right > pd.Timestamp(start)


def test_detector_identifies_injected_suspicious_windows() -> None:
    df = generate_transactions(seed=42)
    spikes = detect_spikes(df)
    coordinated = [spike for spike in spikes if spike.spike_type == SPIKE_TYPE_COORDINATED]
    assert coordinated, "detector returned no coordinated spikes"

    for spec in ATTACKS:
        matched = [
            spike
            for spike in coordinated
            if _overlaps(spike.window_start, spike.window_end, spec.start, spec.end)
        ]
        assert matched, f"no coordinated spike overlapped {spec.name}"
        assert any(spike.volume >= 16 for spike in matched)


def test_detector_does_not_treat_festive_volume_as_fraud() -> None:
    df = generate_transactions(seed=42)
    spikes = detect_spikes(df)

    festive_spikes = [
        spike
        for spike in spikes
        if _overlaps(spike.window_start, spike.window_end, FESTIVE_START, FESTIVE_END)
    ]
    assert festive_spikes, "expected at least one festive volume spike"

    misclassified = [
        spike for spike in festive_spikes if spike.spike_type == SPIKE_TYPE_COORDINATED
    ]
    assert misclassified == []
    assert all(spike.spike_type == SPIKE_TYPE_FESTIVE for spike in festive_spikes)

    coordinated_outside_attacks = []
    for spike in spikes:
        if spike.spike_type != SPIKE_TYPE_COORDINATED:
            continue
        if any(_overlaps(spike.window_start, spike.window_end, spec.start, spec.end) for spec in ATTACKS):
            continue
        coordinated_outside_attacks.append(spike)
    assert coordinated_outside_attacks == []
