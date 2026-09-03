"""Lightweight structured audit trail. No secrets, no ledger dumps."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent.actions.models import AuditEvent, AuditEventType
from agent.actions.store import ActionStore


def record_audit(
    store: ActionStore,
    *,
    kind: AuditEventType,
    action_id: str,
    spike_id: str,
    actor: str,
    details: dict[str, Any],
    timestamp: str,
) -> AuditEvent:
    event = AuditEvent(
        event_id=f"aud-{uuid4().hex[:12]}",
        timestamp=timestamp,
        action_id=action_id,
        spike_id=spike_id,
        kind=kind,
        actor=actor,
        details=details,
    )
    store.append_audit(event)
    return event
