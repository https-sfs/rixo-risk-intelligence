"""Hour-level evaluation labels from scenario calendars.

Hidden synthetic truth for evaluation only. Independent of detector output
and of delayed transaction labels. The live detector, tools, and reasoner
must not import this module.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from data.scenarios import ATTACKS, FESTIVE_END, FESTIVE_START

LABEL_COORDINATED = "coordinated_abuse"
LABEL_FESTIVE = "legitimate_festive"
LABEL_BACKGROUND = "background"

PREDICTED_COORDINATED = "suspicious_coordinated_spike"
PREDICTED_FESTIVE = "legitimate_festive_spike"
PREDICTED_BACKGROUND = "ordinary"


def label_hour(window_start: datetime | pd.Timestamp | str) -> str:
    """Map a clock hour to the scenario that injected activity there."""
    start = pd.Timestamp(window_start).to_pydatetime().replace(tzinfo=None)
    for spec in ATTACKS:
        if spec.start <= start < spec.end:
            return LABEL_COORDINATED
    if FESTIVE_START <= start < FESTIVE_END:
        return LABEL_FESTIVE
    return LABEL_BACKGROUND


def map_detector_prediction(spike_type: str) -> str:
    """Translate a detector class into the evaluation label space."""
    if spike_type == PREDICTED_COORDINATED:
        return LABEL_COORDINATED
    if spike_type == PREDICTED_FESTIVE:
        return LABEL_FESTIVE
    return LABEL_BACKGROUND


def label_windows(window_starts: list[object] | pd.Series) -> list[str]:
    return [label_hour(start) for start in window_starts]
