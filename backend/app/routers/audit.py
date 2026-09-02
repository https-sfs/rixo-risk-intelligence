from fastapi import APIRouter, Query

from agent.actions.service import default_store
from app.schemas.audit import AuditEventOut, AuditListOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=AuditListOut)
def list_audit(
    spike_id: str | None = Query(default=None),
    action_id: str | None = Query(default=None),
) -> AuditListOut:
    events = [item.to_dict() for item in default_store().audit]
    if spike_id:
        events = [item for item in events if item.get("spike_id") == spike_id]
    if action_id:
        events = [item for item in events if item.get("action_id") == action_id]
    return AuditListOut(
        events=[AuditEventOut.model_validate(item) for item in events],
        count=len(events),
    )
