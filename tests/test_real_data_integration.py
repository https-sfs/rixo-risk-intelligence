from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from evaluation.paths import (
    BASELINE_SPIKES_CSV_PATH,
    BASELINE_SPIKES_JSON_PATH,
    BASELINE_TRANSACTIONS_PATH,
    BASELINE_WINDOWS_PATH,
    HELDOUT_META_PATH,
    HELDOUT_TRANSACTIONS_PATH,
)
from evaluation.real_data.detect import detect_anomalies, score_hourly
from evaluation.real_data.mapper import (
    AMOUNT_CURRENCY,
    discover_files,
    map_transactions,
    read_csv_header,
    validate_required_columns,
)
from evaluation.real_data.profile import SAMPLE_SUBMISSION_NOTE
from tools.paths import TRANSACTIONS_PATH

REPO = Path(__file__).resolve().parent.parent
REAL_DIR = REPO / "data" / "real"
TRAIN = REAL_DIR / "train_transaction.csv"
PROFILE = REAL_DIR / "profile.json"
BENCHMARK = REAL_DIR / "benchmark.json"
HOURLY = REAL_DIR / "hourly_metrics.csv"
ANOMALIES = REAL_DIR / "anomalies.json"
EVALUATION = REAL_DIR / "evaluation.json"

LOCKED = (
    BASELINE_TRANSACTIONS_PATH,
    BASELINE_SPIKES_CSV_PATH,
    BASELINE_SPIKES_JSON_PATH,
    BASELINE_WINDOWS_PATH,
    BASELINE_TRANSACTIONS_PATH.parent / "dataset_meta.json",
    HELDOUT_TRANSACTIONS_PATH,
    HELDOUT_META_PATH,
)

requires_real = pytest.mark.skipif(not TRAIN.is_file(), reason="IEEE-CIS train file is not present")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


@requires_real
def test_actual_file_discovery() -> None:
    files = discover_files(REAL_DIR)
    assert files["train_transaction.csv"] is not None
    assert files["train_identity.csv"] is not None
    assert files["test_transaction.csv"] is not None
    assert files["sample_submission.csv"] is not None


@requires_real
def test_schema_validation_on_actual_headers() -> None:
    header = read_csv_header(TRAIN)
    assert "TransactionID" in header
    assert "TransactionAmt" in header
    assert "isFraud" in header
    assert "TransactionDT" in header
    assert "ProductCD" in header
    assert "ip_address" not in header
    assert "sku_id" not in header
    test_header = read_csv_header(REAL_DIR / "test_transaction.csv")
    assert "isFraud" not in test_header
    sample = pd.read_csv(REAL_DIR / "sample_submission.csv", nrows=3)
    assert set(sample["isFraud"].unique()) == {0.5}


@requires_real
def test_row_counts_match_generated_profile() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    assert profile["files"]["train_transaction.csv"]["rows"] == 590540
    assert profile["files"]["train_identity.csv"]["rows"] == 144233
    assert profile["files"]["test_transaction.csv"]["rows"] == 506691
    assert profile["train_labelled"]["transactions"] == 590540
    assert profile["amount_currency"] == "USD"


@requires_real
def test_fraud_labels_and_benchmark_provenance() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    assert profile["train_labelled"]["fraud_count"] == 20663
    assert benchmark["measurements"]["labelled_fraud_transactions"]["value"] == 20663
    assert "isFraud" in benchmark["measurements"]["labelled_fraud_transactions"]["source"]
    assert benchmark["amount_currency"] == "USD"
    assert SAMPLE_SUBMISSION_NOTE in profile["notes"]


@requires_real
def test_mapping_amount_usd_and_no_ip_fabrication() -> None:
    frame = pd.DataFrame(
        {
            "TransactionID": [1],
            "isFraud": [0],
            "TransactionDT": [86400],
            "TransactionAmt": [12.5],
            "ProductCD": ["W"],
            "card1": [1],
        }
    )
    mapped = map_transactions(frame)
    assert mapped.loc[0, "amount_usd"] == 12.5
    assert mapped.loc[0, "amount_currency"] == AMOUNT_CURRENCY
    assert "ip_address" not in mapped.columns
    assert "timestamp" not in mapped.columns
    validate_required_columns(frame)


@requires_real
def test_temporal_buckets_and_productcd_exist() -> None:
    hourly = pd.read_csv(HOURLY)
    assert "relative_hour_bucket" in hourly.columns
    assert hourly["relative_hour_bucket"].min() >= 0
    assert not pd.api.types.is_datetime64_any_dtype(hourly["relative_hour_bucket"])
    benchmark = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    products = {row["value"] for row in benchmark["by_product"]}
    assert {"W", "C", "R", "H", "S"} <= products
    assert all(row["signal_kind"] == "OBSERVED FROM IEEE-CIS" for row in benchmark["by_product"])


@requires_real
def test_identity_coverage_is_partial() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    coverage = profile["identity_coverage"]["coverage"]
    assert 0 < coverage < 1
    assert profile["unavailable_signals"]["ip_subnet"]


@requires_real
def test_real_data_anomaly_detection_does_not_use_labels() -> None:
    hourly = pd.read_csv(HOURLY)
    first = detect_anomalies(hourly.head(200), limit=5)
    mutated = hourly.head(200).copy()
    mutated["labelled_fraud_rate"] = 1.0
    mutated["labelled_fraud_count"] = 99
    second = detect_anomalies(mutated, limit=5)
    assert [item["anomaly_id"] for item in first] == [item["anomaly_id"] for item in second]
    assert "evaluation.labels" not in inspect.getsource(detect_anomalies)
    assert "data.scenarios" not in inspect.getsource(detect_anomalies)
    anomalies = json.loads(ANOMALIES.read_text(encoding="utf-8"))
    assert anomalies["anomalies"][0]["kind"] == "REAL DATA ANOMALY"
    assert anomalies["anomalies"][0]["amount_currency"] == "USD"
    assert "coordinated abuse" in anomalies["anomalies"][0]["not_claimed"]


@requires_real
def test_evaluation_is_not_a_trained_model() -> None:
    evaluation = json.loads(EVALUATION.read_text(encoding="utf-8"))
    assert evaluation["methodology"]["not_a_trained_model"] is True
    assert evaluation["methodology"]["synthetic_calendar_used"] is False
    assert evaluation["pr_auc"]["calculated"] is False


@requires_real
def test_synthetic_seed_42_integrity() -> None:
    before = {path: _sha256(path) for path in LOCKED if path.is_file()}
    assert TRANSACTIONS_PATH.resolve() == (REPO / "data" / "transactions.csv").resolve()
    meta = json.loads((REPO / "data" / "dataset_meta.json").read_text(encoding="utf-8"))
    assert meta["seed"] == 42
    after = {path: _sha256(path) for path in LOCKED if path.is_file()}
    assert after == before


@requires_real
def test_real_api_reads_artifacts_not_the_ledger() -> None:
    from app.main import app

    client = TestClient(app)
    status = client.get("/api/real/status")
    assert status.status_code == 200
    assert status.json()["ready"] is True
    profile = client.get("/api/real/profile")
    assert profile.status_code == 200
    assert profile.json()["train_labelled"]["transactions"] == 590540
    anomalies = client.get("/api/real/anomalies")
    assert anomalies.status_code == 200
    anomaly_id = anomalies.json()["anomalies"][0]["anomaly_id"]
    detail = client.get(f"/api/real/anomalies/{anomaly_id}")
    assert detail.status_code == 200
    assert "evidence" in detail.json()
    investigation = client.get(f"/api/real/anomalies/{anomaly_id}/investigation")
    assert investigation.status_code == 200
    assert investigation.json()["provider_label"] in {"DETERMINISTIC", "LLM"}
    synthetic = client.get("/api/spikes")
    assert synthetic.status_code == 200
    assert synthetic.json()["count"] >= 1
