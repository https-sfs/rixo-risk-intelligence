from fastapi import APIRouter, Query

from app.services.real_world import (
    approve_real_action,
    decide_real_anomaly,
    get_anomaly,
    get_benchmark,
    get_evaluation,
    get_evidence,
    get_model_evaluation,
    get_profile,
    get_real_action,
    get_real_audit,
    get_real_investigation_state,
    investigate,
    list_anomalies,
    model_status,
    predict_real_transaction,
    propose_real_action,
    simulate_real_action,
    world_status,
)

router = APIRouter(prefix="/api/real", tags=["real-public-data"])


@router.get("/status")
def real_status() -> dict:
    return world_status()


@router.get("/profile")
def real_profile() -> dict:
    return get_profile()


@router.get("/benchmark")
def real_benchmark() -> dict:
    return get_benchmark()


@router.get("/anomalies")
def real_anomalies() -> dict:
    return list_anomalies()


@router.get("/anomalies/{anomaly_id}")
def real_anomaly(anomaly_id: str) -> dict:
    from agent.investigator import investigate_with_tools
    from evaluation.intelligence_worlds import for_ieee

    anomaly = get_anomaly(anomaly_id)
    evidence = get_evidence(anomaly_id)
    intelligence = for_ieee(anomaly, evidence)
    return {
        "anomaly": anomaly,
        "evidence": evidence,
        "investigation_state": get_real_investigation_state(anomaly_id),
        "investigation_intelligence": intelligence,
        "investigation_agent": investigate_with_tools(intelligence),
    }


@router.get("/anomalies/{anomaly_id}/investigation")
def real_investigation(
    anomaly_id: str,
    provider: str = Query(default="auto"),
) -> dict:
    return investigate(anomaly_id, provider=provider)


@router.get("/evaluation")
def real_evaluation() -> dict:
    return get_evaluation()


@router.get("/model/status")
def real_model_status() -> dict:
    return model_status()


@router.get("/model/evaluation")
def real_model_evaluation() -> dict:
    return get_model_evaluation()


@router.post("/model/predict")
def real_model_predict(payload: dict) -> dict:
    return predict_real_transaction(payload)


@router.post("/anomalies/{anomaly_id}/decision")
def real_decision(anomaly_id: str, provider: str = Query(default="auto")) -> dict:
    return decide_real_anomaly(anomaly_id, provider=provider)


@router.post("/actions/propose")
def real_propose(payload: dict) -> dict:
    anomaly_id = str(payload.get("anomaly_id") or "").strip()
    if not anomaly_id:
        raise ValueError("anomaly_id is required.")
    key = payload.get("idempotency_key")
    return propose_real_action(
        anomaly_id,
        provider=str(payload.get("provider") or "auto"),
        idempotency_key=str(key).strip() if key is not None and str(key).strip() else None,
    )


@router.post("/actions/{action_id}/approve")
def real_approve(action_id: str, payload: dict) -> dict:
    approved_by = str(payload.get("approved_by") or "").strip()
    if not approved_by:
        raise ValueError("approved_by is required.")
    return approve_real_action(action_id, approved_by=approved_by, note=payload.get("note"))


@router.post("/actions/{action_id}/simulate")
def real_simulate(action_id: str) -> dict:
    return simulate_real_action(action_id)


@router.get("/actions/{action_id}")
def real_action(action_id: str) -> dict:
    return get_real_action(action_id)


@router.get("/audit")
def real_audit(anomaly_id: str | None = Query(default=None)) -> dict:
    return get_real_audit(anomaly_id=anomaly_id)
