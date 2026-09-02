from fastapi import APIRouter, Query, Request

from app.services.custom_world import (
    analyze_session,
    approve_custom_action,
    assert_size_within_limit,
    confirm_mapping,
    decide_custom_anomaly,
    get_anomaly,
    get_custom_action,
    get_custom_audit,
    get_session,
    ingest_upload_stream,
    investigate_anomaly,
    list_anomalies,
    propose_custom_action,
    session_payload,
    simulate_custom_action,
    world_status,
)

router = APIRouter(prefix="/api/custom", tags=["bring-your-data"])


@router.get("/status")
def custom_status() -> dict:
    return world_status()


@router.post("/upload")
async def custom_upload(request: Request) -> dict:
    filename = request.headers.get("x-filename") or "upload.csv"
    announced = request.headers.get("content-length")
    if announced:
        try:
            announced_size = int(announced)
        except ValueError:
            announced_size = None
        if announced_size is not None:
            assert_size_within_limit(announced_size)
    return await ingest_upload_stream(filename, request.stream())


@router.get("/sessions/{session_id}")
def custom_session(session_id: str) -> dict:
    return session_payload(get_session(session_id))


@router.post("/sessions/{session_id}/mapping")
def custom_mapping(session_id: str, payload: dict) -> dict:
    mapping = payload.get("mapping")
    if not isinstance(mapping, dict):
        raise ValueError("mapping must be an object of canonical field → column name.")
    return confirm_mapping(session_id, mapping)


@router.post("/sessions/{session_id}/analyze")
def custom_analyze(session_id: str) -> dict:
    return analyze_session(session_id)


@router.get("/sessions/{session_id}/anomalies")
def custom_anomalies(session_id: str) -> dict:
    return list_anomalies(session_id)


@router.get("/sessions/{session_id}/anomalies/{anomaly_id}")
def custom_anomaly(session_id: str, anomaly_id: str) -> dict:
    return get_anomaly(session_id, anomaly_id)


@router.get("/sessions/{session_id}/anomalies/{anomaly_id}/investigation")
def custom_investigation(
    session_id: str,
    anomaly_id: str,
    provider: str = Query(default="auto"),
) -> dict:
    return investigate_anomaly(session_id, anomaly_id, provider=provider)


@router.post("/sessions/{session_id}/anomalies/{anomaly_id}/decision")
def custom_decision(
    session_id: str,
    anomaly_id: str,
    provider: str = Query(default="auto"),
) -> dict:
    return decide_custom_anomaly(session_id, anomaly_id, provider=provider)


@router.post("/sessions/{session_id}/actions/propose")
def custom_propose(session_id: str, payload: dict) -> dict:
    anomaly_id = str(payload.get("anomaly_id") or "").strip()
    if not anomaly_id:
        raise ValueError("anomaly_id is required.")
    return propose_custom_action(session_id, anomaly_id, provider=str(payload.get("provider") or "auto"))


@router.post("/sessions/{session_id}/actions/{action_id}/approve")
def custom_approve(session_id: str, action_id: str, payload: dict) -> dict:
    approved_by = str(payload.get("approved_by") or "").strip()
    if not approved_by:
        raise ValueError("approved_by is required.")
    return approve_custom_action(session_id, action_id, approved_by=approved_by, note=payload.get("note"))


@router.post("/sessions/{session_id}/actions/{action_id}/simulate")
def custom_simulate(session_id: str, action_id: str) -> dict:
    return simulate_custom_action(session_id, action_id)


@router.get("/sessions/{session_id}/actions/{action_id}")
def custom_action(session_id: str, action_id: str) -> dict:
    return get_custom_action(session_id, action_id)


@router.get("/sessions/{session_id}/audit")
def custom_audit(session_id: str, anomaly_id: str | None = Query(default=None)) -> dict:
    return get_custom_audit(session_id, anomaly_id=anomaly_id)
