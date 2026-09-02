"""Integration checks against the local January 2026 CSV, if present."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evaluation.paths import BASELINE_TRANSACTIONS_PATH, HELDOUT_TRANSACTIONS_PATH
from evaluation.recent_data import RECENT_DATA_DIR
from evaluation.recent_data.mapper import SOURCE_MODEL_OUTPUTS, load_raw, map_collection

REPO = Path(__file__).resolve().parent.parent
CSV = RECENT_DATA_DIR / "fraud_tests_export_20260501_080333.csv"
IEEE_TRAIN = REPO / "data" / "real" / "train_transaction.csv"

requires_recent = pytest.mark.skipif(not CSV.is_file(), reason="January 2026 CSV is not present")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


@requires_recent
def test_actual_schema_and_january_counts() -> None:
    raw = load_raw(RECENT_DATA_DIR)
    assert len(raw) == 57394
    assert len(raw.columns) == 40
    for name in (
        "transaction_id",
        "amount",
        "is_fraud",
        "timestamp",
        "test_date",
        "ip_address",
        *SOURCE_MODEL_OUTPUTS,
    ):
        assert name in raw.columns
    assert "response_time_ms" not in raw.columns
    mapped = map_collection(raw)
    assert len(mapped) == 56962
    assert int((mapped["fraud_label"] == 1).sum()) == 98
    for name in SOURCE_MODEL_OUTPUTS:
        assert name not in mapped.columns
    assert "is_fraud" not in mapped.columns


@requires_recent
def test_recent_api_reads_artifacts_and_leaves_other_worlds() -> None:
    before_seed = _sha256(BASELINE_TRANSACTIONS_PATH)
    before_heldout = _sha256(HELDOUT_TRANSACTIONS_PATH) if HELDOUT_TRANSACTIONS_PATH.is_file() else None
    before_ieee = _sha256(IEEE_TRAIN) if IEEE_TRAIN.is_file() else None

    from app.main import app

    client = TestClient(app)
    status = client.get("/api/recent/status")
    assert status.status_code == 200
    body = status.json()
    assert body["world"] == "RECENT PUBLIC DATA"
    if body["ready"]:
        profile = client.get("/api/recent/profile")
        assert profile.status_code == 200
        assert profile.json()["january_collection"]["rows"] == 56962
        assert profile.json()["january_collection"]["fraud_count"] == 98
        benchmark = client.get("/api/recent/benchmark")
        assert benchmark.status_code == 200
        assert benchmark.json()["measurements"]["labelled_fraud_transactions"]["value"] == 98
        evaluation = client.get("/api/recent/evaluation")
        assert evaluation.status_code == 200
        assert evaluation.json()["methodology"]["source_model_used_as_our_prediction"] is False
        client.get("/api/recent/anomalies")

    ieee = client.get("/api/real/status")
    assert ieee.status_code == 200
    assert ieee.json()["world"] == "REAL PUBLIC DATA"
    spikes = client.get("/api/spikes")
    assert spikes.status_code == 200

    assert _sha256(BASELINE_TRANSACTIONS_PATH) == before_seed
    if before_heldout is not None:
        assert _sha256(HELDOUT_TRANSACTIONS_PATH) == before_heldout
    if before_ieee is not None:
        assert _sha256(IEEE_TRAIN) == before_ieee
