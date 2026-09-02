from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pandas as pd
import pytest

from evaluation.paths import (
    BASELINE_SPIKES_CSV_PATH,
    BASELINE_SPIKES_JSON_PATH,
    BASELINE_TRANSACTIONS_PATH,
    BASELINE_WINDOWS_PATH,
    HELDOUT_META_PATH,
    HELDOUT_SPIKES_CSV_PATH,
    HELDOUT_SPIKES_JSON_PATH,
    HELDOUT_TRANSACTIONS_PATH,
    HELDOUT_WINDOWS_PATH,
)
from evaluation.real_data.benchmark import NOT_CALCULATED, benchmark_from_frames, run_benchmark
from evaluation.real_data.coverage import build_coverage_report, coverage_from_dir
from evaluation.real_data.mapper import (
    AMOUNT_CURRENCY,
    InvalidRealDatasetError,
    MissingRealDatasetError,
    UNAVAILABLE_SIGNALS,
    WORLD,
    assert_not_synthetic_world_path,
    classify_fields,
    map_transactions,
    validate_required_columns,
)
from tools.paths import DATA_DIR, TRANSACTIONS_PATH

LOCKED_SYNTHETIC = (
    BASELINE_TRANSACTIONS_PATH,
    BASELINE_SPIKES_CSV_PATH,
    BASELINE_SPIKES_JSON_PATH,
    BASELINE_WINDOWS_PATH,
    BASELINE_TRANSACTIONS_PATH.parent / "dataset_meta.json",
)
LOCKED_HELDOUT = (
    HELDOUT_TRANSACTIONS_PATH,
    HELDOUT_META_PATH,
    HELDOUT_SPIKES_CSV_PATH,
    HELDOUT_SPIKES_JSON_PATH,
    HELDOUT_WINDOWS_PATH,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _fixture_transactions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "TransactionID": [1, 2, 3],
            "isFraud": [0, 1, 0],
            "TransactionDT": [86400, 90000, 180000],
            "TransactionAmt": [10.0, 25.5, 4.0],
            "ProductCD": ["W", "C", None],
            "card1": [1111, 1111, 2222],
            "card4": ["visa", "visa", None],
            "addr1": [123.0, None, 456.0],
            "addr2": [87.0, None, None],
            "P_emaildomain": ["gmail.com", None, "yahoo.com"],
        }
    )


def _fixture_identity() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "TransactionID": [1],
            "DeviceType": ["mobile"],
            "DeviceInfo": ["SAMSUNG"],
        }
    )


def _write_fixture(directory: Path, include_identity: bool = True) -> Path:
    _fixture_transactions().to_csv(directory / "train_transaction.csv", index=False)
    if include_identity:
        _fixture_identity().to_csv(directory / "train_identity.csv", index=False)
    return directory


def test_missing_raw_dataset_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(MissingRealDatasetError, match="does not download") as exc:
        run_benchmark(data_dir=tmp_path)
    message = str(exc.value)
    assert "train_transaction.csv" in message
    assert "Kaggle" in message
    assert "data/real" in message


def test_required_column_validation() -> None:
    frame = _fixture_transactions().drop(columns=["isFraud"])
    with pytest.raises(InvalidRealDatasetError, match="isFraud"):
        validate_required_columns(frame)
    missing_amount = _fixture_transactions().drop(columns=["TransactionAmt"])
    with pytest.raises(InvalidRealDatasetError, match="TransactionAmt"):
        validate_required_columns(missing_amount)


def test_amount_column_alias_transactionamt() -> None:
    frame = _fixture_transactions().rename(columns={"TransactionAmt": "TransactionAMT"})
    mapped = map_transactions(frame)
    assert list(mapped["amount"]) == [10.0, 25.5, 4.0]
    assert set(mapped["amount_currency"]) == {AMOUNT_CURRENCY}


def test_field_mapping() -> None:
    mapped = map_transactions(_fixture_transactions(), _fixture_identity())
    assert list(mapped["transaction_id"]) == [1, 2, 3]
    assert list(mapped["fraud_label"]) == [0, 1, 0]
    assert list(mapped["elapsed_seconds"]) == [86400, 90000, 180000]
    assert list(mapped["relative_hour_bucket"]) == [24, 25, 50]
    assert mapped.loc[0, "DeviceType"] == "mobile"
    assert pd.isna(mapped.loc[1, "DeviceType"])
    assert mapped.loc[0, "account_proxy"] == "1111|123.0|gmail.com"
    classification = classify_fields()
    assert classification["available"]["transaction_id"] == "TransactionID"
    assert classification["available"]["fraud_label"] == "isFraud"
    assert classification["world"] == WORLD


def test_unavailable_signals_are_explicit() -> None:
    report = build_coverage_report(_fixture_transactions(), _fixture_identity())
    for name, reason in UNAVAILABLE_SIGNALS.items():
        assert report["unavailable"][name]["available"] is False
        assert report["unavailable"][name]["reason"] == reason
    mapped = map_transactions(_fixture_transactions())
    for name in (
        "ip_address",
        "ip_subnet",
        "transaction_status",
        "sku_id",
        "timestamp",
        "account_id",
        "festive",
        "diwali",
    ):
        assert name not in mapped.columns


def test_transactiondt_is_never_a_fake_calendar_date() -> None:
    mapped = map_transactions(_fixture_transactions())
    assert "timestamp" not in mapped.columns
    assert "day_of_week" not in mapped.columns
    for column in mapped.columns:
        assert not pd.api.types.is_datetime64_any_dtype(mapped[column])
    dumped = mapped.to_csv(index=False)
    assert "1970" not in dumped
    assert "Diwali" not in dumped
    assert "festive" not in dumped.lower()
    note = classify_fields()["partial_proxy"]["elapsed_seconds"]["note"]
    assert "not a calendar timestamp" in note.lower()


def test_fraud_label_is_evaluation_only() -> None:
    notes = " ".join(classify_fields()["notes"])
    assert "evaluation-only" in notes
    coverage = build_coverage_report(_fixture_transactions())
    assert any("evaluation-only" in note for note in coverage["notes"])
    benchmark = benchmark_from_frames(_fixture_transactions())
    assert any("evaluation-only" in note for note in benchmark["notes"])
    assert benchmark["measurements"]["labelled_fraud_transactions"] == 1
    assert benchmark["measurements"]["labelled_fraud_amount_usd"] == 25.5
    assert benchmark["amount_currency"] == "USD"


def test_coverage_reports_missingness_honestly() -> None:
    report = build_coverage_report(_fixture_transactions(), _fixture_identity())
    assert report["totals"]["transactions"] == 3
    assert report["available"]["amount"]["non_null"] == 3
    assert report["available"]["fraud_label"]["non_null"] == 3
    assert report["partial_proxy"]["product"]["non_null"] == 2
    assert report["partial_proxy"]["device_identity"]["non_null"] == 1
    assert report["partial_proxy"]["device_identity"]["identity_file_present"] is True
    assert report["unavailable"]["ip_subnet"]["available"] is False


def test_benchmark_uses_relative_hours_and_usd() -> None:
    report = benchmark_from_frames(_fixture_transactions(), _fixture_identity())
    hours = report["measurements"]["hourly_transaction_volume"]
    assert [row["relative_hour_bucket"] for row in hours] == [24, 25, 50]
    assert report["amount_currency"] == "USD"
    assert "labelled_fraud_amount_usd" in report["measurements"]
    for item in NOT_CALCULATED:
        assert item in report["not_calculated"]


def test_raw_data_is_never_written_to_synthetic_paths(tmp_path: Path) -> None:
    before_synthetic = {path: _sha256(path) for path in LOCKED_SYNTHETIC if path.is_file()}
    before_heldout = {path: _sha256(path) for path in LOCKED_HELDOUT if path.is_file()}
    _write_fixture(tmp_path)
    output = tmp_path / "ieee_benchmark.json"
    run_benchmark(data_dir=tmp_path, output_path=output)
    assert output.is_file()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["world"] == WORLD
    assert payload["amount_currency"] == "USD"
    with pytest.raises(Exception, match="locked synthetic"):
        assert_not_synthetic_world_path(BASELINE_TRANSACTIONS_PATH)
    with pytest.raises(Exception, match="held-out"):
        assert_not_synthetic_world_path(HELDOUT_TRANSACTIONS_PATH)
    after_synthetic = {path: _sha256(path) for path in LOCKED_SYNTHETIC if path.is_file()}
    after_heldout = {path: _sha256(path) for path in LOCKED_HELDOUT if path.is_file()}
    assert after_synthetic == before_synthetic
    assert after_heldout == before_heldout
    assert not (DATA_DIR / "train_transaction.csv").exists()


def test_seed_42_and_heldout_artifacts_remain_unchanged(tmp_path: Path) -> None:
    before = {path: _sha256(path) for path in (*LOCKED_SYNTHETIC, *LOCKED_HELDOUT) if path.is_file()}
    _write_fixture(tmp_path, include_identity=False)
    coverage_from_dir(tmp_path)
    run_benchmark(data_dir=tmp_path, output_path=tmp_path / "out.json")
    after = {path: _sha256(path) for path in (*LOCKED_SYNTHETIC, *LOCKED_HELDOUT) if path.is_file()}
    assert after == before
    meta = json.loads((BASELINE_TRANSACTIONS_PATH.parent / "dataset_meta.json").read_text(encoding="utf-8"))
    assert meta["seed"] == 42
    heldout_meta = json.loads(HELDOUT_META_PATH.read_text(encoding="utf-8"))
    assert heldout_meta["seed"] == 2027


def test_tools_paths_remain_on_seed_42() -> None:
    assert TRANSACTIONS_PATH.resolve() == (DATA_DIR / "transactions.csv").resolve()
    assert TRANSACTIONS_PATH.resolve() != (DATA_DIR / "real" / "train_transaction.csv").resolve()


def test_adapter_does_not_reuse_scenario_labels() -> None:
    from evaluation.real_data import benchmark as benchmark_mod
    from evaluation.real_data import coverage as coverage_mod
    from evaluation.real_data import mapper as mapper_mod

    for module in (benchmark_mod, coverage_mod, mapper_mod):
        source = inspect.getsource(module)
        assert "evaluation.labels" not in source
        assert "evaluation.heldout" not in source
        assert "data.scenarios" not in source
        assert "tools.paths" not in source
