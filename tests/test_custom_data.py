"""Bring Your Data: inspect, map, compatibility, detect, evaluate, govern."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from io import StringIO
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from evaluation.custom_data.compatibility import assess_compatibility
from evaluation.custom_data.detect import detect_anomalies
from evaluation.custom_data.evaluate import evaluate_user_labels
from evaluation.custom_data.governance import (
    CustomGovernanceError,
    decide_from_investigation,
    investigation_state,
    propose_action,
    record_decision,
    reset_store,
    simulate_action,
)
from evaluation.custom_data.mapping import (
    high_confidence_mapping,
    mapping_readiness,
    propose_mappings,
    validate_mapping,
)
from evaluation.paths import BASELINE_TRANSACTIONS_PATH
from models.ieee_fraud.predict import PredictSchemaError, assert_ieee_predict_schema

REPO = Path(__file__).resolve().parent.parent
LOCKED = (
    BASELINE_TRANSACTIONS_PATH,
    REPO / "data" / "real_2026" / "anomalies.json",
    REPO / "data" / "real" / "model" / "model_evaluation.json",
)


def _minimal_csv() -> str:
    rows = ["transaction_id,amount,timestamp"]
    for day in range(1, 4):
        for hour in range(8):
            count = 80 if day == 2 and hour == 4 else 12
            amount = 400 if day == 2 and hour == 4 else 20
            for index in range(count):
                rows.append(f"txn-{day}-{hour}-{index},{amount},2026-03-{day:02d} {hour:02d}:15:00")
    return "\n".join(rows) + "\n"


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


def _ieee_ready_csv(rows: int = 8) -> str:
    lines = [
        "TransactionID,TransactionDT,TransactionAmt,ProductCD,card1,C1,C2,C3,V1,V2,V3,addr1,isFraud"
    ]
    for index in range(rows):
        fraud = 1 if index < 2 else 0
        lines.append(
            f"{index + 1},{10_000 + index * 200},{20 + index},W,{1000 + index},1,2,3,0.1,0.2,0.3,123,{fraud}"
        )
    return "\n".join(lines) + "\n"


def _labelled_csv() -> str:
    rows = ["transaction_id,amount,timestamp,is_fraud"]
    for index in range(40):
        fraud = 1 if index < 4 else 0
        rows.append(f"txn-{index},{20 + index},2026-03-01 10:00:00,{fraud}")
    return "\n".join(rows) + "\n"


def test_mapping_does_not_assume_ambiguous_columns() -> None:
    proposals = propose_mappings(["amt", "value", "when"])
    amount = next(item for item in proposals if item["target"] == "amount")
    assert amount["ambiguous"] is True
    assert amount["suggested"] is None
    assert amount["auto_accepted"] is False
    confirmed = validate_mapping(["amt", "when"], {"amount": "amt", "timestamp": "when"})
    assert confirmed == {"amount": "amt", "timestamp": "when"}


def test_exact_amount_outranks_alias_candidates() -> None:
    proposals = propose_mappings(["amt", "amount", "value", "when"])
    amount = next(item for item in proposals if item["target"] == "amount")
    assert amount["suggested"] == "amount"
    assert amount["confidence"] == "high"
    assert amount["auto_accepted"] is True
    assert amount["ambiguous"] is False


def test_ieee_exact_mappings_outrank_card_columns() -> None:
    columns = [
        "TransactionID",
        "isFraud",
        "TransactionDT",
        "TransactionAmt",
        "ProductCD",
        "card1",
        "card2",
        "card4",
        "C1",
        "V1",
        "addr1",
    ]
    proposals = {item["target"]: item for item in propose_mappings(columns)}
    assert proposals["transaction_id"]["suggested"] == "TransactionID"
    assert proposals["amount"]["suggested"] == "TransactionAmt"
    assert proposals["timestamp"]["suggested"] == "TransactionDT"
    assert proposals["product_sku"]["suggested"] == "ProductCD"
    assert proposals["fraud_label"]["suggested"] == "isFraud"
    assert proposals["transaction_id"]["confidence"] == "high"
    assert proposals["amount"]["confidence"] == "high"
    assert proposals["timestamp"]["confidence"] == "high"
    accepted = high_confidence_mapping(list(proposals.values()))
    assert accepted["transaction_id"] == "TransactionID"
    assert accepted["amount"] == "TransactionAmt"
    assert accepted["timestamp"] == "TransactionDT"
    assert "card1" not in accepted.values()
    assert "card2" not in accepted.values()
    assert "card4" not in accepted.values()


def test_low_confidence_mappings_are_not_silently_accepted() -> None:
    proposals = {item["target"]: item for item in propose_mappings(["card1", "card2", "card4", "C1"])}
    accepted = high_confidence_mapping(list(proposals.values()))
    assert accepted == {}
    assert proposals["transaction_id"]["auto_accepted"] is False
    assert proposals["amount"]["auto_accepted"] is False
    assert proposals["timestamp"]["auto_accepted"] is False
    assert mapping_readiness(accepted)["ready"] is False


def test_ieee_train_header_maps_without_scanning_rows() -> None:
    from evaluation.custom_data.inspect import inspect_schema
    from evaluation.custom_data.stream import read_columns

    path = REPO / "data" / "real" / "train_transaction.csv"
    if not path.is_file():
        pytest.skip("IEEE train_transaction.csv is not present.")
    columns = read_columns(path)
    assert columns[0] == "TransactionID"
    proposals = {item["target"]: item for item in propose_mappings(columns)}
    assert proposals["transaction_id"]["suggested"] == "TransactionID"
    assert proposals["amount"]["suggested"] == "TransactionAmt"
    assert proposals["timestamp"]["suggested"] == "TransactionDT"
    assert proposals["product_sku"]["suggested"] == "ProductCD"
    assert proposals["fraud_label"]["suggested"] == "isFraud"
    schema = inspect_schema(path, path.name)
    assert schema["schema_only"] is True
    assert schema["rows"] is None
    assert schema["column_count"] == len(columns)


def test_schema_inspect_does_not_scan_csv_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from evaluation.custom_data import inspect as inspect_mod
    from evaluation.custom_data.inspect import inspect_schema

    path = tmp_path / "header.csv"
    path.write_text(
        "TransactionID,TransactionAmt,TransactionDT,ProductCD,isFraud,card1\n1,10,100,W,0,111\n",
        encoding="utf-8",
    )

    def _fail(*_args: object, **_kwargs: object):
        raise AssertionError("inspect_schema must not scan CSV rows")

    monkeypatch.setattr(inspect_mod, "iter_csv_chunks", _fail)
    payload = inspect_schema(path, "header.csv")
    assert payload["detected_candidate_fields"]["amount"] == "TransactionAmt"
    assert payload["schema_only"] is True


def test_partial_compatibility_for_amount_and_timestamp_only() -> None:
    mapping = {"transaction_id": "transaction_id", "amount": "amount", "timestamp": "timestamp"}
    gate = assess_compatibility(["transaction_id", "amount", "timestamp"], mapping)
    assert gate["status"] == "partial"
    assert gate["may_use_ieee_model"] is False
    assert gate["may_score_classifier"] is True
    assert gate["anomaly_ready"] is True
    assert gate["features_fabricated"] is False
    assert "will not fabricate" in gate["reason"]


def test_compatible_requires_official_ieee_contract() -> None:
    columns = [
        "TransactionID",
        "TransactionAmt",
        "TransactionDT",
        "ProductCD",
        "card1",
        "C1",
        "C2",
        "C3",
        "V1",
        "V2",
        "V3",
        "addr1",
    ]
    gate = assess_compatibility(columns, {"amount": "TransactionAmt", "timestamp": "TransactionDT"})
    assert gate["status"] == "compatible"
    assert gate["may_use_ieee_model"] is True


def test_january_pca_does_not_unlock_ieee_model() -> None:
    columns = ["transaction_id", "amount", "timestamp", "v1", "v2", "v28"]
    gate = assess_compatibility(columns, {"amount": "amount", "timestamp": "timestamp"})
    assert gate["status"] == "partial"
    assert gate["may_use_ieee_model"] is False
    with pytest.raises(PredictSchemaError, match="January 2026"):
        assert_ieee_predict_schema(columns)


def test_custom_anomaly_detection_ignores_labels() -> None:
    frame = pd.read_csv(StringIO(_minimal_csv()))
    frame["fraud_label"] = 0
    anomalies, summary = detect_anomalies(frame)
    assert summary["labels_used_as_detector_input"] is False
    assert summary["temporal_anomalies"] + summary["amount_concentration_anomalies"] >= 1
    assert any(item["kind"] in {"Temporal anomaly", "Amount concentration"} for item in anomalies)
    assert all("fraud_label" not in item["detection_inputs"] or "were not used" in item["detection_inputs"] for item in anomalies)


def test_user_labels_without_scores_are_rate_only() -> None:
    frame = pd.read_csv(StringIO(_labelled_csv()))
    frame = frame.rename(columns={"is_fraud": "fraud_label"})
    evaluation = evaluate_user_labels(frame, None)
    assert evaluation["available"] is True
    assert evaluation["provenance"] == "USER-PROVIDED GROUND TRUTH"
    assert evaluation["classifier_metrics_calculated"] is False
    assert evaluation["used_as_detector_input"] is False
    assert evaluation["retrained_on_upload"] is False
    assert evaluation["fraud_count"] == 4


def test_custom_governance_requires_approval() -> None:
    reset_store()
    decision = decide_from_investigation(
        {"anomaly_id": "cda-20260302-04", "signals": ["elevated transaction amount"], "live_score": 4.0},
        {"anomaly_id": "cda-20260302-04", "hour_start": "2026-03-02T04:00:00", "signals": ["elevated transaction amount"]},
        {"summary": "amount", "provider": "deterministic"},
    )
    proposal = propose_action("cxs-test", decision)
    with pytest.raises(CustomGovernanceError, match="not been explicitly approved"):
        simulate_action("cxs-test", proposal["action_id"])


def test_investigation_state_is_per_anomaly_and_does_not_duplicate() -> None:
    reset_store()
    decision = decide_from_investigation(
        {"anomaly_id": "cda-20260302-04", "signals": ["elevated transaction amount"], "live_score": 4.0},
        {"anomaly_id": "cda-20260302-04", "hour_start": "2026-03-02T04:00:00", "signals": ["elevated transaction amount"]},
        {"summary": "amount", "provider": "deterministic"},
    )
    first = record_decision("cxs-test", decision)
    second = record_decision("cxs-test", decision)
    assert second["recorded_at"] == first["recorded_at"]
    proposal = propose_action("cxs-test", decision)
    again = propose_action("cxs-test", decision)
    assert again["action_id"] == proposal["action_id"]
    state_a = investigation_state("cxs-test", "cda-20260302-04")
    assert state_a["status"]["decision"] == "recorded"
    assert state_a["proposal"]["action_id"] == proposal["action_id"]
    assert len(state_a["audit"]) == 2
    state_b = investigation_state("cxs-test", "cda-other")
    assert state_b["status"]["decision"] == "not_recorded"
    assert state_b["proposal"] is None
    assert state_b["audit"] == []


def test_default_limits_are_1gb_and_two_million_rows() -> None:
    from app.services.custom_world import (
        assert_rows_within_limit,
        assert_size_within_limit,
        max_row_limit,
        max_upload_bytes,
    )

    assert max_upload_bytes() == 1024 * 1024 * 1024
    assert max_row_limit() == 2_000_000
    assert_size_within_limit(1024 * 1024 * 1024)
    assert_rows_within_limit(2_000_000)
    with pytest.raises(Exception, match="1.00 GB"):
        assert_size_within_limit(1024 * 1024 * 1024 + 1)
    with pytest.raises(Exception, match="more than 2,000,000 rows"):
        assert_rows_within_limit(2_000_001)


def test_size_and_row_limit_messages_name_the_exact_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import custom_world

    monkeypatch.setattr(custom_world, "max_upload_bytes", lambda: 1024)
    with pytest.raises(custom_world.CustomDataError, match="size limit is 0.0 MB \\(1,024 bytes\\)"):
        custom_world.assert_size_within_limit(2048)
    monkeypatch.setattr(custom_world, "max_row_limit", lambda: 5)
    with pytest.raises(custom_world.CustomDataError, match="more than 5 rows"):
        custom_world.assert_rows_within_limit(20)


def test_content_length_rejects_before_reading_body(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from app.routers import custom as custom_router
    from app.services import custom_world

    monkeypatch.setattr(custom_world, "max_upload_bytes", lambda: 1024)

    class _Request:
        headers = {"content-length": str(2 * 1024 * 1024 * 1024), "x-filename": "huge.csv"}

        def stream(self):
            raise AssertionError("streamed body must not be read after Content-Length rejection")

    with pytest.raises(custom_world.CustomDataError, match="Upload rejected"):
        asyncio.run(custom_router.custom_upload(_Request()))


def test_content_length_rejects_via_http(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import custom_world
    from app.main import app

    custom_world.reset_sessions()
    monkeypatch.setattr(custom_world, "max_upload_bytes", lambda: 512)
    client = TestClient(app)
    response = client.post(
        "/api/custom/upload",
        content=b"transaction_id,amount,timestamp\n1,2,2026-01-01\n",
        headers={"X-Filename": "over.csv", "Content-Length": "2048"},
    )
    if response.status_code != 400:
        fat = ("transaction_id,amount,timestamp\n" + ("x,1,2026-01-01\n" * 80)).encode()
        assert len(fat) > 512
        response = client.post(
            "/api/custom/upload",
            content=fat,
            headers={"X-Filename": "over.csv"},
        )
    assert response.status_code == 400
    assert "size limit" in response.json()["detail"]
    assert "Upload rejected" in response.json()["detail"]


def test_streamed_upload_exceeding_limit_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from app.services import custom_world

    custom_world.reset_sessions()
    monkeypatch.setattr(custom_world, "max_upload_bytes", lambda: 1024)

    async def _chunks():
        yield b"transaction_id,amount,timestamp\n"
        yield b"x" * 2048

    with pytest.raises(custom_world.CustomDataError, match="size limit"):
        asyncio.run(custom_world.ingest_upload_stream("stream.csv", _chunks()))


def test_over_one_gigabyte_is_rejected() -> None:
    from app.services.custom_world import CustomDataError, assert_size_within_limit, max_upload_bytes

    ceiling = max_upload_bytes()
    assert ceiling == 1024 * 1024 * 1024
    with pytest.raises(CustomDataError, match="Upload rejected"):
        assert_size_within_limit(ceiling + 1)


def test_row_limit_is_named_in_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import custom_world
    from app.main import app

    custom_world.reset_sessions()
    monkeypatch.setattr(custom_world, "max_row_limit", lambda: 3)
    client = TestClient(app)
    csv = "transaction_id,amount,timestamp\n" + "\n".join(
        f"txn-{index},10,2026-03-01 10:00:00" for index in range(8)
    )
    uploaded = client.post(
        "/api/custom/upload",
        content=csv.encode("utf-8"),
        headers={"X-Filename": "rows.csv"},
    )
    assert uploaded.status_code == 200
    session_id = uploaded.json()["session_id"]
    client.post(
        f"/api/custom/sessions/{session_id}/mapping",
        json={"mapping": {"transaction_id": "transaction_id", "amount": "amount", "timestamp": "timestamp"}},
    )
    response = client.post(f"/api/custom/sessions/{session_id}/analyze")
    assert response.status_code == 400
    assert "more than 3 rows" in response.json()["detail"]
    assert "Upload rejected" in response.json()["detail"]


def test_row_limit_stops_without_loading_the_full_csv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from evaluation.custom_data import inspect as inspect_mod
    from evaluation.custom_data.inspect import inspect_path
    from evaluation.custom_data.schema import CustomDataError
    from evaluation.custom_data.stream import iter_csv_chunks

    path = tmp_path / "many.csv"
    path.write_text(
        "transaction_id,amount,timestamp\n"
        + "\n".join(f"txn-{index},10,2026-03-01 10:00:00" for index in range(80))
        + "\n",
        encoding="utf-8",
    )
    seen = {"chunks": 0}
    real = iter_csv_chunks

    def _counting(source, chunksize=10_000, usecols=None):
        for chunk in real(source, chunksize=5, usecols=usecols):
            seen["chunks"] += 1
            yield chunk

    monkeypatch.setattr(inspect_mod, "iter_csv_chunks", _counting)
    with pytest.raises(CustomDataError, match="more than 12 rows"):
        inspect_path(path, "many.csv", max_rows=12)
    assert 1 <= seen["chunks"] <= 4
    assert seen["chunks"] < 16


def test_router_streams_and_never_buffers_the_request_body() -> None:
    router = (REPO / "backend" / "app" / "routers" / "custom.py").read_text(encoding="utf-8")
    world = (REPO / "backend" / "app" / "services" / "custom_world.py").read_text(encoding="utf-8")
    assert "request.stream()" in router
    assert "ingest_upload_stream" in router
    assert "begin_chunked_upload" in router
    assert "write_upload_part" in router
    assert "await request.body()" not in world


def test_small_csv_still_uploads() -> None:
    from app.services.custom_world import create_session, reset_sessions

    reset_sessions()
    payload = create_session("small.csv", _minimal_csv().encode("utf-8"))
    assert payload["inspection"]["schema_only"] is True
    assert payload["inspection"]["rows"] is None
    assert payload["inspection"]["column_count"] == 3
    assert payload["privacy"]["storage"] == "isolated_temp_file"
    accepted = {item["target"]: item["suggested"] for item in payload["mapping_proposals"] if item["auto_accepted"]}
    assert accepted == {
        "transaction_id": "transaction_id",
        "amount": "amount",
        "timestamp": "timestamp",
    }
    reset_sessions()


def test_chunked_upload_reassembles_and_creates_a_session() -> None:
    from app.main import app
    from app.services.custom_world import reset_sessions

    reset_sessions()
    client = TestClient(app)
    content = _minimal_csv().encode("utf-8")
    mid = max(1, len(content) // 2)
    begin = client.post("/api/custom/upload/begin", json={"filename": "parts.csv", "size": len(content)})
    assert begin.status_code == 200
    upload_id = begin.json()["upload_id"]
    first = client.post(
        "/api/custom/upload/part",
        content=content[:mid],
        headers={"X-Upload-Id": upload_id, "X-Part-Index": "0"},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/custom/upload/part",
        content=content[mid:],
        headers={"X-Upload-Id": upload_id, "X-Part-Index": "1"},
    )
    assert second.status_code == 200
    finished = client.post("/api/custom/upload/finish", json={"upload_id": upload_id, "parts": 2})
    assert finished.status_code == 200
    body = finished.json()
    assert body["filename"] == "parts.csv"
    assert body["session_id"]
    reset_sessions()


def test_custom_status_advertises_chunked_upload_limits() -> None:
    from app.main import app

    status = TestClient(app).get("/api/custom/status")
    assert status.status_code == 200
    limits = status.json()["upload_limits"]
    assert limits["chunked_upload"] is True
    assert limits["chunk_bytes"] == 3 * 1024 * 1024
    assert limits["platform_body_limit_bytes"] == int(4.5 * 1024 * 1024)


def test_file_over_previous_50mb_guard_is_accepted(tmp_path: Path) -> None:
    import asyncio

    from app.services.custom_world import ingest_upload_stream, max_upload_bytes, reset_sessions

    reset_sessions()
    path = tmp_path / "over50.csv"
    _write_padded_csv(path, 50 * 1024 * 1024 + 4096)
    assert 50 * 1024 * 1024 < path.stat().st_size < max_upload_bytes()
    payload = asyncio.run(ingest_upload_stream("over50.csv", _file_chunks(path)))
    assert payload["inspection"]["schema_only"] is True
    assert payload["inspection"]["column_count"] >= 3
    assert payload["world"] == "BRING YOUR DATA"
    reset_sessions()


def test_january_csv_uploads_when_present() -> None:
    import asyncio

    from app.services.custom_world import ingest_upload_stream, reset_sessions

    path = REPO / "data" / "real_2026" / "fraud_tests_export_20260501_080333.csv"
    if not path.is_file():
        pytest.skip("January 2026 CSV is not present.")
    reset_sessions()
    payload = asyncio.run(ingest_upload_stream(path.name, _file_chunks(path)))
    assert payload["inspection"]["schema_only"] is True
    assert payload["inspection"]["column_count"] > 10
    assert payload["privacy"]["mixed_with_existing_datasets"] is False
    reset_sessions()


def test_custom_upload_api_partial_flow_and_isolation() -> None:
    reset_store()
    from app.services.custom_world import reset_sessions
    from app.main import app

    reset_sessions()
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in LOCKED if path.is_file()}
    client = TestClient(app)
    uploaded = client.post(
        "/api/custom/upload",
        content=_minimal_csv().encode("utf-8"),
        headers={"X-Filename": "merchant.csv"},
    )
    assert uploaded.status_code == 200
    body = uploaded.json()
    assert body["world"] == "BRING YOUR DATA"
    assert body["privacy"]["mixed_with_existing_datasets"] is False
    session_id = body["session_id"]
    mapped = client.post(
        f"/api/custom/sessions/{session_id}/mapping",
        json={
            "mapping": {
                "transaction_id": "transaction_id",
                "amount": "amount",
                "timestamp": "timestamp",
            }
        },
    )
    assert mapped.status_code == 200
    assert mapped.json()["compatibility"]["status"] == "partial"
    assert mapped.json()["compatibility"]["may_use_ieee_model"] is False
    analyzed = client.post(f"/api/custom/sessions/{session_id}/analyze")
    assert analyzed.status_code == 200
    summary = analyzed.json()["summary"]
    assert summary["transactions_analyzed"] > 50
    from models.ieee_fraud import JOBLIB_NAME, MODEL_DIR

    if (MODEL_DIR / JOBLIB_NAME).is_file():
        assert summary["supervised_scores"] is True
        assert analyzed.json()["model_overlay"]["features_fabricated"] is False
    else:
        assert summary["supervised_scores"] is False
    anomalies = analyzed.json()["anomalies"]
    assert anomalies
    anomaly_id = anomalies[0]["anomaly_id"]
    propose = client.post(
        f"/api/custom/sessions/{session_id}/actions/propose",
        json={"anomaly_id": anomaly_id},
    )
    assert propose.status_code == 200
    action_id = propose.json()["action_id"]
    blocked = client.post(f"/api/custom/sessions/{session_id}/actions/{action_id}/simulate")
    assert blocked.status_code == 409
    client.post(
        f"/api/custom/sessions/{session_id}/actions/{action_id}/approve",
        json={"approved_by": "analyst"},
    )
    simulated = client.post(f"/api/custom/sessions/{session_id}/actions/{action_id}/simulate")
    assert simulated.status_code == 200
    assert simulated.json()["simulated"] is True
    assert "Razorpay" in simulated.json()["result"]
    trail = client.get(f"/api/custom/sessions/{session_id}/audit?anomaly_id={anomaly_id}")
    kinds = {event["kind"] for event in trail.json()["events"]}
    assert "CUSTOM_ACTION_SIMULATED" in kinds
    recent = client.get("/api/recent/audit")
    if recent.status_code == 200:
        assert "CUSTOM_ACTION_SIMULATED" not in {event["kind"] for event in recent.json()["events"]}
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in LOCKED if path.is_file()}
    assert after == before


def test_get_session_reuses_analyzed_results_and_governance_without_reanalyze() -> None:
    from app.services.custom_world import reset_sessions
    from app.main import app

    reset_sessions()
    client = TestClient(app)
    uploaded = client.post(
        "/api/custom/upload",
        content=_minimal_csv().encode("utf-8"),
        headers={"X-Filename": "merchant.csv"},
    )
    session_id = uploaded.json()["session_id"]
    client.post(
        f"/api/custom/sessions/{session_id}/mapping",
        json={
            "mapping": {
                "transaction_id": "transaction_id",
                "amount": "amount",
                "timestamp": "timestamp",
            }
        },
    )
    analyzed = client.post(f"/api/custom/sessions/{session_id}/analyze")
    assert analyzed.status_code == 200
    first_ids = [item["anomaly_id"] for item in analyzed.json()["anomalies"]]
    assert first_ids

    restored = client.get(f"/api/custom/sessions/{session_id}")
    assert restored.status_code == 200
    assert restored.json()["session_id"] == session_id
    assert restored.json()["summary"] == analyzed.json()["summary"]
    assert [item["anomaly_id"] for item in restored.json()["anomalies"]] == first_ids

    anomaly_a = first_ids[0]
    propose = client.post(
        f"/api/custom/sessions/{session_id}/actions/propose",
        json={"anomaly_id": anomaly_a},
    )
    action_id = propose.json()["action_id"]
    client.post(
        f"/api/custom/sessions/{session_id}/actions/{action_id}/approve",
        json={"approved_by": "analyst"},
    )
    client.post(f"/api/custom/sessions/{session_id}/actions/{action_id}/simulate")

    again = client.get(f"/api/custom/sessions/{session_id}")
    assert [item["anomaly_id"] for item in again.json()["anomalies"]] == first_ids

    action = client.get(f"/api/custom/sessions/{session_id}/actions/{action_id}")
    assert action.status_code == 200
    assert action.json()["proposal"]["action_id"] == action_id
    assert action.json()["approval"]["approved"] is True
    assert action.json()["execution"]["simulated"] is True

    detail_a = client.get(f"/api/custom/sessions/{session_id}/anomalies/{anomaly_a}")
    assert detail_a.status_code == 200
    gov_a = detail_a.json()["investigation_state"]
    assert gov_a["status"]["decision"] == "recorded"
    assert gov_a["status"]["approval"] == "approved"
    assert gov_a["status"]["simulation"] == "completed"
    assert gov_a["proposal"]["action_id"] == action_id
    assert [event["kind"] for event in gov_a["audit"]] == [
        "CUSTOM_DECISION_RECORDED",
        "CUSTOM_ACTION_PROPOSED",
        "CUSTOM_ACTION_APPROVED",
        "CUSTOM_ACTION_SIMULATED",
    ]
    restored_again = client.get(f"/api/custom/sessions/{session_id}/anomalies/{anomaly_a}")
    assert [event["kind"] for event in restored_again.json()["investigation_state"]["audit"]] == [
        event["kind"] for event in gov_a["audit"]
    ]
    assert again.json()["anomalies"][0]["investigation"]["decision"] == "recorded"

    trail_a = client.get(f"/api/custom/sessions/{session_id}/audit?anomaly_id={anomaly_a}")
    assert "CUSTOM_ACTION_SIMULATED" in {event["kind"] for event in trail_a.json()["events"]}
    if len(first_ids) > 1:
        trail_b = client.get(f"/api/custom/sessions/{session_id}/audit?anomaly_id={first_ids[1]}")
        assert trail_b.json()["events"] == []
        gov_b = client.get(f"/api/custom/sessions/{session_id}/anomalies/{first_ids[1]}").json()[
            "investigation_state"
        ]
        assert gov_b["status"]["decision"] == "not_recorded"
        assert gov_b["proposal"] is None
        assert gov_b["audit"] == []


def test_temporary_upload_is_isolated_and_cleaned_up() -> None:
    from app.services.custom_world import create_session, get_session, reset_sessions
    from evaluation.custom_data.stream import byd_temp_dir

    reset_sessions()
    payload = create_session("cleanup.csv", _minimal_csv().encode("utf-8"))
    session = get_session(payload["session_id"])
    path = Path(session.csv_path)
    assert path.is_file()
    resolved = path.resolve()
    assert resolved.parent == byd_temp_dir().resolve()
    data_root = (REPO / "data").resolve()
    assert data_root not in resolved.parents
    assert "data\\real" not in str(resolved).lower() or str(data_root) not in str(resolved)
    assert not str(resolved).startswith(str(REPO / "data" / "real"))
    assert not str(resolved).startswith(str(REPO / "data" / "real_2026"))
    reset_sessions()
    assert not path.exists()


def test_partial_dataset_does_not_receive_fake_model_scores() -> None:
    from app.services.custom_world import analyze_session, confirm_mapping, create_session, reset_sessions
    from models.ieee_fraud import JOBLIB_NAME, MODEL_DIR

    reset_sessions()
    payload = create_session("partial.csv", _labelled_csv().encode("utf-8"))
    confirm_mapping(
        payload["session_id"],
        {
            "transaction_id": "transaction_id",
            "amount": "amount",
            "timestamp": "timestamp",
            "fraud_label": "is_fraud",
        },
    )
    analyzed = analyze_session(payload["session_id"])
    assert analyzed["compatibility"]["status"] == "partial"
    assert analyzed["compatibility"]["may_use_ieee_model"] is False
    assert analyzed["compatibility"]["may_score_classifier"] is True
    evaluation = analyzed["evaluation"]
    assert evaluation["used_as_detector_input"] is False
    assert evaluation["retrained_on_upload"] is False
    assert evaluation["provenance"] == "USER-PROVIDED GROUND TRUTH"
    if not (MODEL_DIR / JOBLIB_NAME).is_file():
        assert analyzed["summary"]["supervised_scores"] is False
        reset_sessions()
        pytest.skip("Persisted classifier artifact is not present.")
    assert analyzed["summary"]["supervised_scores"] is True
    overlay = analyzed["model_overlay"]
    assert overlay["features_fabricated"] is False
    assert overlay["invoked_shared_infer"] is True
    assert overlay["retrained"] is False
    reset_sessions()


def test_ready_dataset_uses_persisted_ieee_model_only() -> None:
    from app.services.custom_world import analyze_session, confirm_mapping, create_session, reset_sessions
    from models.ieee_fraud import JOBLIB_NAME, MODEL_DIR

    reset_sessions()
    payload = create_session("ieee-ready.csv", _ieee_ready_csv().encode("utf-8"))
    mapped = confirm_mapping(
        payload["session_id"],
        {
            "transaction_id": "TransactionID",
            "amount": "TransactionAmt",
            "timestamp": "TransactionDT",
            "fraud_label": "isFraud",
        },
    )
    assert mapped["compatibility"]["status"] == "compatible"
    assert mapped["compatibility"]["may_use_ieee_model"] is True
    analyzed = analyze_session(payload["session_id"])
    if not (MODEL_DIR / JOBLIB_NAME).is_file():
        assert analyzed["summary"]["supervised_scores"] is False
        reset_sessions()
        pytest.skip("Persisted IEEE artifact is not present.")
    assert analyzed["summary"]["supervised_scores"] is True
    overlay = analyzed["model_overlay"]
    assert overlay["provenance"] == "MODEL PREDICTION · USER DATASET"
    assert overlay["retrained"] is False
    assert overlay["features_fabricated"] is False
    assert overlay["chunked"] is True
    assert overlay["scored_rows"] == 8
    evaluation = analyzed["evaluation"]
    assert evaluation["used_as_detector_input"] is False
    assert evaluation["retrained_on_upload"] is False
    assert evaluation["provenance"] == "USER-PROVIDED GROUND TRUTH"
    reset_sessions()


def test_large_partial_dataset_is_investigated_chunk_by_chunk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from evaluation.custom_data import detect as detect_mod
    from evaluation.custom_data.detect import detect_from_path
    from evaluation.custom_data.stream import iter_mapped_chunks

    path = tmp_path / "partial-chunks.csv"
    path.write_text(_minimal_csv(), encoding="utf-8")
    seen = {"chunks": 0}
    real = iter_mapped_chunks

    def _counting(source, mapping, chunksize=10_000):
        for chunk in real(source, mapping, chunksize=8):
            seen["chunks"] += 1
            assert len(chunk) <= 8
            yield chunk

    monkeypatch.setattr(detect_mod, "iter_mapped_chunks", _counting)
    anomalies, summary, _labels = detect_from_path(
        path,
        {"transaction_id": "transaction_id", "amount": "amount", "timestamp": "timestamp"},
    )
    assert summary["chunked"] is True
    assert summary["labels_used_as_detector_input"] is False
    assert summary["hourly_context"]
    assert "transaction_count" in summary["hourly_context"][0]
    assert seen["chunks"] >= 2
    assert summary["transactions_analyzed"] > 50
    assert anomalies


def test_large_ready_dataset_is_scored_chunk_by_chunk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from evaluation.custom_data import score as score_mod
    from evaluation.custom_data.score import score_compatible_path
    from evaluation.custom_data.stream import iter_csv_chunks
    from models.ieee_fraud import JOBLIB_NAME, MODEL_DIR

    if not (MODEL_DIR / JOBLIB_NAME).is_file():
        pytest.skip("Persisted IEEE artifact is not present.")
    path = tmp_path / "ready-chunks.csv"
    path.write_text(_ieee_ready_csv(7), encoding="utf-8")
    seen = {"chunks": 0, "max_rows": 0}
    real = iter_csv_chunks

    def _counting(source, chunksize=10_000, usecols=None):
        for chunk in real(source, chunksize=2, usecols=usecols):
            seen["chunks"] += 1
            seen["max_rows"] = max(seen["max_rows"], int(len(chunk)))
            yield chunk

    monkeypatch.setattr(score_mod, "SCORE_CHUNK_ROWS", 2)
    monkeypatch.setattr(score_mod, "iter_csv_chunks", _counting)
    scored = score_compatible_path(
        path,
        [
            "TransactionID",
            "TransactionDT",
            "TransactionAmt",
            "ProductCD",
            "card1",
            "C1",
            "C2",
            "C3",
            "V1",
            "V2",
            "V3",
            "addr1",
            "isFraud",
        ],
        label_column="isFraud",
    )
    assert scored["chunked"] is True
    assert scored["retrained"] is False
    assert scored["provenance"] == "MODEL PREDICTION · USER DATASET"
    assert scored["scored_rows"] == 7
    assert seen["chunks"] >= 3
    assert seen["max_rows"] <= 2
    assert scored["threshold"] == 0.5


def test_missing_required_fields_block_analysis() -> None:
    from app.services.custom_world import analyze_session, confirm_mapping, create_session, reset_sessions

    reset_sessions()
    payload = create_session("partial-missing.csv", _minimal_csv().encode("utf-8"))
    confirmed = confirm_mapping(payload["session_id"], {"transaction_id": "transaction_id"})
    assert confirmed["mapping_validation"]["ready"] is False
    missing = {item["target"] for item in confirmed["mapping_validation"]["missing"]}
    assert missing == {"amount", "timestamp"}
    with pytest.raises(Exception, match="amount"):
        analyze_session(payload["session_id"])
    reset_sessions()


def test_incorrect_amount_mapping_does_not_emit_nan() -> None:
    from evaluation.custom_data.detect import detect_anomalies, build_evidence

    frame = pd.DataFrame(
        {
            "amount": ["visa", "mastercard", "visa"],
            "timestamp": ["2026-03-01 10:00:00", "2026-03-01 11:00:00", "2026-03-01 12:00:00"],
        }
    )
    anomalies, _summary = detect_anomalies(frame)
    dumped = str(anomalies)
    assert "nan" not in dumped.lower()
    for item in anomalies:
        evidence = build_evidence(item)
        amount = (evidence["live_evidence"].get("amount") or {}).get("value")
        assert amount is None or amount == amount
        assert str(amount).lower() != "nan"


def test_transactiondt_does_not_become_1970() -> None:
    from evaluation.custom_data.detect import detect_anomalies, build_evidence
    from evaluation.custom_data.investigate import deterministic_analysis

    amounts = [10.0] * 20 + [12.0] * 20 + [400.0] * 20
    stamps = [10_000] * 20 + [14_000] * 20 + [18_000] * 20
    frame = pd.DataFrame({"amount": amounts, "timestamp": stamps})
    anomalies, _summary = detect_anomalies(frame)
    dumped = str(anomalies)
    assert "1970" not in dumped
    assert anomalies
    assert any(item.get("time_kind") == "relative_elapsed" for item in anomalies)
    for item in anomalies:
        assert "1970" not in str(item.get("time_display"))
        assert not str(item.get("hour_start", "")).startswith("1970")
        evidence = build_evidence(item)
        report = deterministic_analysis(evidence)
        assert "1970" not in report["summary"]
        assert "nan" not in report["summary"].lower()


def test_custom_high_risk_count_does_not_select_action() -> None:
    """Classifier high_risk_count cannot independently change the BYOD recommended action."""
    reset_store()
    quiet_high = decide_from_investigation(
        {"anomaly_id": "cda-quiet", "signals": [], "live_score": 1.0},
        {
            "anomaly_id": "cda-quiet",
            "hour_start": "2026-03-02T04:00:00",
            "signals": [],
            "model_prediction": {"high_risk_count": 4, "label": "MODEL PREDICTION · USER DATASET"},
        },
        {"summary": "quiet"},
    )
    quiet_zero = decide_from_investigation(
        {"anomaly_id": "cda-quiet", "signals": [], "live_score": 1.0},
        {
            "anomaly_id": "cda-quiet",
            "hour_start": "2026-03-02T04:00:00",
            "signals": [],
            "model_prediction": {"high_risk_count": 0},
        },
        {"summary": "quiet"},
    )
    assert quiet_high["recommended_action"]["type"] == quiet_zero["recommended_action"]["type"] == "monitor_only"
    assert "model_high_risk_count" not in quiet_high["live_inputs"]
    assert quiet_high["supporting_classifier_evidence"]["used_for_action_selection"] is False
    assert quiet_high["delayed_ground_truth_used"] is False
    amount_high = decide_from_investigation(
        {"anomaly_id": "cda-amount", "signals": ["elevated transaction amount"], "live_score": 4.0},
        {
            "anomaly_id": "cda-amount",
            "hour_start": "2026-03-02T04:00:00",
            "signals": ["elevated transaction amount"],
            "model_prediction": {"high_risk_count": 12},
        },
        {"summary": "amount"},
    )
    amount_zero = decide_from_investigation(
        {"anomaly_id": "cda-amount", "signals": ["elevated transaction amount"], "live_score": 4.0},
        {
            "anomaly_id": "cda-amount",
            "hour_start": "2026-03-02T04:00:00",
            "signals": ["elevated transaction amount"],
            "model_prediction": {"high_risk_count": 0},
        },
        {"summary": "amount"},
    )
    assert (
        amount_high["recommended_action"]["type"]
        == amount_zero["recommended_action"]["type"]
        == "flag_for_human_review"
    )
    volume = decide_from_investigation(
        {"anomaly_id": "cda-volume", "signals": ["elevated transaction volume"], "live_score": 3.0},
        {
            "anomaly_id": "cda-volume",
            "hour_start": "2026-03-02T04:00:00",
            "signals": ["elevated transaction volume"],
            "model_prediction": {"high_risk_count": 8},
        },
        {"summary": "volume"},
    )
    assert volume["recommended_action"]["type"] == "review_time_window"


def test_custom_user_labels_are_evaluation_only_on_evidence() -> None:
    from evaluation.custom_data.detect import build_evidence

    overlay = {
        "label": "USER-PROVIDED GROUND TRUTH",
        "fraud_count": 2,
        "fraud_rate": 0.1,
        "used_as_detector_input": False,
        "used_as_model_feature": False,
        "note": "USER-PROVIDED GROUND TRUTH is evaluation only. It is not a model feature and not the system's fraud decision.",
    }
    evidence = build_evidence(
        {
            "anomaly_id": "cda-labelled",
            "kind": "Temporal anomaly",
            "hour_start": "2026-03-02T04:00:00",
            "time_kind": "calendar",
            "transactions": 20,
            "signals": ["elevated transaction volume"],
        },
        label_overlay=overlay,
    )
    assert evidence["evaluation_overlay"]["label"] == "USER-PROVIDED GROUND TRUTH"
    assert evidence["evaluation_overlay"]["used_as_detector_input"] is False
    assert evidence["evaluation_overlay"]["used_as_model_feature"] is False
    assert "evaluation only" in evidence["evaluation_overlay"]["note"]
