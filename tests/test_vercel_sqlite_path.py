"""Serverless SQLite path resolution. Local defaults stay unchanged."""

from __future__ import annotations

from pathlib import Path

from app.config import (
    DEFAULT_GOVERNANCE_SQLITE_PATH,
    SERVERLESS_GOVERNANCE_SQLITE_PATH,
    resolve_governance_sqlite_path,
    settings,
)
from app.persistence import GovernanceDB, attach_default_stores


def test_local_default_sqlite_path_unchanged() -> None:
    assert settings.governance_sqlite_path == DEFAULT_GOVERNANCE_SQLITE_PATH
    assert settings.governance_sqlite_path == "data/governance.sqlite"
    assert resolve_governance_sqlite_path() == "data/governance.sqlite"
    assert resolve_governance_sqlite_path("data/governance.sqlite") == "data/governance.sqlite"


def test_explicit_temp_path_unchanged_locally(tmp_path: Path) -> None:
    target = str(tmp_path / "governance.sqlite")
    assert resolve_governance_sqlite_path(target) == target


def test_vercel_relocates_default_relative_path(monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    assert resolve_governance_sqlite_path("data/governance.sqlite") == SERVERLESS_GOVERNANCE_SQLITE_PATH
    assert resolve_governance_sqlite_path() == SERVERLESS_GOVERNANCE_SQLITE_PATH


def test_vercel_keeps_writable_absolute_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VERCEL", "1")
    target = str(tmp_path / "custom.sqlite")
    assert resolve_governance_sqlite_path(target) == target


def test_attach_creates_missing_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "does-not-exist-yet" / "governance.sqlite"
    db = attach_default_stores(str(nested))
    assert db is not None
    assert db.path == nested
    assert nested.exists()


def test_governance_db_uses_wal_locally(tmp_path: Path) -> None:
    db = GovernanceDB(tmp_path / "governance.sqlite")
    with db._connect() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_governance_db_uses_delete_journal_on_vercel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    db = GovernanceDB(tmp_path / "governance.sqlite")
    with db._connect() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "delete"
