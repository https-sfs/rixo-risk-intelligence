from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.repo  # noqa: F401 — put repo root on sys.path
from app.config import GOVERNANCE_TICKET_HEADER, resolve_governance_sqlite_path, settings
from app.errors import register_exception_handlers
from app.governance_ticket import GovernanceTicketMiddleware
from app.persistence import attach_default_stores
from app.routers import actions, audit, custom, evaluation, health, investigations, real, recent, sandbox, spikes

app = FastAPI(
    title=settings.app_name,
    description="Merchant-facing fraud risk operations API.",
    version="0.1.0",
)

app.add_middleware(GovernanceTicketMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[GOVERNANCE_TICKET_HEADER],
)

register_exception_handlers(app)
attach_default_stores(resolve_governance_sqlite_path(settings.governance_sqlite_path))
app.include_router(health.router)
app.include_router(spikes.router)
app.include_router(evaluation.router)
app.include_router(investigations.router)
app.include_router(actions.router)
app.include_router(audit.router)
app.include_router(real.router)
app.include_router(recent.router)
app.include_router(custom.router)
app.include_router(sandbox.router)
