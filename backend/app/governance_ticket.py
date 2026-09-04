"""Signed governance tickets so action state survives separate Vercel invocations.

Vercel function instances do not share /tmp or process memory. The existing
GovernanceDB/SQLite file is still used when the same instance is reused, but
consecutive Decision → Approval → Simulation → Audit requests can land on
different instances. The browser already holds the action_id; this ticket
carries the minimal validated records for that action (and BYOD session
metadata, never the CSV) so the next instance can reconstruct the same store
rows and continue the existing approval gates.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import re
import time
from dataclasses import asdict, fields
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from agent.actions.models import ActionProposal, Approval, AuditEvent, ExecutionResult
from agent.actions.store import SYNTHETIC_WORLD
from app.config import GOVERNANCE_TICKET_HEADER, settings
from evaluation.custom_data.governance import (
    custom_world_key,
    parse_custom_world_key,
    store_for as custom_store_for,
)
from evaluation.real_data.mapper import WORLD as IEEE_WORLD
from evaluation.recent_data.mapper import WORLD as JANUARY_WORLD

TICKET_HEADER = GOVERNANCE_TICKET_HEADER
GOVERNANCE_PREFIXES = (
    "/api/actions",
    "/api/audit",
    "/api/investigations",
    "/api/spikes/",
    "/api/recent/",
    "/api/real/",
    "/api/custom/",
)

_ACTION_ID_RE = re.compile(r"/actions/([^/?]+)")
_SESSION_ID_RE = re.compile(r"/sessions/([^/?]+)")
_SPIKE_ID_RE = re.compile(r"/spikes/([^/?]+)")
_ANOMALY_ID_RE = re.compile(r"/anomalies/([^/?]+)")


def _secret() -> bytes:
    return settings.governance_signing_key.encode("utf-8")


def _b64url(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64url(text: str) -> bytes:
    import base64

    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def issue_ticket(payload: dict[str, Any]) -> str:
    body = dict(payload)
    now = int(time.time())
    body.setdefault("v", 1)
    body.setdefault("iat", now)
    body.setdefault("exp", now + int(settings.governance_ticket_ttl_seconds))
    packed = gzip.compress(json.dumps(body, default=str, separators=(",", ":")).encode("utf-8"), compresslevel=6)
    signature = hmac.new(_secret(), packed, hashlib.sha256).digest()
    return f"v1.{_b64url(packed)}.{_b64url(signature)}"


def read_ticket(token: str | None) -> dict[str, Any] | None:
    if not token or not token.startswith("v1."):
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        packed = _unb64url(parts[1])
        signature = _unb64url(parts[2])
    except (ValueError, OSError):
        return None
    expected = hmac.new(_secret(), packed, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(gzip.decompress(packed).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and exp < time.time():
        return None
    return payload


def _dataclass_from(model: type, payload: dict[str, Any]) -> Any:
    allowed = {item.name for item in fields(model)}
    data = dict(payload)
    if model is AuditEvent and "kind" not in data and "event_type" in data:
        data["kind"] = data["event_type"]
    return model(**{key: value for key, value in data.items() if key in allowed})


def hydrate_ticket(token: str | None) -> dict[str, Any] | None:
    payload = read_ticket(token)
    if payload is None:
        return None
    _hydrate_actions(payload.get("actions") or {})
    for session_id, snapshot in (payload.get("sessions") or {}).items():
        if isinstance(snapshot, dict):
            from app.services.custom_world import restore_session_snapshot

            restore_session_snapshot(snapshot, persist_sidecar=False)
            custom_store_for(str(session_id))
    return payload


def _hydrate_actions(actions: dict[str, Any]) -> None:
    from agent.actions.service import default_store as synthetic_store
    from evaluation.real_data.governance import default_store as ieee_store
    from evaluation.recent_data.governance import default_store as january_store

    for world, records in actions.items():
        if not isinstance(records, dict):
            continue
        if world == SYNTHETIC_WORLD:
            store = synthetic_store()
            for action_id, record in records.items():
                if not isinstance(record, dict):
                    continue
                proposal = record.get("proposal")
                if isinstance(proposal, dict):
                    item = _dataclass_from(ActionProposal, proposal)
                    store.proposals[action_id] = item
                    store.persist(proposals=[item])
                approval = record.get("approval")
                if isinstance(approval, dict):
                    item = _dataclass_from(Approval, approval)
                    store.approvals[action_id] = item
                    store.persist(approvals=[item])
                execution = record.get("execution")
                if isinstance(execution, dict):
                    item = _dataclass_from(ExecutionResult, execution)
                    store.executions[action_id] = item
                    store.persist(executions=[item])
                for event in record.get("audit") or []:
                    if not isinstance(event, dict):
                        continue
                    item = _dataclass_from(AuditEvent, event)
                    if all(existing.event_id != item.event_id for existing in store.audit):
                        store.audit.append(item)
                        store.persist(audits=[item])
            continue
        if world == JANUARY_WORLD:
            _hydrate_dict_store(january_store(), records)
            continue
        if world == IEEE_WORLD:
            _hydrate_dict_store(ieee_store(), records)
            continue
        session_id = parse_custom_world_key(world)
        if session_id:
            _hydrate_dict_store(custom_store_for(session_id), records)


def _hydrate_dict_store(store: Any, records: dict[str, Any]) -> None:
    for action_id, record in records.items():
        if not isinstance(record, dict):
            continue
        proposal = record.get("proposal")
        if isinstance(proposal, dict):
            store.proposals[action_id] = proposal
        approval = record.get("approval")
        if isinstance(approval, dict):
            store.approvals[action_id] = approval
        execution = record.get("execution")
        if isinstance(execution, dict):
            store.executions[action_id] = execution
        decision = record.get("decision")
        if isinstance(decision, dict):
            case_id = str(decision.get("anomaly_id") or decision.get("spike_id") or "")
            if case_id:
                store.decisions[case_id] = decision
        for event in record.get("audit") or []:
            if not isinstance(event, dict):
                continue
            event_id = event.get("audit_event_id") or event.get("event_id")
            if event_id and any(
                item.get("audit_event_id") == event_id or item.get("event_id") == event_id
                for item in store.audit
            ):
                continue
            store.audit.append(event)
        persist = getattr(store, "persist", None)
        if persist is None:
            continue
        persist(
            decisions=[decision] if isinstance(decision, dict) else None,
            proposals=[proposal] if isinstance(proposal, dict) else None,
            approvals=[approval] if isinstance(approval, dict) else None,
            executions=[execution] if isinstance(execution, dict) else None,
            audits=list(record.get("audit") or []) or None,
        )


def _collect_ids(path: str, body: bytes, inbound: dict[str, Any] | None) -> tuple[set[str], set[str]]:
    action_ids: set[str] = set()
    session_ids: set[str] = set()
    if inbound:
        for records in (inbound.get("actions") or {}).values():
            if isinstance(records, dict):
                action_ids.update(str(key) for key in records)
        session_ids.update(str(key) for key in (inbound.get("sessions") or {}))
    match = _ACTION_ID_RE.search(path)
    if match and match.group(1) not in {"propose", "execute", "approve", "simulate"}:
        action_ids.add(match.group(1))
    match = _SESSION_ID_RE.search(path)
    if match:
        session_ids.add(match.group(1))
    parsed = _json_object(body)
    if parsed:
        _walk_ids(parsed, action_ids, session_ids)
    return action_ids, session_ids


def _walk_ids(value: Any, action_ids: set[str], session_ids: set[str]) -> None:
    if isinstance(value, dict):
        action_id = value.get("action_id")
        if isinstance(action_id, str) and action_id:
            action_ids.add(action_id)
        session_id = value.get("session_id")
        if isinstance(session_id, str) and session_id:
            session_ids.add(session_id)
        for child in value.values():
            _walk_ids(child, action_ids, session_ids)
    elif isinstance(value, list):
        for child in value:
            _walk_ids(child, action_ids, session_ids)


def _json_object(body: bytes) -> dict[str, Any] | None:
    if not body:
        return None
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _snapshot_action(world: str, action_id: str) -> dict[str, Any] | None:
    from agent.actions.service import default_store as synthetic_store
    from evaluation.real_data.governance import default_store as ieee_store
    from evaluation.recent_data.governance import default_store as january_store

    if world == SYNTHETIC_WORLD:
        store = synthetic_store()
        proposal = store.proposals.get(action_id)
        if proposal is None:
            return None
        approval = store.approvals.get(action_id)
        execution = store.executions.get(action_id)
        return {
            "proposal": proposal.to_dict(),
            "approval": approval.to_dict() if approval else None,
            "execution": execution.to_dict() if execution else None,
            "audit": [asdict(event) for event in store.events_for(action_id)],
        }
    if world == JANUARY_WORLD:
        return _snapshot_dict_store(january_store(), action_id)
    if world == IEEE_WORLD:
        return _snapshot_dict_store(ieee_store(), action_id)
    session_id = parse_custom_world_key(world)
    if session_id:
        return _snapshot_dict_store(custom_store_for(session_id), action_id)
    return None


def _snapshot_dict_store(store: Any, action_id: str) -> dict[str, Any] | None:
    proposal = store.proposals.get(action_id)
    if proposal is None:
        return None
    case_id = str(proposal.get("anomaly_id") or proposal.get("spike_id") or "")
    return {
        "proposal": proposal,
        "approval": store.approvals.get(action_id),
        "execution": store.executions.get(action_id),
        "decision": store.decisions.get(case_id) if case_id else None,
        "audit": [
            event
            for event in store.audit
            if event.get("action_id") == action_id or event.get("anomaly_id") == case_id
        ],
    }


def _locate_action(action_id: str) -> str | None:
    from agent.actions.service import default_store as synthetic_store
    from evaluation.real_data.governance import default_store as ieee_store
    from evaluation.recent_data.governance import default_store as january_store

    if action_id in synthetic_store().proposals:
        return SYNTHETIC_WORLD
    if action_id in january_store().proposals:
        return JANUARY_WORLD
    if action_id in ieee_store().proposals:
        return IEEE_WORLD
    from evaluation.custom_data.governance import _STORES

    for session_id, store in _STORES.items():
        if action_id in store.proposals:
            return custom_world_key(session_id)
    return None


def _path_world_hints(path: str, session_ids: set[str]) -> list[str]:
    hints: list[str] = []
    if path.startswith("/api/actions") or path.startswith("/api/spikes/") or path.startswith("/api/audit"):
        hints.append(SYNTHETIC_WORLD)
    if path.startswith("/api/recent/"):
        hints.append(JANUARY_WORLD)
    if path.startswith("/api/real/"):
        hints.append(IEEE_WORLD)
    if path.startswith("/api/custom/"):
        hints.extend(custom_world_key(session_id) for session_id in session_ids)
    return hints


def issue_ticket_after_response(
    inbound_token: str | None,
    path: str,
    body: bytes,
) -> str | None:
    inbound = read_ticket(inbound_token) or {}
    action_ids, session_ids = _collect_ids(path, body, inbound)
    spike_match = _SPIKE_ID_RE.search(path)
    if spike_match:
        from agent.actions.service import default_store

        latest = default_store().latest_proposal_for_spike(spike_match.group(1))
        if latest is not None:
            action_ids.add(latest.action_id)
    anomaly_match = _ANOMALY_ID_RE.search(path)
    if anomaly_match:
        anomaly_id = anomaly_match.group(1)
        from evaluation.real_data.governance import default_store as ieee_store
        from evaluation.recent_data.governance import default_store as january_store

        for store in (january_store(), ieee_store()):
            for proposal in store.proposals.values():
                if proposal.get("anomaly_id") == anomaly_id:
                    action_ids.add(str(proposal["action_id"]))
        for session_id in session_ids:
            store = custom_store_for(session_id)
            for proposal in store.proposals.values():
                if proposal.get("anomaly_id") == anomaly_id:
                    action_ids.add(str(proposal["action_id"]))

    actions: dict[str, dict[str, Any]] = {}
    inbound_actions = inbound.get("actions") if isinstance(inbound.get("actions"), dict) else {}
    for world, records in inbound_actions.items():
        if isinstance(records, dict):
            actions[world] = {key: value for key, value in records.items() if isinstance(value, dict)}

    for action_id in action_ids:
        world = _locate_action(action_id)
        if world is None:
            for hint in _path_world_hints(path, session_ids):
                record = _snapshot_action(hint, action_id)
                if record is not None:
                    world = hint
                    break
        if world is None:
            continue
        record = _snapshot_action(world, action_id)
        if record is None:
            continue
        actions.setdefault(world, {})[action_id] = record

    sessions: dict[str, Any] = {}
    inbound_sessions = inbound.get("sessions") if isinstance(inbound.get("sessions"), dict) else {}
    for session_id, snapshot in inbound_sessions.items():
        if isinstance(snapshot, dict):
            sessions[session_id] = snapshot
    if session_ids:
        from app.services.custom_world import session_snapshot_for_ticket

        for session_id in session_ids:
            snapshot = session_snapshot_for_ticket(session_id)
            if snapshot is not None:
                sessions[session_id] = snapshot

    if not actions and not sessions:
        return inbound_token if inbound_token else None
    return issue_ticket({"actions": actions, "sessions": sessions})


def _inject_ticket_json(body: bytes, ticket: str) -> bytes:
    parsed = _json_object(body)
    if parsed is None:
        return body
    parsed["governance_ticket"] = ticket
    return json.dumps(parsed, default=str).encode("utf-8")


def is_governance_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in GOVERNANCE_PREFIXES)


class GovernanceTicketMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        inbound = request.headers.get(TICKET_HEADER)
        if inbound:
            hydrate_ticket(inbound)
        response = await call_next(request)
        if not is_governance_path(request.url.path):
            return response
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        ticket = issue_ticket_after_response(inbound, request.url.path, body)
        headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() != "content-length"
        }
        if ticket:
            headers[TICKET_HEADER] = ticket
            body = _inject_ticket_json(body, ticket)
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )
