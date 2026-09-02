from fastapi import APIRouter, Query

from app.services.recent_world import (
    approve_recent_action,
    decide_recent_anomaly,
    get_anomaly,
    get_benchmark,
    get_evaluation,
    get_evidence,
    get_profile,
    get_recent_action,
    get_recent_audit,
    get_recent_investigation_state,
    investigate_anomaly,
    list_anomalies,
    propose_recent_action,
    simulate_recent_action,
    world_status,
)

router = APIRouter(prefix="/api/recent", tags=["recent-public-data"])


@router.get("/status")
def recent_status() -> dict:
    return world_status()


@router.get("/profile")
def recent_profile() -> dict:
    return get_profile()


@router.get("/benchmark")
def recent_benchmark() -> dict:
    return get_benchmark()


@router.get("/anomalies")
def recent_anomalies() -> dict:
    return list_anomalies()


@router.get("/anomalies/{anomaly_id}")
def recent_anomaly(anomaly_id: str) -> dict:
    from agent.investigator import investigate_with_tools
    from evaluation.intelligence_worlds import for_january

    anomaly = get_anomaly(anomaly_id)
    evidence = get_evidence(anomaly_id)
    intelligence = for_january(anomaly, evidence)
    return {
        "anomaly": anomaly,
        "evidence": evidence,
        "investigation_state": get_recent_investigation_state(anomaly_id),
        "investigation_intelligence": intelligence,
        "investigation_agent": investigate_with_tools(intelligence),
    }


@router.get("/anomalies/{anomaly_id}/investigation")
def recent_investigation(anomaly_id: str, provider: str = Query(default="auto")) -> dict:
    return investigate_anomaly(anomaly_id, provider=provider)


@router.get("/evaluation")
def recent_evaluation() -> dict:
    return get_evaluation()


@router.post("/anomalies/{anomaly_id}/decision")
def recent_decision(anomaly_id: str, provider: str = Query(default="auto")) -> dict:
    return decide_recent_anomaly(anomaly_id, provider=provider)


@router.post("/actions/propose")
def recent_propose(payload: dict) -> dict:
    anomaly_id = str(payload.get("anomaly_id") or "").strip()
    if not anomaly_id:
        raise ValueError("anomaly_id is required.")
    return propose_recent_action(anomaly_id, provider=str(payload.get("provider") or "auto"))


@router.post("/actions/{action_id}/approve")
def recent_approve(action_id: str, payload: dict) -> dict:
    approved_by = str(payload.get("approved_by") or "").strip()
    if not approved_by:
        raise ValueError("approved_by is required.")
    return approve_recent_action(action_id, approved_by=approved_by, note=payload.get("note"))


@router.post("/actions/{action_id}/simulate")
def recent_simulate(action_id: str) -> dict:
    return simulate_recent_action(action_id)


@router.get("/actions/{action_id}")
def recent_action(action_id: str) -> dict:
    return get_recent_action(action_id)


@router.get("/audit")
def recent_audit(anomaly_id: str | None = Query(default=None)) -> dict:
    return get_recent_audit(anomaly_id=anomaly_id)
