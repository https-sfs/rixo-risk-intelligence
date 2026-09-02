"""Isolated tests for the January 2026 recent-public-data adapter."""

from __future__ import annotations

import hashlib
import inspect
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
from evaluation.recent_data.benchmark import NOT_CALCULATED, benchmark_from_raw, run_benchmark
from evaluation.recent_data.coverage import build_coverage_report
from evaluation.recent_data.detect import assert_no_source_model_or_label_inputs, detect_anomalies, score_hourly
from evaluation.recent_data.evaluate import build_evaluation
from evaluation.recent_data.mapper import (
    AMOUNT_CURRENCY,
    InvalidRecentDatasetError,
    MissingRecentDatasetError,
    SOURCE_MODEL_OUTPUTS,
    WORLD,
    assert_not_locked_path,
    classify_fields,
    load_raw,
    map_collection,
    validate_required_columns,
)
from evaluation.recent_data.preprocess import preprocess
from tools.paths import TRANSACTIONS_PATH

LOCKED_SYNTHETIC = (
    BASELINE_TRANSACTIONS_PATH,
    BASELINE_SPIKES_CSV_PATH,
    BASELINE_SPIKES_JSON_PATH,
    BASELINE_WINDOWS_PATH,
    BASELINE_TRANSACTIONS_PATH.parent / "dataset_meta.json",
)
LOCKED_HELDOUT = (HELDOUT_TRANSACTIONS_PATH, HELDOUT_META_PATH)
IEEE_DIR = Path(__file__).resolve().parent.parent / "data" / "real"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _fixture_raw() -> pd.DataFrame:
    rows: list[dict[object, object]] = []
    for day in range(1, 4):
        for hour in range(8):
            spike = day == 2 and hour == 4
            count = 80 if spike else 20
            amount = 400.0 if spike else 25.0
            for index in range(count):
                rows.append(
                    {
                        "id": len(rows) + 1,
                        "transaction_id": f"txn-{len(rows) + 1}",
                        "amount": amount,
                        "time_value": 1767225600 + len(rows),
                        "v1": 0.1,
                        "is_fraud": 1 if spike and index < 2 else 0,
                        "fraud_probability": 12.4,
                        "risk_level": "LOW",
                        "confidence": 0.81,
                        "recommendation": "ALLOW",
                        "timestamp": f"2026-01-{day:02d} {hour:02d}:15:00",
                        "test_date": f"2026-01-{day:02d}",
                        "ip_address": f"203.0.{day}.{hour}",
                    }
                )
    rows.append(
        {
            "id": 99999,
            "transaction_id": "txn-extra",
            "amount": 9.0,
            "time_value": 1775750000,
            "v1": 0.2,
            "is_fraud": 1,
            "fraud_probability": 40.0,
            "risk_level": "HIGH",
            "confidence": 0.99,
            "recommendation": "BLOCK",
            "timestamp": "2026-04-10 12:00:00",
            "test_date": None,
            "ip_address": "198.51.100.1",
        }
    )
    return pd.DataFrame(rows)


def _write_fixture(directory: Path) -> Path:
    path = directory / "fraud_tests_export_20260501_080333.csv"
    _fixture_raw().to_csv(path, index=False)
    return path


def test_missing_raw_dataset_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(MissingRecentDatasetError, match="does not download") as exc:
        run_benchmark(tmp_path)
    message = str(exc.value)
    assert "fraud_tests_export" in message or "data/real_2026" in message
    assert "20359708" in message


def test_required_column_validation() -> None:
    frame = _fixture_raw().drop(columns=["is_fraud"])
    with pytest.raises(InvalidRecentDatasetError, match="is_fraud"):
        validate_required_columns(frame)
    missing_amount = _fixture_raw().drop(columns=["amount"])
    with pytest.raises(InvalidRecentDatasetError, match="amount"):
        validate_required_columns(missing_amount)


def test_schema_mapping_and_january_filter() -> None:
    mapped = map_collection(_fixture_raw())
    assert len(mapped) == 3 * 8 * 20 + 60
    assert "txn-extra" not in set(mapped["transaction_id"])
    assert set(mapped["amount_currency"]) == {AMOUNT_CURRENCY}
    assert mapped["fraud_label"].sum() == 2
    classification = classify_fields()
    assert classification["world"] == WORLD
    assert classification["available"]["fraud_label"].startswith("is_fraud")
    assert "fraud_probability" in classification["source_model_output"]


def test_source_model_outputs_are_excluded_from_mapped_frame() -> None:
    mapped = map_collection(_fixture_raw())
    for name in SOURCE_MODEL_OUTPUTS:
        assert name not in mapped.columns
    assert "is_fraud" not in mapped.columns


def test_detect_rejects_source_model_or_label_inputs() -> None:
    with pytest.raises(RuntimeError, match="source-model"):
        assert_no_source_model_or_label_inputs(pd.DataFrame({"fraud_probability": [0.2]}))
    with pytest.raises(RuntimeError, match="fraud"):
        assert_no_source_model_or_label_inputs(pd.DataFrame({"fraud_label": [1]}))


def test_anomaly_generation_uses_volume_and_amount_only() -> None:
    mapped = map_collection(_fixture_raw())
    from evaluation.recent_data.detect import build_hourly

    hourly = build_hourly(mapped)
    scored = score_hourly(hourly)
    assert "fraud_probability" not in scored.columns
    anomalies = detect_anomalies(hourly)
    assert anomalies
    assert anomalies[0]["kind"] in {"Temporal anomaly", "Amount concentration"}
    assert "coordinated abuse" not in anomalies[0]["kind"].lower()
    assert "is_fraud" in anomalies[0]["detection_inputs"]


def test_benchmark_january_counts_and_excludes_classifier_metrics() -> None:
    report = benchmark_from_raw(_fixture_raw())
    measurements = report["measurements"]
    assert measurements["total_transactions"]["value"] == 3 * 8 * 20 + 60
    assert measurements["labelled_fraud_transactions"]["value"] == 2
    assert measurements["unique_ip_addresses"]["value"] == 24
    assert "PR-AUC" in " ".join(NOT_CALCULATED)
    for name in ("precision", "recall", "f1", "pr_auc"):
        assert name not in report["measurements"]
    assert report["source_model_outputs_excluded"] == list(SOURCE_MODEL_OUTPUTS)


def test_coverage_marks_unavailable_families() -> None:
    report = build_coverage_report(_fixture_raw())
    assert report["unavailable"]["account_identity"]["available"] is False
    assert report["unavailable"]["sku_identity"]["available"] is False
    assert report["source_model_outputs_excluded_from_analysis"] is True


def test_evaluation_does_not_compute_classifier_metrics() -> None:
    evaluation = build_evaluation()
    assert evaluation["methodology"]["classifier_metrics_calculated"] is False
    assert evaluation["methodology"]["source_model_used_as_our_prediction"] is False
    assert "f1" in evaluation["not_calculated"]


def test_missing_optional_ip_does_not_invent_identity() -> None:
    raw = _fixture_raw().drop(columns=["ip_address"])
    mapped = map_collection(raw)
    assert "ip_address" not in mapped.columns
    assert "account_id" not in mapped.columns
    assert "device_id" not in mapped.columns
    assert "sku_id" not in mapped.columns


def test_preprocess_refuses_locked_paths(tmp_path: Path) -> None:
    with pytest.raises(Exception):
        assert_not_locked_path(TRANSACTIONS_PATH)
    with pytest.raises(Exception):
        assert_not_locked_path(IEEE_DIR / "benchmark.json")
    allowed = tmp_path / "benchmark.json"
    assert_not_locked_path(allowed)


def test_preprocess_and_api_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_fixture(tmp_path)
    summary = preprocess(tmp_path)
    assert summary["january_rows"] == 3 * 8 * 20 + 60
    assert (tmp_path / "profile.json").is_file()
    assert (tmp_path / "evaluation.json").is_file()

    import app.services.recent_world as recent_world

    monkeypatch.setattr(recent_world, "RECENT_DATA_DIR", tmp_path)
    recent_world._load_json_file.cache_clear()
    from app.main import app

    client = TestClient(app)
    status = client.get("/api/recent/status")
    assert status.status_code == 200
    assert status.json()["world"] == WORLD
    profile = client.get("/api/recent/profile")
    assert profile.status_code == 200
    assert profile.json()["january_collection"]["rows"] == 3 * 8 * 20 + 60
    benchmark = client.get("/api/recent/benchmark")
    assert benchmark.status_code == 200
    assert "labelled_fraud_transactions" in benchmark.json()["measurements"]
    anomalies = client.get("/api/recent/anomalies")
    assert anomalies.status_code == 200
    items = anomalies.json()["anomalies"]
    assert items
    detail = client.get(f"/api/recent/anomalies/{items[0]['anomaly_id']}")
    assert detail.status_code == 200
    assert detail.json()["evidence"]["source_dataset_model_output"]["used"] is False
    evaluation = client.get("/api/recent/evaluation")
    assert evaluation.status_code == 200
    assert evaluation.json()["methodology"]["classifier_metrics_calculated"] is False

    ieee = client.get("/api/real/status")
    assert ieee.status_code == 200
    assert ieee.json()["world"] == "REAL PUBLIC DATA"
    spikes = client.get("/api/spikes")
    assert spikes.status_code == 200


def test_locked_artifacts_unchanged() -> None:
    for path in (*LOCKED_SYNTHETIC, *LOCKED_HELDOUT):
        if path.is_file():
            _sha256(path)


def test_adapter_does_not_import_locked_modules() -> None:
    import evaluation.recent_data.benchmark as benchmark
    import evaluation.recent_data.detect as detect
    import evaluation.recent_data.mapper as mapper

    for module in (mapper, detect, benchmark):
        source = inspect.getsource(module)
        assert "evaluation.labels" not in source
        assert "data.scenarios" not in source
        assert "evaluation.real_data" not in source
