"""Map domain failures to HTTP errors. Never fabricate investigation output."""

from __future__ import annotations

import app.repo  # noqa: F401

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent.actions.errors import ActionError
from agent.errors import LLMProviderError
from app.services.real_world import ModelUnavailableError, RealDataUnavailableError
from app.services.recent_world import RecentDataUnavailableError
from evaluation.custom_data.governance import CustomGovernanceError
from evaluation.custom_data.schema import CustomDataError, CustomSessionError
from evaluation.real_data.governance import RealGovernanceError
from evaluation.real_data.mapper import MissingRealDatasetError, RealDataError
from evaluation.recent_data.governance import RecentGovernanceError
from evaluation.recent_data.mapper import MissingRecentDatasetError, RecentDataError
from models.ieee_fraud.predict import IncompletePredictPayloadError


def _action_status(exc: ActionError) -> int:
    message = str(exc).lower()
    if "unknown action" in message:
        return 404
    if "not been explicitly approved" in message or "cannot change" in message:
        return 409
    return 400


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(KeyError)
    def unknown_spike(_request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc).strip("'")})

    @app.exception_handler(ActionError)
    def action_rejected(_request: Request, exc: ActionError) -> JSONResponse:
        return JSONResponse(status_code=_action_status(exc), content={"detail": str(exc)})

    @app.exception_handler(LLMProviderError)
    def llm_failed(_request: Request, exc: LLMProviderError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "detail": str(exc),
                "provider": "llm",
                "fail_closed": True,
            },
        )

    @app.exception_handler(IncompletePredictPayloadError)
    def incomplete_predict(_request: Request, exc: IncompletePredictPayloadError) -> JSONResponse:
        return JSONResponse(status_code=400, content=exc.to_dict())

    @app.exception_handler(RealGovernanceError)
    def ieee_governance_failed(_request: Request, exc: RealGovernanceError) -> JSONResponse:
        message = str(exc).lower()
        if "unknown" in message:
            status = 404
        elif "not been explicitly approved" in message or "idempotency-key conflict" in message:
            status = 409
        else:
            status = 400
        return JSONResponse(
            status_code=status,
            content={"detail": str(exc), "world": "REAL PUBLIC DATA", "simulation_only": True},
        )

    @app.exception_handler(ValueError)
    def bad_request(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(MissingRealDatasetError)
    def missing_real(_request: Request, exc: MissingRealDatasetError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc), "world": "REAL PUBLIC DATA"})

    @app.exception_handler(RealDataUnavailableError)
    def real_artifacts_missing(_request: Request, exc: RealDataUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc), "world": "REAL PUBLIC DATA"})

    @app.exception_handler(ModelUnavailableError)
    def model_artifacts_missing(_request: Request, exc: ModelUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": str(exc), "world": "REAL PUBLIC DATA", "provenance": "MODEL PREDICTION"},
        )

    @app.exception_handler(RealDataError)
    def real_data_failed(_request: Request, exc: RealDataError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc), "world": "REAL PUBLIC DATA"})

    @app.exception_handler(MissingRecentDatasetError)
    def missing_recent(_request: Request, exc: MissingRecentDatasetError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc), "world": "RECENT PUBLIC DATA"})

    @app.exception_handler(RecentDataUnavailableError)
    def recent_artifacts_missing(_request: Request, exc: RecentDataUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc), "world": "RECENT PUBLIC DATA"})

    @app.exception_handler(RecentDataError)
    def recent_data_failed(_request: Request, exc: RecentDataError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc), "world": "RECENT PUBLIC DATA"})

    @app.exception_handler(RecentGovernanceError)
    def recent_governance_failed(_request: Request, exc: RecentGovernanceError) -> JSONResponse:
        message = str(exc).lower()
        status = 404 if "unknown" in message else 409 if "not been explicitly approved" in message else 400
        return JSONResponse(
            status_code=status,
            content={"detail": str(exc), "world": "RECENT PUBLIC DATA", "simulation_only": True},
        )

    @app.exception_handler(CustomSessionError)
    def custom_session_missing(_request: Request, exc: CustomSessionError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc), "world": "BRING YOUR DATA", "storage": "local_memory_session"},
        )

    @app.exception_handler(CustomDataError)
    def custom_data_failed(_request: Request, exc: CustomDataError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc), "world": "BRING YOUR DATA"})

    @app.exception_handler(CustomGovernanceError)
    def custom_governance_failed(_request: Request, exc: CustomGovernanceError) -> JSONResponse:
        message = str(exc).lower()
        status = 404 if "unknown" in message else 409 if "not been explicitly approved" in message else 400
        return JSONResponse(
            status_code=status,
            content={"detail": str(exc), "world": "BRING YOUR DATA", "simulation_only": True},
        )
