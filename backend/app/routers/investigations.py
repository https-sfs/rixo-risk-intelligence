from fastapi import APIRouter, Query

from agent.actions.service import investigation_state
from agent.investigate import investigate_spike, resolve_provider
from app.schemas.investigations import InvestigationOut, ProviderName
from app.services.spikes import get_detected_spike

router = APIRouter(prefix="/api/spikes", tags=["investigations"])


@router.get("/{spike_id}/investigation", response_model=InvestigationOut)
def investigate(
    spike_id: str,
    provider: ProviderName = Query(default="deterministic"),
) -> InvestigationOut:
    get_detected_spike(spike_id)
    result = investigate_spike(spike_id, provider=resolve_provider(provider))
    result["investigation_state"] = investigation_state(spike_id)
    return InvestigationOut.model_validate(result)
