from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)
PRODUCTION_FRONTEND = "https://rixo-risk-intelligence.vercel.app"
LEGACY_FRONTEND = "https://rixo-risk-intelligence-frontend.vercel.app"


def test_health_check_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "fraud-spike-investigator",
        "component": "backend",
    }


def test_cors_allows_production_frontend_origin() -> None:
    assert PRODUCTION_FRONTEND in settings.cors_origin_list
    response = client.get("/api/health", headers={"Origin": PRODUCTION_FRONTEND})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == PRODUCTION_FRONTEND


def test_cors_allows_legacy_frontend_origin() -> None:
    assert LEGACY_FRONTEND in settings.cors_origin_list
    response = client.get("/api/health", headers={"Origin": LEGACY_FRONTEND})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == LEGACY_FRONTEND


def test_cors_exposes_governance_ticket_header() -> None:
    report = client.get("/api/spikes/spk-coord-20260118-02/investigation").json()["report"]
    response = client.post(
        "/api/actions/propose",
        json=report,
        headers={"Origin": PRODUCTION_FRONTEND},
    )
    assert response.status_code == 200
    exposed = (response.headers.get("access-control-expose-headers") or "").lower()
    assert "x-governance-ticket" in exposed
    assert response.headers.get("x-governance-ticket")
