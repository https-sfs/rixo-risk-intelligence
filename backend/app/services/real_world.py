"""Read precomputed IEEE-CIS artifacts. Never scans the raw 590k-row ledger."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import app.repo  # noqa: F401
from app.repo import REPO_ROOT
from evaluation.real_data.investigate import investigate_real_anomaly
from evaluation.real_data.mapper import DATASET_NAME, MissingRealDatasetError, WORLD
from models.ieee_fraud import (
    ENCODER_NAME,
    EVALUATION_NAME,
    JOBLIB_NAME,
    MODEL_DIR,
    OVERLAY_NAME,
    PROVENANCE,
)
from evaluation.real_data.governance import (
    approve_action as approve_ieee_action,
    decide_from_investigation,
    get_action as get_ieee_action,
    investigation_state as ieee_investigation_state,
    list_audit as list_ieee_audit,
    propose_action as propose_ieee_action,
    record_decision,
    simulate_action as simulate_ieee_action,
)
from models.ieee_fraud.infer import attach_classifier, classifier_from_hour_overlay
from models.ieee_fraud.overlay import apply_sample_scopes, overlay_for_anomaly
from models.ieee_fraud.predict import (
    IncompleteModelArtifactError,
    load_model,
    predict_transaction,
)

REAL_DATA_DIR = REPO_ROOT / "data" / "real"
ARTIFACT_NAMES = {
    "profile": "profile.json",
    "benchmark": "benchmark.json",
    "anomalies": "anomalies.json",
    "evidence": "evidence.json",
    "evaluation": "evaluation.json",
}


class RealDataUnavailableError(RuntimeError):
    """Derived real-data artifacts are missing."""


class ModelUnavailableError(RuntimeError):
    """IEEE-CIS supervised model artifacts are missing."""


def artifact_path(name: str) -> Path:
    return REAL_DATA_DIR / ARTIFACT_NAMES[name]


def raw_train_present() -> bool:
    return (REAL_DATA_DIR / "train_transaction.csv").is_file()


def _read_json(name: str) -> dict[str, Any]:
    path = artifact_path(name)
    if not path.is_file():
        raise RealDataUnavailableError(
            f"{path.name} is missing. Run "
            r".\backend\.venv\Scripts\python.exe -m evaluation.real_data.preprocess "
            "after placing IEEE-CIS files in data/real/."
        )
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def load_artifact(name: str) -> dict[str, Any]:
    return _read_json(name)


def world_status() -> dict[str, Any]:
    artifacts = {key: artifact_path(key).is_file() for key in ARTIFACT_NAMES}
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "raw_train_present": raw_train_present(),
        "artifacts": artifacts,
        "ready": raw_train_present() and all(artifacts.values()),
        "amount_currency": "USD",
    }


def get_profile() -> dict[str, Any]:
    if not raw_train_present():
        raise MissingRealDatasetError(
            "IEEE-CIS train_transaction.csv was not found under data/real/."
        )
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


def apply_ieee_provenance(payload: dict[str, Any]) -> dict[str, Any]:
    """ProductCD share and detector hour scores are computed, not raw observations."""
    from evaluation.real_data.evidence import DERIVED

    live = payload.get("live_evidence")
    if isinstance(live, dict):
        product = live.get("product_concentration")
        if isinstance(product, dict):
            product["label"] = DERIVED
            product["source"] = "share of train_transaction.csv ProductCD in the hour window"
        temporal = live.get("temporal_anomaly")
        if isinstance(temporal, dict):
            temporal["label"] = DERIVED
            temporal["source"] = "evaluation.real_data.detect live score"
    return payload


def get_evidence(anomaly_id: str) -> dict[str, Any]:
    evidence = load_artifact("evidence")
    if anomaly_id not in evidence:
        raise KeyError(anomaly_id)
    payload = apply_ieee_provenance(copy.deepcopy(evidence[anomaly_id]))
    overlay_path = MODEL_DIR / OVERLAY_NAME
    if overlay_path.is_file():
        overlay = _load_json_file(str(overlay_path.resolve()))
        apply_sample_scopes(overlay, _train_cutoff_elapsed())
        model_block = overlay_for_anomaly(overlay, int(payload["relative_hour_bucket"]))
        if model_block is not None:
            payload["model_prediction"] = model_block
            attach_classifier(
                payload,
                classifier_from_hour_overlay(
                    model_block,
                    world=WORLD,
                    anomaly_id=anomaly_id,
                    source="persisted_overlay",
                ),
            )
    if "classifier" not in payload:
        from models.ieee_fraud.infer import not_scored

        attach_classifier(
            payload,
            not_scored(
                world=WORLD,
                anomaly_id=anomaly_id,
                reason="Required feature(s) unavailable",
                missing_features=["hour overlay"],
            ),
        )
    return payload


def _train_cutoff_elapsed() -> float | None:
    path = MODEL_DIR / EVALUATION_NAME
    if not path.is_file():
        return None
    evaluation = json.loads(path.read_text(encoding="utf-8"))
    split = evaluation.get("split") or {}
    cutoff = split.get("train_cutoff_elapsed_seconds")
    return float(cutoff) if cutoff is not None else None


def get_evaluation() -> dict[str, Any]:
    return load_artifact("evaluation")


def investigate(anomaly_id: str, provider: str = "auto") -> dict[str, Any]:
    get_anomaly(anomaly_id)
    return investigate_real_anomaly(get_evidence(anomaly_id), provider=provider)


def _load_json_file(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def model_status() -> dict[str, Any]:
    artifacts = {
        "joblib": (MODEL_DIR / JOBLIB_NAME).is_file(),
        "encoder": (MODEL_DIR / ENCODER_NAME).is_file(),
        "evaluation": (MODEL_DIR / EVALUATION_NAME).is_file(),
        "overlay": (MODEL_DIR / OVERLAY_NAME).is_file(),
    }
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "provenance": PROVENANCE,
        "artifacts": artifacts,
        "ready": artifacts["evaluation"],
        "predict_ready": artifacts["joblib"],
        "not_an_llm": True,
        "not_january_2026_source_model": True,
    }


def predict_real_transaction(payload: dict[str, Any]) -> dict[str, Any]:
    path = MODEL_DIR / JOBLIB_NAME
    if not path.is_file():
        raise ModelUnavailableError(
            f"{JOBLIB_NAME} is missing. Run "
            r".\backend\.venv\Scripts\python.exe -m models.ieee_fraud.pipeline "
            "after placing IEEE-CIS train files in data/real/."
        )
    try:
        artifact = load_model(path)
    except IncompleteModelArtifactError as exc:
        raise ModelUnavailableError(str(exc)) from exc
    return predict_transaction(artifact, payload)


def get_model_evaluation() -> dict[str, Any]:
    path = MODEL_DIR / EVALUATION_NAME
    if not path.is_file():
        raise ModelUnavailableError(
            f"{EVALUATION_NAME} is missing. Run "
            r".\backend\.venv\Scripts\python.exe -m models.ieee_fraud.pipeline "
            "after placing IEEE-CIS train files in data/real/."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def decide_real_anomaly(anomaly_id: str, provider: str = "auto") -> dict[str, Any]:
    anomaly = get_anomaly(anomaly_id)
    evidence = get_evidence(anomaly_id)
    report = investigate_real_anomaly(evidence, provider=provider)
    decision = decide_from_investigation(anomaly, evidence, report)
    return record_decision(decision)


def propose_real_action(
    anomaly_id: str,
    provider: str = "auto",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    decision = decide_real_anomaly(anomaly_id, provider=provider)
    return propose_ieee_action(decision, idempotency_key=idempotency_key, provider=provider)


def approve_real_action(action_id: str, approved_by: str, note: str | None = None) -> dict[str, Any]:
    return approve_ieee_action(action_id, approved_by=approved_by, note=note)


def simulate_real_action(action_id: str) -> dict[str, Any]:
    return simulate_ieee_action(action_id)


def get_real_action(action_id: str) -> dict[str, Any]:
    return get_ieee_action(action_id)


def get_real_audit(anomaly_id: str | None = None) -> dict[str, Any]:
    return list_ieee_audit(anomaly_id=anomaly_id)


def get_real_investigation_state(anomaly_id: str) -> dict[str, Any]:
    return ieee_investigation_state(anomaly_id)