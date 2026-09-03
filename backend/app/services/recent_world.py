"""Read precomputed January 2026 artifacts. Never rescans the raw export."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import app.repo  # noqa: F401
from app.repo import resolve_data_subdir
from evaluation.recent_data.governance import (
    approve_action as approve_recent_gov,
    decide_from_investigation,
    get_action as get_recent_gov_action,
    investigation_state as recent_investigation_state,
    list_audit as list_recent_gov_audit,
    propose_action as propose_recent_gov,
    record_decision,
    simulate_action as simulate_recent_gov,
)
from evaluation.recent_data.classifier import classifier_for_recent_anomaly
from evaluation.recent_data.investigate import investigate_recent_anomaly
from evaluation.recent_data.mapper import (
    AMOUNT_CURRENCY,
    DATASET_NAME,
    RAW_CSV_FILENAME,
    WORLD,
)

RECENT_DATA_DIR = resolve_data_subdir("real_2026", marker="benchmark.json")
ARTIFACT_NAMES = {
    "profile": "profile.json",
    "benchmark": "benchmark.json",
    "anomalies": "anomalies.json",
    "evidence": "evidence.json",
    "evaluation": "evaluation.json",
}


class RecentDataUnavailableError(RuntimeError):
    """Derived recent-data artifacts are missing."""


def artifact_path(name: str) -> Path:
    return RECENT_DATA_DIR / ARTIFACT_NAMES[name]


def raw_csv_present() -> bool:
    dest = RECENT_DATA_DIR
    named = dest / RAW_CSV_FILENAME
    if named.is_file():
        return True
    return any(dest.glob("*.csv"))


@lru_cache(maxsize=16)
def _load_json_file(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_artifact(name: str) -> dict[str, Any]:
    path = artifact_path(name)
    if not path.is_file():
        raise RecentDataUnavailableError(
            f"{path.name} is missing. Derived January 2026 artifacts were not found at {path}. "
            "Run `python -m evaluation.recent_data.preprocess` after placing the CSV in data/real_2026/."
        )
    return _load_json_file(str(path.resolve()))


def world_status() -> dict[str, Any]:
    artifacts = {key: artifact_path(key).is_file() for key in ARTIFACT_NAMES}
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "raw_csv_present": raw_csv_present(),
        "artifacts": artifacts,
        "ready": all(artifacts.values()),
        "amount_currency": AMOUNT_CURRENCY,
    }


def get_profile() -> dict[str, Any]:
    return load_artifact("profile")


def get_benchmark() -> dict[str, Any]:
    return load_artifact("benchmark")


def list_anomalies() -> dict[str, Any]:
    return load_artifact("anomalies")


def get_anomaly(anomaly_id: str) -> dict[str, Any]:
    payload = list_anomalies()
    for item in payload.get("anomalies", []):
        if item.get("anomaly_id") == anomaly_id:
            return item
    raise KeyError(anomaly_id)


def apply_january_provenance(payload: dict[str, Any]) -> dict[str, Any]:
    """Hour-floor windows are derived from timestamps, not observed source fields."""
    live = payload.get("live_evidence")
    if isinstance(live, dict):
        window = live.get("temporal_window")
        if isinstance(window, dict):
            window["label"] = "DERIVED"
            window["source"] = "floor(timestamp to hour)"
    return payload


def get_evidence(anomaly_id: str) -> dict[str, Any]:
    evidence = load_artifact("evidence")
    if anomaly_id not in evidence:
        raise KeyError(anomaly_id)
    payload = apply_january_provenance(copy.deepcopy(evidence[anomaly_id]))
    payload["classifier"] = classifier_for_recent_anomaly(anomaly_id, payload)
    return payload


def get_evaluation() -> dict[str, Any]:
    return load_artifact("evaluation")


def investigate_anomaly(anomaly_id: str, provider: str = "auto") -> dict[str, Any]:
    anomaly = get_anomaly(anomaly_id)
    evidence = {**get_evidence(anomaly_id), "signals": anomaly.get("signals") or []}
    return investigate_recent_anomaly(evidence, provider=provider)


def decide_recent_anomaly(anomaly_id: str, provider: str = "auto") -> dict[str, Any]:
    anomaly = get_anomaly(anomaly_id)
    evidence = get_evidence(anomaly_id)
    report = investigate_recent_anomaly(evidence, provider=provider)
    decision = decide_from_investigation(anomaly, evidence, report)
    return record_decision(decision)


def propose_recent_action(anomaly_id: str, provider: str = "auto") -> dict[str, Any]:
    decision = decide_recent_anomaly(anomaly_id, provider=provider)
    return propose_recent_gov(decision)


def approve_recent_action(action_id: str, approved_by: str, note: str | None = None) -> dict[str, Any]:
    return approve_recent_gov(action_id, approved_by=approved_by, note=note)


def simulate_recent_action(action_id: str) -> dict[str, Any]:
    return simulate_recent_gov(action_id)


def get_recent_action(action_id: str) -> dict[str, Any]:
    return get_recent_gov_action(action_id)


def get_recent_audit(anomaly_id: str | None = None) -> dict[str, Any]:
    return list_recent_gov_audit(anomaly_id=anomaly_id)


def get_recent_investigation_state(anomaly_id: str) -> dict[str, Any]:
    return recent_investigation_state(anomaly_id)
