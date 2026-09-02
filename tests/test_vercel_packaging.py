"""Vercel must ship the top-level agent package with api/index.py."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agent_package_is_present_and_importable() -> None:
    assert (ROOT / "agent" / "__init__.py").is_file()
    assert (ROOT / "agent" / "errors.py").is_file()
    assert (ROOT / "agent" / "actions" / "errors.py").is_file()
    from agent.actions.errors import ActionError
    from agent.errors import LLMProviderError

    assert issubclass(ActionError, Exception)
    assert issubclass(LLMProviderError, Exception)


def test_vercel_function_include_files_covers_agent() -> None:
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    function = config["functions"]["api/index.py"]
    assert "agent" in function["includeFiles"]


def test_entrypoint_statically_imports_agent() -> None:
    tree = ast.parse((ROOT / "api" / "index.py").read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    assert "agent" in names


def test_entrypoint_import_chain_resolves_agent_errors() -> None:
    import runpy

    namespace = runpy.run_path(str(ROOT / "api" / "index.py"))
    from agent.actions.errors import ActionError
    from agent.errors import LLMProviderError
    from app.errors import register_exception_handlers
    from fastapi.testclient import TestClient

    app = namespace["app"]
    health = TestClient(app).get("/health")
    assert health.status_code == 200
    assert namespace["agent"].errors.LLMProviderError is LLMProviderError
    assert register_exception_handlers is not None
    assert issubclass(ActionError, Exception)
