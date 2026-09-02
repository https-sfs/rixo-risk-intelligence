from __future__ import annotations

import pytest

from agent.actions.service import reset_default_store
from app.config import settings
from evaluation.custom_data.governance import reset_store as reset_custom
from evaluation.real_data.governance import reset_store as reset_ieee
from evaluation.recent_data.governance import reset_store as reset_january


@pytest.fixture(autouse=True)
def _razorpay_test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "razorpay_key_id", "")
    monkeypatch.setattr(settings, "razorpay_key_secret", "")
    monkeypatch.setattr(settings, "razorpay_mode", "test")


@pytest.fixture(autouse=True)
def _isolate_governance_stores() -> None:
    """Keep existing tests on in-memory stores. Durable tests bind an explicit temp file."""
    reset_default_store()
    reset_ieee()
    reset_january()
    reset_custom()
