from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from agent.actions.errors import ActionError
from agent.actions.service import approve_action, execute_action, get_audit_trail, propose_from_report
from agent.actions.store import ActionStore
from agent.investigate import investigate_spike
from app.config import settings
from app.integrations.razorpay_adapter import (
    RazorpayLiveBlockedError,
    RazorpayPaymentAdapter,
    sanitize_public,
)
from app.integrations.sandbox_payments import apply_after_approval, attach_to_execution
from evaluation.recent_data.governance import RecentActionStore, RecentGovernanceError
from evaluation.recent_data.governance import approve_action as recent_approve
from evaluation.recent_data.governance import propose_action as recent_propose
from evaluation.recent_data.governance import simulate_action as recent_simulate


class FakeHttp:
    def __init__(self, status_code: int = 200, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.payload = payload or {
            "id": "order_test_abc",
            "status": "created",
            "amount": 100,
            "currency": "INR",
            "receipt": "act-test",
            "key_secret": "should-never-leak",
        }
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        auth: tuple[str, str] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        self.calls.append(
            {"method": method, "url": url, "auth": auth, "json": json, "timeout": timeout}
        )
        return httpx.Response(self.status_code, json=self.payload)


def _test_adapter(http: FakeHttp | None = None) -> RazorpayPaymentAdapter:
    return RazorpayPaymentAdapter(
        key_id="rzp_test_key",
        key_secret="test_secret_value",
        mode="test",
        http=http,
    )


def test_test_mode_configuration() -> None:
    adapter = RazorpayPaymentAdapter(key_id="rzp_test_key", key_secret="secret", mode="test")
    status = adapter.public_status()
    assert status["environment"] == "test"
    assert status["mode"] == "test"
    assert status["available"] is True
    assert status["live_blocked"] is False


def test_missing_credentials_are_unavailable() -> None:
    adapter = RazorpayPaymentAdapter(key_id="", key_secret="", mode="test")
    result = adapter.simulate_test_action(
        action_id="act-1",
        case_id="rct-1",
        action_type="review",
        scope="window",
    )
    assert result["status"] == "unavailable"
    assert result["reason"] == "configuration_missing"
    assert "Razorpay" in result["message"]
    assert "test_secret" not in json.dumps(result)


def test_live_production_execution_is_blocked() -> None:
    live_mode = RazorpayPaymentAdapter(key_id="rzp_test_key", key_secret="secret", mode="live")
    with pytest.raises(RazorpayLiveBlockedError, match="TEST MODE"):
        live_mode.simulate_test_action(
            action_id="act-1", case_id="rct-1", action_type="review", scope="window"
        )
    live_key = RazorpayPaymentAdapter(key_id="rzp_live_abc", key_secret="secret", mode="test")
    with pytest.raises(RazorpayLiveBlockedError):
        live_key.create_test_order(receipt="act-1")


def test_adapter_request_construction() -> None:
    http = FakeHttp()
    adapter = _test_adapter(http)
    adapter.create_test_order(receipt="act-order-1", notes={"action_id": "act-order-1"})
    assert len(http.calls) == 1
    call = http.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://api.razorpay.com/v1/orders"
    assert call["auth"] == ("rzp_test_key", "test_secret_value")
    body = call["json"]
    assert body["amount"] == 100
    assert body["currency"] == "INR"
    assert body["payment_capture"] == 0
    assert body["notes"]["environment"] == "test"
    assert body["notes"]["not_a_live_payment"] == "true"


def test_sanitized_response_strips_secrets() -> None:
    raw = {
        "id": "order_test_abc",
        "key_secret": "super-secret",
        "razorpay_key_secret": "also-secret",
        "authorization": "Basic abc",
        "nested": {"secret": "nope", "status": "created"},
    }
    cleaned = sanitize_public(raw)
    dumped = json.dumps(cleaned)
    assert "super-secret" not in dumped
    assert "also-secret" not in dumped
    assert "Basic abc" not in dumped
    assert cleaned["id"] == "order_test_abc"
    http = FakeHttp()
    order = _test_adapter(http).create_test_order(receipt="act-1")
    assert order["test_order_id"] == "order_test_abc"
    assert "key_secret" not in order
    assert order["environment"] == "test"
    assert order["not_a_live_payment"] is True


def test_approval_gate_and_no_adapter_before_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def boom(**kwargs: Any) -> dict[str, Any]:
        called.append(str(kwargs.get("action_id")))
        raise AssertionError("adapter must not run before approval")

    monkeypatch.setattr("app.integrations.sandbox_payments.apply_after_approval", boom)
    store = RecentActionStore()
    proposal = recent_propose(
        {
            "anomaly_id": "rct-gate",
            "verdict": "review_recommended",
            "recommended_action": {
                "type": "flag_for_human_review",
                "scope": "January window",
                "reason": "test",
            },
            "human_approval_required": True,
            "delayed_ground_truth_used": False,
            "source_model_used": False,
            "ieee_model_used": False,
            "reasoning_provider": "deterministic",
        },
        store=store,
    )
    with pytest.raises(RecentGovernanceError, match="not been explicitly approved"):
        recent_simulate(proposal["action_id"], store=store)
    assert called == []

    store_syn = ActionStore()
    syn = propose_from_report(investigate_spike("spk-coord-20260118-02")["report"], store=store_syn)
    with pytest.raises(ActionError, match="not been explicitly approved"):
        execute_action(syn.action_id, store=store_syn)
    assert called == []


def test_successful_test_simulation_and_audit() -> None:
    http = FakeHttp()
    adapter = _test_adapter(http)
    store = RecentActionStore()
    proposal = recent_propose(
        {
            "anomaly_id": "rct-ok",
            "verdict": "review_recommended",
            "recommended_action": {
                "type": "flag_for_human_review",
                "scope": "January window",
                "reason": "test",
            },
            "human_approval_required": True,
            "delayed_ground_truth_used": False,
            "source_model_used": False,
            "ieee_model_used": False,
            "reasoning_provider": "deterministic",
        },
        store=store,
    )
    recent_approve(proposal["action_id"], approved_by="analyst", store=store)
    monkey_adapter = adapter

    from app.integrations import sandbox_payments as sandbox

    original = sandbox.get_adapter
    sandbox.get_adapter = lambda http=None: monkey_adapter  # type: ignore[assignment]
    try:
        execution = recent_simulate(proposal["action_id"], store=store)
    finally:
        sandbox.get_adapter = original  # type: ignore[assignment]

    assert execution["simulated"] is True
    assert execution["razorpay_test"]["status"] == "completed"
    assert execution["razorpay_test"]["test_order_id"] == "order_test_abc"
    assert "Razorpay test simulation completed" in execution["result"]
    kinds = [event["kind"] for event in store.audit]
    assert "RECENT_ACTION_APPROVED" in kinds
    assert "RECENT_ACTION_SIMULATED" in kinds
    assert "RECENT_RAZORPAY_TEST_SIMULATED" in kinds
    event = next(item for item in store.audit if item["kind"] == "RECENT_RAZORPAY_TEST_SIMULATED")
    dumped = json.dumps(event)
    assert "test_secret_value" not in dumped
    assert event["details"]["environment"] == "test"
    assert event["details"]["test_order_id"] == "order_test_abc"


def test_failed_test_simulation_is_not_successful() -> None:
    http = FakeHttp(status_code=502, payload={"error": {"description": "unavailable"}})
    store = RecentActionStore()
    proposal = recent_propose(
        {
            "anomaly_id": "rct-fail",
            "verdict": "review_recommended",
            "recommended_action": {
                "type": "flag_for_human_review",
                "scope": "January window",
                "reason": "test",
            },
            "human_approval_required": True,
            "delayed_ground_truth_used": False,
            "source_model_used": False,
            "ieee_model_used": False,
            "reasoning_provider": "deterministic",
        },
        store=store,
    )
    recent_approve(proposal["action_id"], approved_by="analyst", store=store)
    from app.integrations import sandbox_payments as sandbox

    original = sandbox.get_adapter
    failing = _test_adapter(http)
    sandbox.get_adapter = lambda http=None, adapter=failing: adapter  # type: ignore[assignment]
    try:
        execution = recent_simulate(proposal["action_id"], store=store)
    finally:
        sandbox.get_adapter = original  # type: ignore[assignment]

    assert execution["simulated"] is False
    assert execution["status"] == "simulation_failed"
    assert store.proposals[proposal["action_id"]]["status"] == "approved"
    kinds = [event["kind"] for event in store.audit]
    assert "RECENT_ACTION_SIMULATED" not in kinds
    assert "RECENT_RAZORPAY_TEST_FAILED" in kinds


def test_secrets_never_appear_in_api_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "super_secret_do_not_leak")
    monkeypatch.setattr(settings, "razorpay_mode", "test")
    payload = apply_after_approval(
        action_id="act-1",
        case_id="rct-1",
        action_type="review",
        scope="window",
        adapter=_test_adapter(FakeHttp()),
    )
    dumped = json.dumps(payload)
    assert "super_secret_do_not_leak" not in dumped
    assert "test_secret_value" not in dumped
    assert "key_secret" not in dumped
    execution = attach_to_execution(
        {"result": "Simulated review for window.", "simulated": True, "status": "simulated"},
        payload,
    )
    assert "super_secret" not in json.dumps(execution)


def test_sandbox_status_endpoint_hides_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", "super_secret_do_not_leak")
    monkeypatch.setattr(settings, "razorpay_mode", "test")
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/sandbox/status")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "razorpay"
    assert body["environment"] == "test"
    assert body["configured"] is True
    dumped = json.dumps(body)
    assert "super_secret_do_not_leak" not in dumped
    assert "key_secret" not in dumped


def test_default_missing_credentials_keep_four_world_simulation() -> None:
    store = RecentActionStore()
    proposal = recent_propose(
        {
            "anomaly_id": "rct-default",
            "verdict": "review_recommended",
            "recommended_action": {
                "type": "flag_for_human_review",
                "scope": "January window",
                "reason": "test",
            },
            "human_approval_required": True,
            "delayed_ground_truth_used": False,
            "source_model_used": False,
            "ieee_model_used": False,
            "reasoning_provider": "deterministic",
        },
        store=store,
    )
    recent_approve(proposal["action_id"], approved_by="analyst", store=store)
    execution = recent_simulate(proposal["action_id"], store=store)
    assert execution["simulated"] is True
    assert execution["razorpay_test"]["status"] == "unavailable"
    assert "Razorpay" in execution["result"]
    kinds = [event["kind"] for event in store.audit]
    assert "RECENT_ACTION_SIMULATED" in kinds
    assert "RECENT_RAZORPAY_TEST_SIMULATED" not in kinds

    syn = ActionStore()
    proposal_syn = propose_from_report(investigate_spike("spk-coord-20260118-02")["report"], store=syn)
    approve_action(proposal_syn.action_id, approved_by="analyst", store=syn)
    result = execute_action(proposal_syn.action_id, store=syn)
    assert result.simulated is True
    assert result.verification["sandbox_test"]["status"] == "unavailable"
    kinds_syn = [item["event_type"] for item in get_audit_trail(proposal_syn.action_id, store=syn)]
    assert kinds_syn == [
        "DECISION_RECORDED",
        "ACTION_PROPOSED",
        "ACTION_APPROVED",
        "ACTION_SIMULATED",
        "ACTION_VERIFIED",
    ]
