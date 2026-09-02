from fastapi import APIRouter

from app.schemas.evaluation import CounterfactualIn
from evaluation.counterfactual import evaluate_synthetic_counterfactual, ieee_intervention_limitation
from evaluation.intelligence import SYNTHETIC_WORLD
from evaluation.scorecard import synthetic_scorecard

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.get("/synthetic")
def get_synthetic_scorecard() -> dict:
    return synthetic_scorecard()


@router.post("/synthetic/counterfactual")
def post_synthetic_counterfactual(body: CounterfactualIn) -> dict:
    return evaluate_synthetic_counterfactual(
        spike_id=body.spike_id,
        action_type=body.action_type,
        scope=body.scope,
        world=body.world or SYNTHETIC_WORLD,
    )


@router.get("/ieee/intervention-outcome")
def get_ieee_intervention_outcome() -> dict:
    return ieee_intervention_limitation()
