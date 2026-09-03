"""Committed derived artifacts are enough to serve IEEE-CIS and January 2026."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parent.parent
REAL_DIR = REPO / "data" / "real"
RECENT_DIR = REPO / "data" / "real_2026"


def test_committed_ieee_artifacts_exist_without_raw_ledger() -> None:
    assert (REAL_DIR / "anomalies.json").is_file()
    assert (REAL_DIR / "profile.json").is_file()
    assert (REAL_DIR / "benchmark.json").is_file()
    assert (REAL_DIR / "evidence.json").is_file()
    assert (REAL_DIR / "evaluation.json").is_file()


def test_committed_january_artifacts_exist() -> None:
    assert (RECENT_DIR / "anomalies.json").is_file()
    assert (RECENT_DIR / "benchmark.json").is_file()
    assert (RECENT_DIR / "evaluation.json").is_file()
    assert (RECENT_DIR / "profile.json").is_file()


def test_ieee_api_serves_artifacts_without_raw_train(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.services import real_world

    monkeypatch.setattr(real_world, "raw_train_present", lambda: False)
    real_world.load_artifact.cache_clear()
    client = TestClient(app)
    status = client.get("/api/real/status")
    assert status.status_code == 200
    body = status.json()
    assert body["ready"] is True
    assert body["raw_train_present"] is False
    assert body["artifacts"]["anomalies"] is True
    profile = client.get("/api/real/profile")
    assert profile.status_code == 200
    assert profile.json()["world"] == "REAL PUBLIC DATA"
    anomalies = client.get("/api/real/anomalies")
    assert anomalies.status_code == 200
    assert anomalies.json()["anomalies"]


def test_january_api_serves_artifacts_without_raw_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.main import app
    from app.services import recent_world

    monkeypatch.setattr(recent_world, "raw_csv_present", lambda: False)
    recent_world._load_json_file.cache_clear()
    client = TestClient(app)
    status = client.get("/api/recent/status")
    assert status.status_code == 200
    body = status.json()
    assert body["ready"] is True
    assert body["raw_csv_present"] is False
    benchmark = client.get("/api/recent/benchmark")
    assert benchmark.status_code == 200
    assert benchmark.json()["world"] == "RECENT PUBLIC DATA"
    evaluation = client.get("/api/recent/evaluation")
    assert evaluation.status_code == 200
    anomalies = client.get("/api/recent/anomalies")
    assert anomalies.status_code == 200
    assert anomalies.json()["anomalies"]
