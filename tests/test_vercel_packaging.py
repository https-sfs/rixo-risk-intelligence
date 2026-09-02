"""Vercel must install the repo-root agent package for the FastAPI runtime."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ROOT_VERCEL = {
    "app/main.py": {
        "includeFiles": "{agent,../agent,data,../data,detection,../detection,evaluation,../evaluation,models,../models}/**"
    },
    "backend/app/main.py": {
        "includeFiles": "{agent,backend,data,detection,evaluation,models}/**"
    },
}

BACKEND_VERCEL = {
    "app/main.py": {
        "includeFiles": "{../agent,../data,../detection,../evaluation,../models}/**"
    }
}


def test_agent_package_is_present_and_importable() -> None:
    assert (ROOT / "agent" / "__init__.py").is_file()
    assert (ROOT / "agent" / "errors.py").is_file()
    assert (ROOT / "agent" / "actions" / "errors.py").is_file()
    from agent.actions.errors import ActionError
    from agent.errors import LLMProviderError

    assert issubclass(ActionError, Exception)
    assert issubclass(LLMProviderError, Exception)


def test_backend_requirements_installs_workspace_from_repo_root() -> None:
    requirements = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    assert "../" in {line.strip() for line in requirements.splitlines()}
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for package in ("agent*", "data*", "detection*", "evaluation*", "models*"):
        assert package in pyproject


def test_vercel_json_matches_required_function_config() -> None:
    path = ROOT / "vercel.json"
    assert path.is_file()
    config = json.loads(path.read_text(encoding="utf-8"))
    assert config["functions"] == ROOT_VERCEL
    assert "api/index.py" not in config["functions"]


def test_backend_vercel_json_matches_required_function_config() -> None:
    path = ROOT / "backend" / "vercel.json"
    assert path.is_file()
    config = json.loads(path.read_text(encoding="utf-8"))
    assert config["functions"] == BACKEND_VERCEL


def test_app_main_import_chain_resolves_agent_errors() -> None:
    from agent.actions.errors import ActionError
    from app.main import app

    assert ActionError.__name__ == "ActionError"
    assert app.title == "Fraud-Spike Investigator"
