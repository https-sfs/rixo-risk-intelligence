"""Razorpay TEST MODE adapter. Never a live payment executor."""

from __future__ import annotations

import re
from typing import Any, Protocol

import httpx

from app.config import settings

API_BASE = "https://api.razorpay.com/v1"
TEST_ORDER_AMOUNT_PAISE = 100
TEST_CURRENCY = "INR"
SECRET_KEYS = frozenset(
    {
        "key_secret",
        "razorpay_key_secret",
        "secret",
        "authorization",
        "auth",
        "password",
        "api_key",
    }
)


class RazorpayAdapterError(RuntimeError):
    """Adapter-level failure. Never includes credentials."""


class RazorpayLiveBlockedError(RazorpayAdapterError):
    """Live/production Razorpay execution is forbidden."""


class RazorpayTestError(RazorpayAdapterError):
    """TEST MODE request failed."""


class RazorpayHttpClient(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        auth: tuple[str, str] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response: ...


def sanitize_public(payload: Any) -> Any:
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if lowered in SECRET_KEYS or "secret" in lowered or lowered.endswith("_key"):
                continue
            cleaned[str(key)] = sanitize_public(value)
        return cleaned
    if isinstance(payload, list):
        return [sanitize_public(item) for item in payload]
    if isinstance(payload, str) and re.search(r"sk_live|rzp_live|key_secret", payload, re.I):
        return "[redacted]"
    return payload


class RazorpayPaymentAdapter:
    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        mode: str | None = None,
        http: RazorpayHttpClient | None = None,
    ) -> None:
        self.key_id = (key_id if key_id is not None else settings.razorpay_key_id).strip()
        self.key_secret = (key_secret if key_secret is not None else settings.razorpay_key_secret).strip()
        self.mode = (mode if mode is not None else settings.razorpay_mode).strip().lower() or "test"
        self.http = http

    @property
    def configured(self) -> bool:
        return bool(self.key_id and self.key_secret)

    def public_status(self) -> dict[str, Any]:
        return {
            "provider": "razorpay",
            "environment": "test",
            "mode": self.mode,
            "configured": self.configured,
            "available": self.configured and self.mode == "test" and not self._looks_live(),
            "live_blocked": self._looks_live() or self.mode != "test",
        }

    def _looks_live(self) -> bool:
        return self.mode == "live" or self.key_id.startswith("rzp_live")

    def assert_test_mode(self) -> None:
        if self.mode != "test" or self.key_id.startswith("rzp_live"):
            raise RazorpayLiveBlockedError(
                "Razorpay live/production execution is blocked. TEST MODE is required."
            )

    def create_test_order(
        self,
        *,
        amount_paise: int = TEST_ORDER_AMOUNT_PAISE,
        currency: str = TEST_CURRENCY,
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.assert_test_mode()
        if not self.configured:
            raise RazorpayTestError("Razorpay TEST credentials are not configured.")
        body = {
            "amount": int(amount_paise),
            "currency": currency,
            "receipt": str(receipt)[:40],
            "payment_capture": 0,
            "notes": {
                "environment": "test",
                "simulation_only": "true",
                "not_a_live_payment": "true",
                **(notes or {}),
            },
        }
        response = self._request("POST", "/orders", body)
        return self._sanitize_order(response)

    def fetch_test_payment(self, payment_id: str) -> dict[str, Any]:
        self.assert_test_mode()
        if not self.configured:
            raise RazorpayTestError("Razorpay TEST credentials are not configured.")
        response = self._request("GET", f"/payments/{payment_id}", None)
        return sanitize_public(
            {
                "provider": "razorpay",
                "environment": "test",
                "test_only": True,
                "not_a_live_payment": True,
                "payment_id": response.get("id"),
                "status": response.get("status"),
                "amount": response.get("amount"),
                "currency": response.get("currency"),
            }
        )

    def simulate_test_action(
        self,
        *,
        action_id: str,
        case_id: str,
        action_type: str,
        scope: str,
    ) -> dict[str, Any]:
        self.assert_test_mode()
        if not self.configured:
            return {
                "status": "unavailable",
                "provider": "razorpay",
                "environment": "test",
                "test_only": True,
                "not_a_live_payment": True,
                "reason": "configuration_missing",
                "message": "Razorpay test integration is unavailable (configuration missing).",
            }
        order = self.create_test_order(
            receipt=action_id,
            notes={"action_id": action_id, "case_id": case_id[:32], "action_type": action_type[:32]},
        )
        return {
            "status": "completed",
            "provider": "razorpay",
            "environment": "test",
            "test_only": True,
            "not_a_live_payment": True,
            "label": "Razorpay test simulation",
            "message": "Razorpay test simulation completed.",
            "test_order_id": order.get("test_order_id"),
            "order_status": order.get("order_status"),
            "amount": order.get("amount"),
            "currency": order.get("currency"),
            "receipt": order.get("receipt"),
            "scope": scope,
        }

    def _sanitize_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        return sanitize_public(
            {
                "provider": "razorpay",
                "environment": "test",
                "test_only": True,
                "not_a_live_payment": True,
                "test_order_id": payload.get("id"),
                "order_status": payload.get("status"),
                "amount": payload.get("amount"),
                "currency": payload.get("currency"),
                "receipt": payload.get("receipt"),
            }
        )

    def _request(self, method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        url = f"{API_BASE}{path}"
        try:
            if self.http is not None:
                response = self.http.request(
                    method,
                    url,
                    auth=(self.key_id, self.key_secret),
                    json=body,
                    timeout=10.0,
                )
            else:
                response = httpx.request(
                    method,
                    url,
                    auth=(self.key_id, self.key_secret),
                    json=body,
                    timeout=10.0,
                )
        except httpx.HTTPError as exc:
            raise RazorpayTestError("Razorpay TEST request failed.") from exc
        if response.status_code >= 400:
            raise RazorpayTestError(
                f"Razorpay TEST request was rejected (HTTP {response.status_code})."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RazorpayTestError("Razorpay TEST response was not JSON.") from exc
        if not isinstance(payload, dict):
            raise RazorpayTestError("Razorpay TEST response was not an object.")
        return payload


def get_adapter(http: RazorpayHttpClient | None = None) -> RazorpayPaymentAdapter:
    return RazorpayPaymentAdapter(http=http)
