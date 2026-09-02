"""In-memory Bring Your Data sessions backed by isolated temp CSV files."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import settings
from evaluation.custom_data import DATASET_NAME, WORLD
from evaluation.custom_data.compatibility import assess_compatibility
from evaluation.custom_data.detect import build_evidence, detect_from_path
from evaluation.custom_data.evaluate import evaluate_label_arrays
from evaluation.custom_data.governance import (
    approve_action as approve_custom_gov,
    decide_from_investigation,
    get_action as get_custom_gov_action,
    investigation_state as custom_investigation_state,
    investigation_summary as custom_investigation_summary,
    list_audit as list_custom_gov_audit,
    propose_action as propose_custom_gov,
    record_decision,
    reset_store as reset_custom_gov,
    simulate_action as simulate_custom_gov,
)
from evaluation.custom_data.inspect import inspect_schema
from evaluation.custom_data.investigate import investigate_custom_anomaly
from evaluation.custom_data.mapping import (
    high_confidence_mapping,
    mapping_readiness,
    propose_mappings,
    summarize_proposals,
    validate_mapping,
)
from evaluation.custom_data.schema import CustomDataError, CustomSessionError, field_catalog
from evaluation.custom_data.score import (
    CustomModelUnavailableError,
    classifier_for_custom_hour,
    hour_model_overlay,
    score_adapted_path,
    score_compatible_path,
)
from evaluation.custom_data.stream import MAX_FIELD_BYTES, new_upload_path, unlink_quietly

MAX_SESSIONS = 8


def max_upload_bytes() -> int:
    return int(settings.custom_max_upload_mb) * 1024 * 1024


def max_row_limit() -> int:
    return int(settings.custom_max_rows)


def format_bytes(size: int) -> str:
    if size >= 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024 * 1024):.2f} GB ({size:,} bytes)"
    return f"{size / (1024 * 1024):.1f} MB ({size:,} bytes)"


def safe_filename(filename: str) -> str:
    name = Path(filename).name.strip() or "upload.csv"
    if not name.lower().endswith(".csv"):
        raise CustomDataError("Upload a CSV file. Only .csv extensions are accepted.")
    return name


def assert_size_within_limit(size: int) -> None:
    ceiling = max_upload_bytes()
    if size > ceiling:
        raise CustomDataError(
            f"Upload rejected: file is {format_bytes(size)}. "
            f"The size limit is {format_bytes(ceiling)}."
        )


def assert_rows_within_limit(rows: int) -> None:
    ceiling = max_row_limit()
    if rows > ceiling:
        raise CustomDataError(f"Upload rejected: CSV contains more than {ceiling:,} rows.")


@dataclass
class CustomSession:
    session_id: str
    filename: str
    csv_path: str
    file_bytes: int
    columns: list[str]
    inspection: dict[str, Any]
    mapping_proposals: list[dict[str, Any]]
    mapping: dict[str, str] | None = None
    compatibility: dict[str, Any] | None = None
    anomalies: list[dict[str, Any]] = field(default_factory=list)
    label_hours: dict[str, dict[str, Any]] = field(default_factory=dict)
    summary: dict[str, Any] | None = None
    evaluation: dict[str, Any] | None = None
    scored: dict[str, Any] | None = None
    hourly: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )


_SESSIONS: dict[str, CustomSession] = {}


def _release_session(session: CustomSession) -> None:
    unlink_quietly(session.csv_path)


def reset_sessions() -> None:
    for session in list(_SESSIONS.values()):
        _release_session(session)
    _SESSIONS.clear()
    reset_custom_gov()


def _evict_if_needed() -> None:
    while len(_SESSIONS) >= MAX_SESSIONS:
        oldest = min(_SESSIONS.values(), key=lambda item: item.created_at)
        _SESSIONS.pop(oldest.session_id, None)
        _release_session(oldest)
        reset_custom_gov(oldest.session_id)


def get_session(session_id: str) -> CustomSession:
    session = _SESSIONS.get(session_id)
    if session is None:
        raise CustomSessionError(
            "This Bring Your Data session is unknown or expired. Upload the CSV again. "
            "Uploads stay in an isolated temporary file and are not written to the benchmark datasets."
        )
    return session


def world_status() -> dict[str, Any]:
    ceiling = max_upload_bytes()
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "active_sessions": len(_SESSIONS),
        "storage": "isolated_temp_file",
        "mixed_with_benchmarks": False,
        "cloud_storage": False,
        "catalog": field_catalog(),
        "upload_limits": {
            "max_bytes": ceiling,
            "max_mb": ceiling / (1024 * 1024),
            "max_rows": max_row_limit(),
            "max_field_bytes": MAX_FIELD_BYTES,
        },
    }


def create_session_from_path(filename: str, path: str, size: int) -> dict[str, Any]:
    safe = safe_filename(filename)
    assert_size_within_limit(size)
    try:
        inspection = inspect_schema(path, safe)
    except Exception:
        unlink_quietly(path)
        raise
    inspection["file_bytes"] = size
    _evict_if_needed()
    session_id = f"cxs-{uuid4().hex[:12]}"
    columns = list(inspection.get("columns") or [])
    session = CustomSession(
        session_id=session_id,
        filename=safe,
        csv_path=path,
        file_bytes=size,
        columns=columns,
        inspection=inspection,
        mapping_proposals=propose_mappings(columns),
    )
    _SESSIONS[session_id] = session
    return session_payload(session)


def create_session(filename: str, content: bytes) -> dict[str, Any]:
    """Small-payload helper. Production uploads must stream via ingest_upload_stream."""
    assert_size_within_limit(len(content))
    target = new_upload_path()
    target.write_bytes(content)
    return create_session_from_path(filename, str(target), len(content))


async def ingest_upload_stream(filename: str, chunks: AsyncIterator[bytes]) -> dict[str, Any]:
    safe = safe_filename(filename)
    target = new_upload_path()
    size = 0
    try:
        with target.open("wb") as handle:
            async for chunk in chunks:
                if not chunk:
                    continue
                size += len(chunk)
                assert_size_within_limit(size)
                handle.write(chunk)
        if size == 0:
            raise CustomDataError("The upload body is empty.")
        return create_session_from_path(safe, str(target), size)
    except Exception:
        unlink_quietly(target)
        raise


def session_payload(session: CustomSession) -> dict[str, Any]:
    scored_public = None
    if session.scored:
        scored_public = {
            key: value
            for key, value in session.scored.items()
            if key not in {"scores", "score_array", "label_array", "hours"}
        }
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "session_id": session.session_id,
        "filename": session.filename,
        "created_at": session.created_at,
        "file_bytes": session.file_bytes,
        "inspection": session.inspection,
        "mapping_proposals": session.mapping_proposals,
        "mapping": session.mapping,
        "mapping_summary": summarize_proposals(session.mapping_proposals),
        "mapping_validation": mapping_readiness(
            session.mapping or high_confidence_mapping(session.mapping_proposals)
        ),
        "compatibility": session.compatibility,
        "anomalies": _anomalies_with_investigation(session),
        "summary": session.summary,
        "evaluation": session.evaluation,
        "model_overlay": scored_public,
        "privacy": {
            "analyzed_as_custom_dataset": True,
            "mixed_with_existing_datasets": False,
            "modifies_benchmark_datasets": False,
            "labels_invented": False,
            "production_payment_action": False,
            "storage": "isolated_temp_file",
        },
    }


def confirm_mapping(session_id: str, mapping: dict[str, Any]) -> dict[str, Any]:
    session = get_session(session_id)
    confirmed = validate_mapping(session.columns, mapping)
    session.mapping = confirmed
    session.compatibility = assess_compatibility(session.columns, confirmed)
    session.anomalies = []
    session.summary = None
    session.evaluation = None
    session.scored = None
    session.label_hours = {}
    session.hourly = []
    return session_payload(session)


def analyze_session(session_id: str) -> dict[str, Any]:
    session = get_session(session_id)
    if session.mapping is None or session.compatibility is None:
        raise CustomDataError("Confirm field mapping before analysis.")
    readiness = mapping_readiness(session.mapping)
    if not readiness["ready"]:
        raise CustomDataError(readiness["reason"] or "Required fields are not mapped.")
    if not session.compatibility.get("anomaly_ready") and session.compatibility.get("status") == "incompatible":
        raise CustomDataError(
            "This dataset is incompatible for both IEEE scoring and anomaly investigation. "
            "Map amount and a timestamp, or upload a richer CSV."
        )
    anomalies, summary, label_hours = detect_from_path(
        session.csv_path,
        session.mapping,
        max_rows=max_row_limit(),
    )
    session.inspection = {
        **session.inspection,
        "rows": summary.get("transactions_analyzed"),
        "schema_only": False,
        "inspected_in_chunks": True,
    }
    session.anomalies = anomalies
    session.label_hours = label_hours
    session.hourly = list(summary.get("hourly_context") or [])
    session.scored = None
    if session.compatibility.get("may_score_classifier") or session.compatibility.get("may_use_ieee_model"):
        try:
            if session.compatibility.get("may_use_ieee_model"):
                session.scored = score_compatible_path(
                    session.csv_path,
                    session.columns,
                    label_column=session.mapping.get("fraud_label"),
                )
            else:
                session.scored = score_adapted_path(
                    session.csv_path,
                    session.columns,
                    mapping=session.mapping,
                    label_column=session.mapping.get("fraud_label"),
                )
        except CustomModelUnavailableError as exc:
            session.scored = {
                "world": WORLD,
                "scored": False,
                "reason": str(exc),
                "features_fabricated": False,
            }
        except CustomDataError as exc:
            session.scored = {
                "world": WORLD,
                "scored": False,
                "reason": str(exc),
                "features_fabricated": False,
            }
    if session.scored and session.scored.get("score_array") is not None:
        session.evaluation = evaluate_label_arrays(
            session.scored.get("label_array"),
            session.scored.get("score_array"),
            session.scored.get("threshold"),
        )
    elif session.mapping.get("fraud_label"):
        session.evaluation = evaluate_label_arrays(None, None, None)
        session.evaluation = {
            "world": WORLD,
            "available": True,
            "provenance": "USER-PROVIDED GROUND TRUTH",
            "classifier_metrics_calculated": False,
            "labels_invented": False,
            "used_as_detector_input": False,
            "retrained_on_upload": False,
            "reason": (
                "User-provided labels are evaluation-only. "
                "Classifier metrics require a scored classifier output."
            ),
        }
        if label_hours:
            fraud_count = sum(int(item.get("fraud_count") or 0) for item in label_hours.values())
            session.evaluation["fraud_count"] = fraud_count
    else:
        session.evaluation = evaluate_label_arrays(None, None, None)
    session.summary = {
        **summary,
        "model_compatibility": session.compatibility.get("headline"),
        "model_status": session.compatibility.get("status"),
        "supervised_scores": bool(session.scored and session.scored.get("scored_rows")),
        "chunked": True,
    }
    return session_payload(session)


def _anomalies_with_investigation(session: CustomSession) -> list[dict[str, Any]]:
    return [
        {
            **item,
            "investigation": custom_investigation_summary(
                session.session_id, str(item.get("anomaly_id") or "")
            ),
        }
        for item in session.anomalies
    ]


def list_anomalies(session_id: str) -> dict[str, Any]:
    session = get_session(session_id)
    return {
        "world": WORLD,
        "session_id": session_id,
        "count": len(session.anomalies),
        "summary": session.summary,
        "compatibility": session.compatibility,
        "anomalies": _anomalies_with_investigation(session),
    }


def get_anomaly(session_id: str, anomaly_id: str) -> dict[str, Any]:
    session = get_session(session_id)
    for item in session.anomalies:
        if item.get("anomaly_id") == anomaly_id:
            hour = str(item.get("hour_start") or "")
            evidence = build_evidence(item, label_overlay=session.label_hours.get(hour))
            evidence["classifier"] = classifier_for_custom_hour(session.scored, hour, anomaly_id)
            if session.scored:
                overlay = hour_model_overlay(None, session.scored, hour)
                if overlay:
                    evidence["model_prediction"] = overlay
                    evidence["ieee_model_used"] = bool(session.compatibility and session.compatibility.get("may_use_ieee_model"))
            from agent.investigator import investigate_with_tools
            from evaluation.intelligence_worlds import for_custom

            intelligence = for_custom(
                item,
                evidence,
                hourly=session.hourly,
                mapped_roles=list((session.mapping or {}).keys()),
            )
            return {
                "anomaly": item,
                "evidence": evidence,
                "session_id": session_id,
                "investigation_state": custom_investigation_state(session_id, anomaly_id),
                "investigation_intelligence": intelligence,
                "investigation_agent": investigate_with_tools(intelligence),
            }
    raise KeyError(anomaly_id)


def investigate_anomaly(session_id: str, anomaly_id: str, provider: str = "auto") -> dict[str, Any]:
    detail = get_anomaly(session_id, anomaly_id)
    return investigate_custom_anomaly(detail["evidence"], provider=provider)


def decide_custom_anomaly(session_id: str, anomaly_id: str, provider: str = "auto") -> dict[str, Any]:
    detail = get_anomaly(session_id, anomaly_id)
    report = investigate_custom_anomaly(detail["evidence"], provider=provider)
    decision = decide_from_investigation(detail["anomaly"], detail["evidence"], report)
    return record_decision(session_id, decision)


def propose_custom_action(session_id: str, anomaly_id: str, provider: str = "auto") -> dict[str, Any]:
    decision = decide_custom_anomaly(session_id, anomaly_id, provider=provider)
    return propose_custom_gov(session_id, decision)


def approve_custom_action(
    session_id: str,
    action_id: str,
    approved_by: str,
    note: str | None = None,
) -> dict[str, Any]:
    return approve_custom_gov(session_id, action_id, approved_by=approved_by, note=note)


def simulate_custom_action(session_id: str, action_id: str) -> dict[str, Any]:
    return simulate_custom_gov(session_id, action_id)


def get_custom_action(session_id: str, action_id: str) -> dict[str, Any]:
    return get_custom_gov_action(session_id, action_id)


def get_custom_audit(session_id: str, anomaly_id: str | None = None) -> dict[str, Any]:
    return list_custom_gov_audit(session_id, anomaly_id=anomaly_id)
