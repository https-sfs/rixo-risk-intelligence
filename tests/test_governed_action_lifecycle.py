"""Governed action lifecycle across a fresh Vercel-style process.

These tests wipe process-local stores and /tmp sidecars between steps so they
fail on the old in-memory persistence model and pass when the signed ticket
reconstructs the same world-scoped action records.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from agent.actions.service import reset_default_store
from app.governance_ticket import TICKET_HEADER
from app.main import app
from evaluation.custom_data.governance import reset_store as reset_custom
from evaluation.real_data.governance import reset_store as reset_ieee
from evaluation.recent_data.governance import reset_store as reset_january

SPIKE_ID = "spk-coord-20260118-02"
JANUARY_ANOMALY = "rct-20260104-20"


def _client() -> TestClient:
    return TestClient(app)


def _ticket(response) -> str:
    return response.headers.get(TICKET_HEADER) or response.json().get("governance_ticket") or ""


def _headers(ticket: str) -> dict[str, str]:
    return {TICKET_HEADER: ticket} if ticket else {}


def _fresh_invocation() -> None:
    """Simulate a new Vercel function instance: empty RAM, no shared /tmp SQLite."""
    reset_default_store()
    reset_ieee()
    reset_january()
    reset_custom()
    from app.persistence import attach_default_stores
    from app.services.custom_world import reset_sessions

    reset_sessions()
    attach_default_stores(None)


def _minimal_csv() -> str:
    rows = ["transaction_id,amount,timestamp"]
    for day in range(1, 4):
        for hour in range(8):
            count = 80 if day == 2 and hour == 4 else 12
            amount = 400 if day == 2 and hour == 4 else 20
            for index in range(count):
                rows.append(f"txn-{day}-{hour}-{index},{amount},2026-03-{day:02d} {hour:02d}:15:00")
    return "\n".join(rows) + "\n"


def test_synthetic_unknown_without_ticket_after_process_reset() -> None:
    client = _client()
    _fresh_invocation()
    report = client.get(f"/api/spikes/{SPIKE_ID}/investigation").json()["report"]
    created = client.post("/api/actions/propose", json=report)
    assert created.status_code == 200
    action_id = created.json()["action_id"]
    _fresh_invocation()
    missing = client.post(
        f"/api/actions/{action_id}/approve",
        json={"approved_by": "analyst"},
    )
    assert missing.status_code == 404
    assert f"Unknown action_id: {action_id}" in missing.json()["detail"]


def test_synthetic_lifecycle_survives_fresh_vercel_instance() -> None:
    client = _client()
    _fresh_invocation()
    report = client.get(f"/api/spikes/{SPIKE_ID}/investigation").json()["report"]
    created = client.post("/api/actions/propose", json=report)
    assert created.status_code == 200
    action_id = created.json()["action_id"]
    ticket = _ticket(created)
    assert ticket
    assert action_id.startswith("act-")

    _fresh_invocation()
    retrieved = client.get(f"/api/actions/{action_id}", headers=_headers(ticket))
    assert retrieved.status_code == 200, retrieved.text
    assert retrieved.json()["proposal"]["action_id"] == action_id
    ticket = _ticket(retrieved) or ticket

    _fresh_invocation()
    approved = client.post(
        f"/api/actions/{action_id}/approve",
        json={"approved_by": "analyst"},
        headers=_headers(ticket),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved"] is True
    ticket = _ticket(approved) or ticket

    _fresh_invocation()
    simulated = client.post(f"/api/actions/{action_id}/execute", headers=_headers(ticket))
    assert simulated.status_code == 200, simulated.text
    assert simulated.json()["simulated"] is True
    ticket = _ticket(simulated) or ticket

    _fresh_invocation()
    trail = client.get(f"/api/audit?action_id={action_id}", headers=_headers(ticket))
    assert trail.status_code == 200, trail.text
    kinds = {event.get("event_type") or event.get("kind") for event in trail.json()["events"]}
    assert "ACTION_APPROVED" in kinds
    assert "ACTION_SIMULATED" in kinds


def test_january_unknown_without_ticket_after_process_reset() -> None:
    client = _client()
    _fresh_invocation()
    opened = client.get(f"/api/recent/anomalies/{JANUARY_ANOMALY}")
    if opened.status_code != 200:
        return
    created = client.post("/api/recent/actions/propose", json={"anomaly_id": JANUARY_ANOMALY})
    assert created.status_code == 200
    action_id = created.json()["action_id"]
    _fresh_invocation()
    missing = client.post(
        f"/api/recent/actions/{action_id}/approve",
        json={"approved_by": "analyst"},
    )
    assert missing.status_code == 404
    assert f"Unknown January 2026 action_id: {action_id}" in missing.json()["detail"]


def test_january_lifecycle_survives_fresh_vercel_instance() -> None:
    client = _client()
    _fresh_invocation()
    opened = client.get(f"/api/recent/anomalies/{JANUARY_ANOMALY}")
    if opened.status_code != 200:
        return
    created = client.post("/api/recent/actions/propose", json={"anomaly_id": JANUARY_ANOMALY})
    assert created.status_code == 200
    action_id = created.json()["action_id"]
    ticket = _ticket(created)
    assert ticket
    assert action_id.startswith("nact-")

    _fresh_invocation()
    retrieved = client.get(f"/api/recent/actions/{action_id}", headers=_headers(ticket))
    assert retrieved.status_code == 200, retrieved.text
    assert retrieved.json()["proposal"]["action_id"] == action_id
    ticket = _ticket(retrieved) or ticket

    _fresh_invocation()
    decided = client.get(
        f"/api/recent/anomalies/{JANUARY_ANOMALY}",
        headers=_headers(ticket),
    )
    assert decided.status_code == 200
    assert decided.json()["investigation_state"]["proposal"]["action_id"] == action_id

    _fresh_invocation()
    approved = client.post(
        f"/api/recent/actions/{action_id}/approve",
        json={"approved_by": "analyst"},
        headers=_headers(ticket),
    )
    assert approved.status_code == 200, approved.text
    ticket = _ticket(approved) or ticket

    _fresh_invocation()
    simulated = client.post(
        f"/api/recent/actions/{action_id}/simulate",
        headers=_headers(ticket),
    )
    assert simulated.status_code == 200, simulated.text
    assert simulated.json()["simulated"] is True
    ticket = _ticket(simulated) or ticket

    _fresh_invocation()
    trail = client.get(
        f"/api/recent/audit?anomaly_id={JANUARY_ANOMALY}",
        headers=_headers(ticket),
    )
    assert trail.status_code == 200
    kinds = {event["kind"] for event in trail.json()["events"]}
    assert "RECENT_ACTION_APPROVED" in kinds
    assert "RECENT_ACTION_SIMULATED" in kinds


def test_byod_unknown_without_ticket_after_process_reset() -> None:
    client = _client()
    _fresh_invocation()
    uploaded = client.post(
        "/api/custom/upload",
        content=_minimal_csv().encode("utf-8"),
        headers={"X-Filename": "merchant.csv"},
    )
    assert uploaded.status_code == 200
    session_id = uploaded.json()["session_id"]
    ticket = _ticket(uploaded)
    client.post(
        f"/api/custom/sessions/{session_id}/mapping",
        json={"mapping": {"transaction_id": "transaction_id", "amount": "amount", "timestamp": "timestamp"}},
        headers=_headers(ticket),
    )
    analyzed = client.post(
        f"/api/custom/sessions/{session_id}/analyze",
        headers=_headers(ticket),
    )
    assert analyzed.status_code == 200
    anomaly_id = analyzed.json()["anomalies"][0]["anomaly_id"]
    created = client.post(
        f"/api/custom/sessions/{session_id}/actions/propose",
        json={"anomaly_id": anomaly_id},
        headers=_headers(_ticket(analyzed) or ticket),
    )
    assert created.status_code == 200
    _fresh_invocation()
    missing = client.get(f"/api/custom/sessions/{session_id}")
    assert missing.status_code == 404
    assert "unknown or expired" in missing.json()["detail"].lower()


def test_byod_lifecycle_survives_fresh_vercel_instance() -> None:
    client = _client()
    _fresh_invocation()
    uploaded = client.post(
        "/api/custom/upload",
        content=_minimal_csv().encode("utf-8"),
        headers={"X-Filename": "merchant.csv"},
    )
    assert uploaded.status_code == 200
    session_id = uploaded.json()["session_id"]
    ticket = _ticket(uploaded)
    mapped = client.post(
        f"/api/custom/sessions/{session_id}/mapping",
        json={"mapping": {"transaction_id": "transaction_id", "amount": "amount", "timestamp": "timestamp"}},
        headers=_headers(ticket),
    )
    assert mapped.status_code == 200
    ticket = _ticket(mapped) or ticket
    analyzed = client.post(
        f"/api/custom/sessions/{session_id}/analyze",
        headers=_headers(ticket),
    )
    assert analyzed.status_code == 200
    ticket = _ticket(analyzed) or ticket
    anomaly_id = analyzed.json()["anomalies"][0]["anomaly_id"]

    _fresh_invocation()
    created = client.post(
        f"/api/custom/sessions/{session_id}/actions/propose",
        json={"anomaly_id": anomaly_id},
        headers=_headers(ticket),
    )
    assert created.status_code == 200, created.text
    action_id = created.json()["action_id"]
    assert action_id.startswith("cact-")
    ticket = _ticket(created) or ticket

    _fresh_invocation()
    retrieved = client.get(
        f"/api/custom/sessions/{session_id}/actions/{action_id}",
        headers=_headers(ticket),
    )
    assert retrieved.status_code == 200, retrieved.text
    assert retrieved.json()["proposal"]["action_id"] == action_id
    ticket = _ticket(retrieved) or ticket

    _fresh_invocation()
    decided = client.get(
        f"/api/custom/sessions/{session_id}/anomalies/{anomaly_id}",
        headers=_headers(ticket),
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["investigation_state"]["proposal"]["action_id"] == action_id

    _fresh_invocation()
    approved = client.post(
        f"/api/custom/sessions/{session_id}/actions/{action_id}/approve",
        json={"approved_by": "analyst"},
        headers=_headers(ticket),
    )
    assert approved.status_code == 200, approved.text
    ticket = _ticket(approved) or ticket

    _fresh_invocation()
    simulated = client.post(
        f"/api/custom/sessions/{session_id}/actions/{action_id}/simulate",
        headers=_headers(ticket),
    )
    assert simulated.status_code == 200, simulated.text
    assert simulated.json()["simulated"] is True
    ticket = _ticket(simulated) or ticket

    _fresh_invocation()
    trail = client.get(
        f"/api/custom/sessions/{session_id}/audit?anomaly_id={anomaly_id}",
        headers=_headers(ticket),
    )
    assert trail.status_code == 200, trail.text
    kinds = {event["kind"] for event in trail.json()["events"]}
    assert "CUSTOM_ACTION_APPROVED" in kinds
    assert "CUSTOM_ACTION_SIMULATED" in kinds


def _csv_with_two_spikes() -> str:
    rows = ["transaction_id,amount,timestamp"]
    for day in range(1, 4):
        for hour in range(8):
            count = 80 if day == 2 and hour in {3, 4} else 12
            amount = 400 if day == 2 and hour in {3, 4} else 20
            for index in range(count):
                rows.append(f"txn-{day}-{hour}-{index},{amount},2026-03-{day:02d} {hour:02d}:15:00")
    return "\n".join(rows) + "\n"


def test_byod_anomaly_investigation_survives_fresh_invocation_for_multiple_anomalies() -> None:
    from app.config import MAX_GOVERNANCE_TICKET_CHARS

    client = _client()
    _fresh_invocation()
    uploaded = client.post(
        "/api/custom/upload",
        content=_csv_with_two_spikes().encode("utf-8"),
        headers={"X-Filename": "two-spikes.csv"},
    )
    assert uploaded.status_code == 200
    session_id = uploaded.json()["session_id"]
    ticket = _ticket(uploaded)
    mapped = client.post(
        f"/api/custom/sessions/{session_id}/mapping",
        json={"mapping": {"transaction_id": "transaction_id", "amount": "amount", "timestamp": "timestamp"}},
        headers=_headers(ticket),
    )
    assert mapped.status_code == 200
    ticket = _ticket(mapped) or ticket
    analyzed = client.post(
        f"/api/custom/sessions/{session_id}/analyze",
        headers=_headers(ticket),
    )
    assert analyzed.status_code == 200, analyzed.text
    ticket = _ticket(analyzed)
    assert ticket
    assert len(ticket) <= MAX_GOVERNANCE_TICKET_CHARS
    anomalies = analyzed.json()["anomalies"]
    assert len(anomalies) >= 2
    ids = [str(item["anomaly_id"]) for item in anomalies[:2]]

    for anomaly_id in ids:
        _fresh_invocation()
        detail = client.get(
            f"/api/custom/sessions/{session_id}/anomalies/{anomaly_id}",
            headers=_headers(ticket),
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["anomaly"]["anomaly_id"] == anomaly_id
        assert detail.json()["evidence"]
        ticket = _ticket(detail) or ticket
        assert "Failed to fetch" not in (detail.text or "")

        _fresh_invocation()
        investigation = client.get(
            f"/api/custom/sessions/{session_id}/anomalies/{anomaly_id}/investigation?provider=auto",
            headers=_headers(ticket),
        )
        assert investigation.status_code == 200, investigation.text
        assert investigation.json().get("summary") or investigation.json().get("provider")
        ticket = _ticket(investigation) or ticket

    first = ids[0]
    _fresh_invocation()
    proposed = client.post(
        f"/api/custom/sessions/{session_id}/actions/propose",
        json={"anomaly_id": first},
        headers=_headers(ticket),
    )
    assert proposed.status_code == 200, proposed.text
    action_id = proposed.json()["action_id"]
    ticket = _ticket(proposed) or ticket
    _fresh_invocation()
    approved = client.post(
        f"/api/custom/sessions/{session_id}/actions/{action_id}/approve",
        json={"approved_by": "analyst"},
        headers=_headers(ticket),
    )
    assert approved.status_code == 200
    ticket = _ticket(approved) or ticket
    _fresh_invocation()
    simulated = client.post(
        f"/api/custom/sessions/{session_id}/actions/{action_id}/simulate",
        headers=_headers(ticket),
    )
    assert simulated.status_code == 200
    ticket = _ticket(simulated) or ticket
    _fresh_invocation()
    trail = client.get(
        f"/api/custom/sessions/{session_id}/audit?anomaly_id={first}",
        headers=_headers(ticket),
    )
    kinds = {event["kind"] for event in trail.json()["events"]}
    assert "CUSTOM_ACTION_SIMULATED" in kinds


def test_byod_ticket_omits_hourly_context_so_headers_stay_small() -> None:
    from app.config import MAX_GOVERNANCE_TICKET_CHARS
    from app.governance_ticket import issue_ticket
    from app.services.custom_world import CustomSession, _SESSIONS, session_snapshot_for_ticket

    session = CustomSession(
        session_id="cxs-fat-hourly",
        filename="fat.csv",
        csv_path="",
        file_bytes=20_000_000,
        columns=["transaction_id", "amount", "timestamp"],
        inspection={"column_count": 3, "sample_rows": [["x"] * 50 for _ in range(20)]},
        mapping_proposals=[{"field": "amount", "column": "amount"}],
        mapping={"transaction_id": "transaction_id", "amount": "amount", "timestamp": "timestamp"},
        compatibility={"status": "partial"},
        anomalies=[
            {
                "anomaly_id": "cda-20260302-04",
                "kind": "Amount concentration",
                "hour_start": "2026-03-02 04:00:00",
                "transactions": 80,
                "amount": 400,
                "signals": ["elevated transaction amount"],
            }
        ],
        hourly=[{"hour_start": f"h-{index}", "transaction_count": 12} for index in range(800)],
        summary={
            "transactions_analyzed": 20000,
            "hourly_context": [{"hour_start": f"h-{index}", "transaction_count": 12} for index in range(800)],
        },
    )
    _SESSIONS[session.session_id] = session
    snapshot = session_snapshot_for_ticket(session.session_id)
    assert snapshot is not None
    assert snapshot["hourly"] == []
    assert "hourly_context" not in (snapshot.get("summary") or {})
    token = issue_ticket({"sessions": {session.session_id: snapshot}})
    assert len(token) <= MAX_GOVERNANCE_TICKET_CHARS
    _SESSIONS.pop(session.session_id, None)


def test_worlds_stay_isolated_across_tickets() -> None:
    client = _client()
    _fresh_invocation()
    report = client.get(f"/api/spikes/{SPIKE_ID}/investigation").json()["report"]
    synthetic = client.post("/api/actions/propose", json=report)
    synthetic_id = synthetic.json()["action_id"]
    synthetic_ticket = _ticket(synthetic)

    opened = client.get(f"/api/recent/anomalies/{JANUARY_ANOMALY}")
    if opened.status_code != 200:
        return
    january = client.post("/api/recent/actions/propose", json={"anomaly_id": JANUARY_ANOMALY})
    january_id = january.json()["action_id"]

    _fresh_invocation()
    crossed = client.post(
        f"/api/recent/actions/{synthetic_id}/approve",
        json={"approved_by": "analyst"},
        headers=_headers(synthetic_ticket),
    )
    assert crossed.status_code == 404
    assert "Unknown January 2026 action_id" in crossed.json()["detail"]

    _fresh_invocation()
    still = client.get(f"/api/actions/{january_id}", headers=_headers(synthetic_ticket))
    assert still.status_code == 404
