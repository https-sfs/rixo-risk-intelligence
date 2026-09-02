from fastapi import APIRouter

router = APIRouter(tags=["health"])


def _payload() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "fraud-spike-investigator",
        "component": "backend",
    }


@router.get("/health")
def health_check() -> dict[str, str]:
    return _payload()


@router.get("/api/health")
def api_health_check() -> dict[str, str]:
    return _payload()
