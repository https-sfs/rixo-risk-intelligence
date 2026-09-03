"""Vercel FastAPI packaging: repo-root entrypoint plus local packages."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agent_package_is_present_and_importable() -> None:
    assert (ROOT / "agent" / "__init__.py").is_file()
    assert (ROOT / "agent" / "actions" / "errors.py").is_file()
    from agent.actions.errors import ActionError

    assert ActionError.__name__ == "ActionError"


def test_backend_requirements_has_no_parent_path_dependency() -> None:
    requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "../" not in {line.strip() for line in requirements.splitlines()}


def test_pyproject_declares_vercel_entrypoint_and_local_packages() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'entrypoint = "backend.app.main:app"' in pyproject
    for package in ("agent*", "data*", "detection*", "evaluation*", "models*"):
        assert package in pyproject


def test_vercel_json_includes_local_packages_on_fastapi_entrypoint() -> None:
    path = ROOT / "vercel.json"
    assert path.is_file()
    config = json.loads(path.read_text(encoding="utf-8"))
    function = config["functions"]["backend/app/main.py"]
    assert "agent" in function["includeFiles"]
    assert "../" not in function["includeFiles"]
    assert "api/index.py" not in config["functions"]
    assert not (ROOT / "backend" / "vercel.json").exists()


def test_app_main_import_chain_resolves_agent_errors() -> None:
    from agent.actions.errors import ActionError
    from app.main import app

    assert ActionError.__name__ == "ActionError"
    assert app.title == "Fraud-Spike Investigator"
