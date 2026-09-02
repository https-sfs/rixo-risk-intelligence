from fastapi import APIRouter

from evaluation.intelligence import load_heldout_overview, load_investigation_overview
from app.schemas.spikes import SpikeListOut, SpikeOut
from app.services.spikes import get_detected_spike, list_detected_spikes

router = APIRouter(prefix="/api/spikes", tags=["spikes"])


@router.get("", response_model=SpikeListOut)
def list_spikes() -> SpikeListOut:
    spikes = [SpikeOut.model_validate(item) for item in list_detected_spikes()]
    return SpikeListOut(
        spikes=spikes,
        count=len(spikes),
        heldout_detection=load_heldout_overview(),
        heldout_investigation=load_investigation_overview(),
    )


@router.get("/{spike_id}", response_model=SpikeOut)
def get_spike(spike_id: str) -> SpikeOut:
    return SpikeOut.model_validate(get_detected_spike(spike_id))
