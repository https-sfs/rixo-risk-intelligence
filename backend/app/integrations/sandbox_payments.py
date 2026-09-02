"""Post-approval sandbox hook. Call only after human approval is recorded."""

from __future__ import annotations

from typing import Any

from app.integrations.razorpay_adapter import (
    RazorpayLiveBlockedError,
    RazorpayPaymentAdapter,
    RazorpayTestError,
    get_adapter,
    sanitize_public,
)

_INTERNAL_RESULT = (
    "No payment was blocked and no merchant account was changed. "
    "No live payment was executed."
)


def apply_after_approval(
    *,
    action_id: str,
    case_id: str,
    action_type: str,
    scope: str,
    adapter: RazorpayPaymentAdapter | None = None,
) -> dict[str, Any]:
    client = adapter or get_adapter()
    try:
        payload = client.simulate_test_action(
            action_id=action_id,
            case_id=case_id,
            action_type=action_type,
            scope=scope,
        )
    except RazorpayLiveBlockedError as exc:
        payload = {
            "status": "blocked",
            "provider": "razorpay",
            "environment": "test",
            "test_only": True,
            "not_a_live_payment": True,
            "reason": "live_execution_blocked",
            "message": str(exc),
        }
    except RazorpayTestError as exc:
        payload = {
            "status": "failed",
            "provider": "razorpay",
            "environment": "test",
            "test_only": True,
            "not_a_live_payment": True,
            "reason": "test_request_failed",
            "message": str(exc),
        }
    return sanitize_public(payload)


def public_status() -> dict[str, Any]:
    return get_adapter().public_status()


def audit_details(payload: dict[str, Any]) -> dict[str, Any]:
    return sanitize_public(
        {
            "provider": payload.get("provider", "razorpay"),
            "environment": payload.get("environment", "test"),
            "test_order_id": payload.get("test_order_id"),
            "order_status": payload.get("order_status"),
            "reason": payload.get("reason"),
            "test_only": True,
            "not_a_live_payment": True,
        }
    )


def attach_to_execution(execution: dict[str, Any], sandbox: dict[str, Any]) -> dict[str, Any]:
    execution["razorpay_test"] = sandbox
    execution["not_a_live_payment_action"] = True
    status = sandbox.get("status")
    if status == "completed":
        execution["simulated"] = True
        execution["status"] = "simulated"
        execution["result"] = f"{execution.get('result', '').rstrip()} Razorpay test simulation completed."
    elif status == "unavailable":
        execution["simulated"] = True
        execution["status"] = "simulated"
        execution["result"] = (
            f"{execution.get('result', '').rstrip()} {sandbox.get('message', '')}".strip()
        )
    else:
        execution["simulated"] = False
        execution["status"] = "simulation_failed"
        execution["result"] = (
            f"Internal simulation was recorded locally, but the Razorpay test simulation did not complete. "
            f"{sandbox.get('message', '')}".strip()
        )
    return execution


def internal_result(action_type: str, scope: str) -> str:
    return f"Simulated {action_type} for {scope}. {_INTERNAL_RESULT}"
