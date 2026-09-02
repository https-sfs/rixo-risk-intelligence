"""Process-restart durability behind the existing governance stores."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent.actions.service import (
    approve_action,
    execute_action,
    propose_from_report,
    reset_default_store,
)
from agent.actions.store import SYNTHETIC_WORLD, ActionStore
from agent.investigate import investigate_spike
from app.persistence import GovernanceDB
from evaluation.custom_data.governance import store_for as byod_store
from evaluation.real_data.governance import (
    RealActionStore,
    RealGovernanceError,
    approve_action as ieee_approve,
    decide_from_investigation,
    propose_action,
    reset_store as reset_ieee,
    simulate_action as ieee_simulate,
)
from evaluation.recent_data.governance import RecentActionStore, reset_store as reset_january
from models.ieee_fraud import PROVENANCE
from models.ieee_fraud.overlay import IN_SAMPLE_OVERLAY


def _db(path: Path) -> GovernanceDB:
    return GovernanceDB(path / "governance.sqlite")


def _ieee_decision(anomaly_id: str = "rda-24") -> dict:
    signals = ["elevated transaction volume"]
    return decide_from_investigation(
        {
            "anomaly_id": anomaly_id,
            "relative_hour_bucket": 24,
            "live_score": 3.1,
            "signals": signals,
        },
        {
            "anomaly_id": anomaly_id,
            "relative_hour_bucket": 24,
            "live_evidence": {"temporal_anomaly": {"value": {"signals": signals, "live_score": 3.1}}},
            "model_prediction": {
                "label": PROVENANCE,
                "high_risk_count": 2,
                "threshold": 0.5,
                "sample_scope": IN_SAMPLE_OVERLAY,
            },
        },
        {"summary": "hour is anomalous", "provider": "deterministic"},
    )


def test_proposal_survives_commit_and_reopen(tmp_path: Path) -> None:
    db = _db(tmp_path)
    first = RealActionStore(db=db)
    created = propose_action(_ieee_decision(), store=first, idempotency_key="persist-1")
    assert created["status"] == "proposed"
    reopened = RealActionStore(db=GovernanceDB(db.path))
    assert created["action_id"] in reopened.proposals
    assert reopened.proposals[created["action_id"]]["status"] == "proposed"
    assert reopened.idempotency["persist-1"]["action_id"] == created["action_id"]


def test_approval_simulation_and_audit_survive_restart(tmp_path: Path) -> None:
    db = _db(tmp_path)
    store = RealActionStore(db=db)
    proposal = propose_action(_ieee_decision(), store=store, idempotency_key="persist-flow")
    ieee_approve(proposal["action_id"], approved_by="analyst", store=store)
    ieee_simulate(proposal["action_id"], store=store)
    audit_count = len(store.audit)
    kinds = [item["kind"] for item in store.audit]

    reopened = RealActionStore(db=GovernanceDB(db.path))
    restored = reopened.proposals[proposal["action_id"]]
    assert restored["status"] == "simulated"
    assert reopened.approvals[proposal["action_id"]]["approved"] is True
    assert reopened.executions[proposal["action_id"]]["simulated"] is True
    assert len(reopened.audit) == audit_count
    assert [item["kind"] for item in reopened.audit] == kinds


def test_idempotency_replay_and_conflict_after_restart(tmp_path: Path) -> None:
    db = _db(tmp_path)
    store = RealActionStore(db=db)
    first = propose_action(_ieee_decision("rda-24"), store=store, idempotency_key="persist-key")
    reopened = RealActionStore(db=GovernanceDB(db.path))
    replay = propose_action(_ieee_decision("rda-24"), store=reopened, idempotency_key="persist-key")
    assert replay["action_id"] == first["action_id"]
    assert len(reopened.proposals) == 1
    proposed = [item for item in reopened.audit if item["kind"] == "IEEE_ACTION_PROPOSED"]
    assert len(proposed) == 1
    with pytest.raises(RealGovernanceError, match="idempotency-key conflict"):
        propose_action(_ieee_decision("rda-25"), store=reopened, idempotency_key="persist-key")
    assert list(reopened.proposals) == [first["action_id"]]


def test_different_keys_and_missing_key_compatibility(tmp_path: Path) -> None:
    db = _db(tmp_path)
    store = RealActionStore(db=db)
    a = propose_action(_ieee_decision(), store=store, idempotency_key="key-a")
    b = propose_action(_ieee_decision(), store=store, idempotency_key="key-b")
    c = propose_action(_ieee_decision(), store=store)
    d = propose_action(_ieee_decision(), store=store)
    assert len({a["action_id"], b["action_id"], c["action_id"], d["action_id"]}) == 4
    reopened = RealActionStore(db=GovernanceDB(db.path))
    assert len(reopened.proposals) == 4
    assert reopened.idempotency["key-a"]["action_id"] == a["action_id"]
    assert reopened.idempotency["key-b"]["action_id"] == b["action_id"]


def test_cross_world_isolation_on_shared_sqlite(tmp_path: Path) -> None:
    db = _db(tmp_path)
    ieee = RealActionStore(db=db)
    january = RecentActionStore(db=db)
    synthetic = ActionStore(db=db)
    proposal = propose_action(_ieee_decision(), store=ieee, idempotency_key="ieee-only")
    report = investigate_spike("spk-coord-20260118-02")["report"]
    syn = propose_from_report(report, store=synthetic)
    assert proposal["action_id"] not in january.proposals
    assert syn.action_id not in ieee.proposals
    assert proposal["action_id"] not in synthetic.proposals
    assert january.proposals == {}
    assert byod_store("cxs-persist").proposals == {}
    assert "ieee-only" not in getattr(january, "idempotency", {})
    reopened_jan = RecentActionStore(db=GovernanceDB(db.path))
    reopened_ieee = RealActionStore(db=GovernanceDB(db.path))
    assert proposal["action_id"] in reopened_ieee.proposals
    assert proposal["action_id"] not in reopened_jan.proposals
    assert reopened_ieee.proposals[proposal["action_id"]]["world"] == "REAL PUBLIC DATA"
    assert syn.action_id not in reopened_ieee.proposals
    assert SYNTHETIC_WORLD != "REAL PUBLIC DATA"


def test_startup_restore_does_not_simulate_or_call_razorpay(tmp_path: Path) -> None:
    db = _db(tmp_path)
    store = RealActionStore(db=db)
    proposal = propose_action(_ieee_decision(), store=store, idempotency_key="no-side-effect")
    ieee_approve(proposal["action_id"], approved_by="analyst", store=store)
    with patch("app.integrations.sandbox_payments.apply_after_approval") as sandbox:
        reopened = RealActionStore(db=GovernanceDB(db.path))
        sandbox.assert_not_called()
    assert reopened.proposals[proposal["action_id"]]["status"] == "approved"
    assert reopened.executions == {}
    assert "IEEE_ACTION_SIMULATED" not in {item["kind"] for item in reopened.audit}


def test_concurrent_same_key_against_durable_store(tmp_path: Path) -> None:
    db = _db(tmp_path)
    store = RealActionStore(db=db)
    decision = _ieee_decision()

    def _propose() -> dict:
        return propose_action(decision, store=store, idempotency_key="durable-race")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in (pool.submit(_propose), pool.submit(_propose))]
    assert results[0]["action_id"] == results[1]["action_id"]
    assert len(store.proposals) == 1
    reopened = RealActionStore(db=GovernanceDB(db.path))
    assert len(reopened.proposals) == 1


def test_synthetic_state_survives_restart(tmp_path: Path) -> None:
    db = _db(tmp_path)
    store = ActionStore(db=db)
    report = investigate_spike("spk-coord-20260118-02")["report"]
    proposal = propose_from_report(report, store=store)
    approve_action(proposal.action_id, approved_by="analyst", store=store)
    execute_action(proposal.action_id, store=store)
    audit_len = len(store.audit)
    reopened = ActionStore(db=GovernanceDB(db.path))
    restored = reopened.get_proposal(proposal.action_id)
    assert restored is not None
    assert restored.status == "simulated"
    assert reopened.get_approval(proposal.action_id) is not None
    assert reopened.executions[proposal.action_id].simulated is True
    assert len(reopened.audit) == audit_len


def test_reload_does_not_duplicate_audit(tmp_path: Path) -> None:
    db = _db(tmp_path)
    store = RealActionStore(db=db)
    propose_action(_ieee_decision(), store=store, idempotency_key="audit-once")
    first = len(store.audit)
    again = RealActionStore(db=GovernanceDB(db.path))
    propose_action(_ieee_decision(), store=again, idempotency_key="audit-once")
    assert len(again.audit) == first
    third = RealActionStore(db=GovernanceDB(db.path))
    assert len(third.audit) == first


def test_http_rebind_restores_ieee_proposal(tmp_path: Path) -> None:
    from app.main import app
    from evaluation.real_data.governance import bind_store

    reset_ieee()
    reset_january()
    reset_default_store()
    listed = TestClient(app).get("/api/real/anomalies")
    if listed.status_code != 200 or not listed.json().get("anomalies"):
        pytest.skip("IEEE derived artifacts are not available.")
    anomaly_id = listed.json()["anomalies"][0]["anomaly_id"]
    db = _db(tmp_path)
    bind_store(RealActionStore(db=db))
    client = TestClient(app)
    created = client.post(
        "/api/real/actions/propose",
        json={"anomaly_id": anomaly_id, "idempotency_key": "http-persist"},
    )
    assert created.status_code == 200
    action_id = created.json()["action_id"]
    bind_store(RealActionStore(db=GovernanceDB(db.path)))
    replay = client.post(
        "/api/real/actions/propose",
        json={"anomaly_id": anomaly_id, "idempotency_key": "http-persist"},
    )
    assert replay.status_code == 200
    assert replay.json()["action_id"] == action_id
    assert replay.json()["status"] == "proposed"
    blocked = client.post(f"/api/real/actions/{action_id}/simulate")
    assert blocked.status_code == 409
