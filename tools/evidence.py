"""Assemble one JSON-serializable investigation evidence object."""

from __future__ import annotations

import json
from typing import Any

from models.ieee_fraud.adapt import adapt_synthetic
from models.ieee_fraud.infer import (
    classifier_from_scores,
    get_cached,
    record_invocation,
    score_canonical_frame,
)
from tools.baseline import calculate_baseline_comparison
from tools.concentration import calculate_concentration
from tools.load import load_spike_transactions
from tools.metrics import calculate_entity_counts, calculate_window_metrics
from tools.relationships import calculate_relationships
from tools.serialize import json_safe
from tools.velocity import calculate_velocity

SYNTHETIC_WORLD = "SYNTHETIC SCENARIO"


def _parse_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def build_investigation_evidence(spike_id: str) -> dict[str, Any]:
    spike, window = load_spike_transactions(spike_id)
    metrics = calculate_window_metrics(window)
    evidence = {
        "spike": {
            "spike_id": spike["spike_id"],
            "window_start": spike["window_start"].strftime("%Y-%m-%dT%H:%M:%S"),
            "window_end": spike["window_end"].strftime("%Y-%m-%dT%H:%M:%S"),
            "detector_type": spike["spike_type"],
            "severity": spike["severity"],
            "anomaly_reasons": _parse_json_field(spike["anomaly_reasons"]),
            "anomaly_score": spike["anomaly_score"],
            "coordination_score": spike["coordination_score"],
        },
        "window": metrics,
        "entities": calculate_entity_counts(window),
        "concentration": calculate_concentration(window),
        "relationships": calculate_relationships(window),
        "velocity": calculate_velocity(window),
        "baseline_comparison": calculate_baseline_comparison(spike, metrics),
        "classifier": _classifier_for_spike(str(spike["spike_id"]), window),
    }
    return json_safe(evidence)


def _classifier_for_spike(spike_id: str, window) -> dict:
    cached = get_cached(SYNTHETIC_WORLD, spike_id)
    if cached is not None:
        record_invocation(SYNTHETIC_WORLD, spike_id, "cache")
        return cached
    adapted = adapt_synthetic(window, world=SYNTHETIC_WORLD)
    scored = score_canonical_frame(
        adapted.frame,
        world=SYNTHETIC_WORLD,
        anomaly_id=spike_id,
        features_used=adapted.features_used,
        features_unavailable=adapted.features_unavailable,
    )
    return classifier_from_scores(
        scored,
        world=SYNTHETIC_WORLD,
        anomaly_id=spike_id,
        source="shared_infer",
        extra={"adapter_notes": adapted.notes},
    )
