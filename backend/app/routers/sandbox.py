from fastapi import APIRouter

from app.integrations.sandbox_payments import public_status

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])


@router.get("/status")
def sandbox_status() -> dict:
    return public_status()
