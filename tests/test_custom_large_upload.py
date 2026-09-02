"""Large Bring Your Data uploads: 200 MB+, IEEE-CIS CSVs, memory-safe streaming."""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from evaluation.paths import BASELINE_TRANSACTIONS_PATH

REPO = Path(__file__).resolve().parent.parent
IEEE_TRAIN = REPO / "data" / "real" / "train_transaction.csv"
IEEE_TEST = REPO / "data" / "real" / "test_transaction.csv"
ONE_GB = 1024 * 1024 * 1024
LOCKED = (
    BASELINE_TRANSACTIONS_PATH,
    REPO / "data" / "real_2026" / "anomalies.json",
    REPO / "data" / "real" / "model" / "model_evaluation.json",
    REPO / "data" / "real" / "model" / "ieee_hgb.joblib",
    REPO / "data" / "real" / "model" / "encoder.json",
)


async def _file_chunks(path: Path, size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    with path.open("rb") as handle:
        while True:
            piece = handle.read(size)
            if not piece:
                break
            yield piece


def _write_padded_csv(path: Path, minimum_bytes: int) -> None:
    with path.open("wb") as handle:
        handle.write(b"transaction_id,amount,timestamp,note\n")
        handle.write(b"txn-1,10.5,2026-03-01 10:00:00,")
        block = b"n" * (1024 * 1024)
        while handle.tell() < minimum_bytes:
            remaining = minimum_bytes - handle.tell()
            handle.write(block if remaining >= len(block) else block[:remaining])
        handle.write(b"\n")


def _process_rss() -> int | None:
    try:
        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    except Exception:  # noqa: BLE001
        return None


def test_200mb_csv_uploads(tmp_path: Path) -> None:
    from app.services.custom_world import ingest_upload_stream, max_upload_bytes, reset_sessions

    reset_sessions()
    path = tmp_path / "200mb.csv"
    _write_padded_csv(path, 200 * 1024 * 1024)
    assert path.stat().st_size >= 200 * 1024 * 1024
    assert path.stat().st_size < max_upload_bytes()
    payload = asyncio.run(ingest_upload_stream("200mb.csv", _file_chunks(path)))
    assert payload["inspection"]["schema_only"] is True
    assert payload["inspection"]["column_count"] >= 3
    assert payload["file_bytes"] >= 200 * 1024 * 1024
    reset_sessions()


def test_realistic_over_200mb_csv_is_accepted(tmp_path: Path) -> None:
    from app.services.custom_world import ingest_upload_stream, max_upload_bytes, reset_sessions

    reset_sessions()
    path = tmp_path / "220mb.csv"
    _write_padded_csv(path, 220 * 1024 * 1024)
    assert path.stat().st_size > 200 * 1024 * 1024
    assert path.stat().st_size < max_upload_bytes()
    payload = asyncio.run(ingest_upload_stream("220mb.csv", _file_chunks(path)))
    assert payload["world"] == "BRING YOUR DATA"
    reset_sessions()


def test_ieee_train_transaction_passes_upload_gate_and_inspects_without_full_buffer() -> None:
    from app.services.custom_world import get_session, ingest_upload_stream, reset_sessions
    from evaluation.custom_data.stream import byd_temp_dir

    if not IEEE_TRAIN.is_file():
        pytest.skip("IEEE train_transaction.csv is not present.")
    file_size = IEEE_TRAIN.stat().st_size
    assert file_size > 200 * 1024 * 1024
    assert file_size < ONE_GB
    reset_sessions()
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in LOCKED if path.is_file()}
    baseline = _process_rss()
    payload = asyncio.run(ingest_upload_stream(IEEE_TRAIN.name, _file_chunks(IEEE_TRAIN)))
    peak = _process_rss()
    proposals = {item["target"]: item for item in payload["mapping_proposals"]}
    assert proposals["transaction_id"]["suggested"] == "TransactionID"
    assert proposals["amount"]["suggested"] == "TransactionAmt"
    assert proposals["timestamp"]["suggested"] == "TransactionDT"
    assert proposals["product_sku"]["suggested"] == "ProductCD"
    assert proposals["fraud_label"]["suggested"] == "isFraud"
    assert payload["mapping_summary"]["identified_count"] == 5
    assert payload["inspection"]["schema_only"] is True
    assert payload["inspection"]["rows"] is None
    assert payload["file_bytes"] == file_size
    session = get_session(payload["session_id"])
    assert not hasattr(session, "raw")
    stored = Path(session.csv_path)
    assert stored.is_file()
    assert stored.stat().st_size == file_size
    assert stored.resolve().parent == byd_temp_dir().resolve()
    assert (REPO / "data" / "real").resolve() not in stored.resolve().parents
    if baseline is not None and peak is not None:
        extra = peak - baseline
        assert extra < file_size, (
            f"Working set grew by {extra / (1024 * 1024):.1f} MB while ingesting "
            f"{file_size / (1024 * 1024):.1f} MB; the upload path buffered too much."
        )
        assert extra < 550 * 1024 * 1024
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in LOCKED if path.is_file()}
    assert after == before
    reset_sessions()
    assert not stored.exists()


def test_ieee_test_transaction_passes_upload_size_gate() -> None:
    from app.services.custom_world import ingest_upload_stream, reset_sessions

    if not IEEE_TEST.is_file():
        pytest.skip("IEEE test_transaction.csv is not present.")
    file_size = IEEE_TEST.stat().st_size
    assert 200 * 1024 * 1024 < file_size < ONE_GB
    reset_sessions()
    payload = asyncio.run(ingest_upload_stream(IEEE_TEST.name, _file_chunks(IEEE_TEST)))
    assert payload["file_bytes"] == file_size
    assert payload["inspection"]["schema_only"] is True
    assert payload["inspection"]["rows"] is None
    proposals = {item["target"]: item for item in payload["mapping_proposals"]}
    assert proposals["transaction_id"]["suggested"] == "TransactionID"
    assert proposals["amount"]["suggested"] == "TransactionAmt"
    assert proposals["timestamp"]["suggested"] == "TransactionDT"
    reset_sessions()


def test_ieee_train_processes_chunked_without_retraining() -> None:
    from app.services.custom_world import (
        analyze_session,
        confirm_mapping,
        get_session,
        ingest_upload_stream,
        reset_sessions,
    )
    from models.ieee_fraud import JOBLIB_NAME, MODEL_DIR

    if not IEEE_TRAIN.is_file():
        pytest.skip("IEEE train_transaction.csv is not present.")
    reset_sessions()
    payload = asyncio.run(ingest_upload_stream(IEEE_TRAIN.name, _file_chunks(IEEE_TRAIN)))
    session_id = payload["session_id"]
    accepted = {
        item["target"]: item["suggested"]
        for item in payload["mapping_proposals"]
        if item.get("auto_accepted")
    }
    assert accepted["transaction_id"] == "TransactionID"
    assert accepted["amount"] == "TransactionAmt"
    mapped = confirm_mapping(session_id, accepted)
    assert mapped["compatibility"]["status"] == "compatible"
    assert mapped["compatibility"]["may_use_ieee_model"] is True
    baseline = _process_rss()
    analyzed = analyze_session(session_id)
    peak = _process_rss()
    assert analyzed["summary"]["chunked"] is True
    assert analyzed["summary"]["transactions_analyzed"] >= 590_000
    assert analyzed["summary"]["labels_used_as_detector_input"] is False
    dumped = str(analyzed["anomalies"])
    assert "1970" not in dumped
    for item in analyzed["anomalies"]:
        assert item.get("time_kind") == "relative_elapsed"
        assert "1970" not in str(item.get("time_display"))
        amount = item.get("amount")
        assert amount is None or amount == amount
        assert str(amount).lower() != "nan"
    if (MODEL_DIR / JOBLIB_NAME).is_file():
        assert analyzed["summary"]["supervised_scores"] is True
        overlay = analyzed["model_overlay"]
        assert overlay["provenance"] == "MODEL PREDICTION · USER DATASET"
        assert overlay["retrained"] is False
        assert overlay["chunked"] is True
        assert overlay["scored_rows"] >= 590_000
        assert overlay["threshold"] == 0.5
        evaluation = analyzed["evaluation"]
        assert evaluation["used_as_detector_input"] is False
        assert evaluation["retrained_on_upload"] is False
    session = get_session(session_id)
    assert not hasattr(session, "raw")
    if baseline is not None and peak is not None:
        extra = peak - baseline
        assert extra < 800 * 1024 * 1024
    reset_sessions()
