"""SQLite durability behind the existing governance stores.

Stdlib sqlite3 only. One database, explicit world column, no second ActionStore.
Startup/reload is restore-only: it never approves, simulates, or calls Razorpay.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    world TEXT NOT NULL,
    case_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (world, case_id)
);
CREATE TABLE IF NOT EXISTS proposals (
    world TEXT NOT NULL,
    action_id TEXT NOT NULL,
    case_id TEXT,
    status TEXT,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (world, action_id)
);
CREATE TABLE IF NOT EXISTS approvals (
    world TEXT NOT NULL,
    action_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (world, action_id)
);
CREATE TABLE IF NOT EXISTS executions (
    world TEXT NOT NULL,
    action_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (world, action_id)
);
CREATE TABLE IF NOT EXISTS audit_events (
    world TEXT NOT NULL,
    audit_event_id TEXT NOT NULL,
    action_id TEXT,
    case_id TEXT,
    kind TEXT,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (world, audit_event_id)
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
    world TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    action_id TEXT NOT NULL,
    fingerprint_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (world, idempotency_key)
);
"""


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


def _load(raw: str) -> dict[str, Any]:
    payload = json.loads(raw)
    return payload if isinstance(payload, dict) else {}


class GovernanceDB:
    """Single-process SQLite file. Queries always filter by world."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def commit_bundle(
        self,
        world: str,
        *,
        decisions: list[dict[str, Any]] | None = None,
        proposals: list[dict[str, Any]] | None = None,
        approvals: list[dict[str, Any]] | None = None,
        executions: list[dict[str, Any]] | None = None,
        audits: list[dict[str, Any]] | None = None,
        idempotency: list[tuple[str, dict[str, Any]]] | None = None,
    ) -> None:
        """Write related governance rows in one transaction."""
        with self.lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN")
                for decision in decisions or []:
                    case_id = str(
                        decision.get("anomaly_id")
                        or decision.get("spike_id")
                        or decision.get("case_id")
                        or ""
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO decisions(world, case_id, payload_json) VALUES (?,?,?)",
                        (world, case_id, _json(decision)),
                    )
                for proposal in proposals or []:
                    conn.execute(
                        "INSERT OR REPLACE INTO proposals(world, action_id, case_id, status, payload_json) "
                        "VALUES (?,?,?,?,?)",
                        (
                            world,
                            str(proposal.get("action_id") or ""),
                            str(proposal.get("anomaly_id") or proposal.get("spike_id") or ""),
                            str(proposal.get("status") or ""),
                            _json(proposal),
                        ),
                    )
                for approval in approvals or []:
                    conn.execute(
                        "INSERT OR REPLACE INTO approvals(world, action_id, payload_json) VALUES (?,?,?)",
                        (world, str(approval.get("action_id") or ""), _json(approval)),
                    )
                for execution in executions or []:
                    conn.execute(
                        "INSERT OR REPLACE INTO executions(world, action_id, payload_json) VALUES (?,?,?)",
                        (world, str(execution.get("action_id") or ""), _json(execution)),
                    )
                for event in audits or []:
                    event_id = str(event.get("audit_event_id") or event.get("event_id") or "")
                    conn.execute(
                        "INSERT OR IGNORE INTO audit_events"
                        "(world, audit_event_id, action_id, case_id, kind, payload_json) "
                        "VALUES (?,?,?,?,?,?)",
                        (
                            world,
                            event_id,
                            event.get("action_id"),
                            event.get("anomaly_id") or event.get("spike_id"),
                            event.get("kind") or event.get("event_type"),
                            _json(event),
                        ),
                    )
                for key, record in idempotency or []:
                    conn.execute(
                        "INSERT OR REPLACE INTO idempotency_keys"
                        "(world, idempotency_key, action_id, fingerprint_json, payload_json) "
                        "VALUES (?,?,?,?,?)",
                        (
                            world,
                            key,
                            str(record.get("action_id") or ""),
                            _json(record.get("fingerprint") or {}),
                            _json(record),
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def load_world(self, world: str) -> dict[str, Any]:
        """Restore one world's rows. Does not approve, simulate, or emit side effects."""
        with self.lock:
            conn = self._connect()
            try:
                decisions = {
                    row[0]: _load(row[1])
                    for row in conn.execute(
                        "SELECT case_id, payload_json FROM decisions WHERE world=?",
                        (world,),
                    )
                }
                proposals = {
                    row[0]: _load(row[1])
                    for row in conn.execute(
                        "SELECT action_id, payload_json FROM proposals WHERE world=?",
                        (world,),
                    )
                }
                approvals = {
                    row[0]: _load(row[1])
                    for row in conn.execute(
                        "SELECT action_id, payload_json FROM approvals WHERE world=?",
                        (world,),
                    )
                }
                executions = {
                    row[0]: _load(row[1])
                    for row in conn.execute(
                        "SELECT action_id, payload_json FROM executions WHERE world=?",
                        (world,),
                    )
                }
                audit = [
                    _load(row[0])
                    for row in conn.execute(
                        "SELECT payload_json FROM audit_events WHERE world=? ORDER BY rowid",
                        (world,),
                    )
                ]
                idempotency = {
                    row[0]: _load(row[1])
                    for row in conn.execute(
                        "SELECT idempotency_key, payload_json FROM idempotency_keys WHERE world=?",
                        (world,),
                    )
                }
            finally:
                conn.close()
        return {
            "decisions": decisions,
            "proposals": proposals,
            "approvals": approvals,
            "executions": executions,
            "audit": audit,
            "idempotency": idempotency,
        }


def attach_default_stores(path: str | None) -> GovernanceDB | None:
    """Bind the existing world stores to one SQLite file. Restore only."""
    if not path or not str(path).strip():
        return None
    db = GovernanceDB(path)
    from agent.actions.service import bind_default_store
    from evaluation.real_data.governance import bind_store as bind_ieee
    from evaluation.recent_data.governance import bind_store as bind_january
    from agent.actions.store import ActionStore
    from evaluation.real_data.governance import RealActionStore
    from evaluation.recent_data.governance import RecentActionStore

    bind_default_store(ActionStore(db=db))
    bind_ieee(RealActionStore(db=db))
    bind_january(RecentActionStore(db=db))
    return db
