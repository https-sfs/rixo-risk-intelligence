"""Vercel FastAPI packaging: repo-root entrypoint plus local packages."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_PACKAGES = ("agent", "data", "detection", "evaluation", "models", "tools")


def test_agent_package_is_present_and_importable() -> None:
    assert (ROOT / "agent" / "__init__.py").is_file()
    assert (ROOT / "agent" / "actions" / "errors.py").is_file()
    from agent.actions.errors import ActionError

    assert ActionError.__name__ == "ActionError"


def test_frontend_production_env_uses_backend_alias() -> None:
    production_env = (ROOT / "frontend" / ".env.production").read_text(encoding="utf-8")
    assert "VITE_API_BASE_URL=https://rixo-risk-intelligence.vercel.app" in production_env


def test_frontend_vercel_rewrites_spa_routes_to_index() -> None:
    config = json.loads((ROOT / "frontend" / "vercel.json").read_text(encoding="utf-8"))
    rewrites = config["rewrites"]
    assert any(item["destination"] == "/index.html" for item in rewrites)


def test_backend_requirements_has_no_path_install() -> None:
    lines = {
        line.strip()
        for line in (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert "../" not in lines
    assert "." not in lines
    assert any(line.startswith("fastapi") for line in lines)


def test_backend_contains_vendored_local_packages() -> None:
    app_dir = ROOT / "backend" / "app"
    for package in LOCAL_PACKAGES:
        assert (app_dir / package / "__init__.py").is_file()
    assert (app_dir / "agent" / "actions" / "errors.py").is_file()
    assert (app_dir / "tools" / "evidence.py").is_file()
    assert (ROOT / "backend" / "vendor_packages.py").is_file()


def test_vendor_copies_derived_world_artifacts() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "backend" / "vendor_packages.py")],
        cwd=str(ROOT / "backend"),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    app_dir = ROOT / "backend" / "app"
    assert (app_dir / "data" / "real" / "anomalies.json").is_file()
    assert (app_dir / "data" / "real" / "profile.json").is_file()
    assert (app_dir / "data" / "real" / "model" / "model_evaluation.json").is_file()
    assert (app_dir / "data" / "real_2026" / "benchmark.json").is_file()
    assert (app_dir / "data" / "real_2026" / "anomalies.json").is_file()
    assert not (app_dir / "data" / "real" / "train_transaction.csv").exists()
    assert not list((app_dir / "data" / "real_2026").glob("fraud_tests_export_*.csv"))


def test_backend_pyproject_declares_runtime_dependencies() -> None:
    pyproject = (ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    for dependency in (
        "fastapi>=0.115.0",
        "uvicorn[standard]>=0.32.0",
        "pydantic-settings>=2.6.0",
        "httpx>=0.27.0",
        "pandas>=2.2.0",
        "numpy>=1.26.0",
        "scikit-learn>=1.4.0",
        "joblib>=1.3.0",
    ):
        assert dependency in pyproject
    assert 'entrypoint = "app.main:app"' in pyproject
    assert '"" = ".."' not in pyproject


def test_pyproject_declares_vercel_entrypoint_and_local_packages() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'entrypoint = "main:app"' in pyproject
    for package in (*LOCAL_PACKAGES,):
        assert f"{package}*" in pyproject


def test_vercel_json_includes_local_packages_on_fastapi_entrypoint() -> None:
    path = ROOT / "vercel.json"
    assert path.is_file()
    config = json.loads(path.read_text(encoding="utf-8"))
    for key in ("main.py", "app/main.py", "backend/app/main.py"):
        include = config["functions"][key]["includeFiles"]
        assert "agent" in include
        assert "tools" in include
        assert "../" not in include
    assert "api/index.py" not in config["functions"]
    backend_config = json.loads((ROOT / "backend" / "vercel.json").read_text(encoding="utf-8"))
    include = backend_config["functions"]["app/main.py"]["includeFiles"]
    assert "app" in include
    assert "data" in include


def test_root_main_entrypoint_imports_app() -> None:
    import main as root_main

    assert root_main.app.title == "Fraud-Spike Investigator"


def test_app_main_import_chain_resolves_agent_errors() -> None:
    from agent.actions.errors import ActionError
    from app.main import app

    assert ActionError.__name__ == "ActionError"
    assert app.title == "Fraud-Spike Investigator"


def test_hoisted_var_task_layout_can_import_app_main(tmp_path: Path) -> None:
    """Reproduce /var/task/app plus sibling packages, repo root off sys.path."""
    import shutil

    subprocess.run(
        [sys.executable, str(ROOT / "backend" / "vendor_packages.py")],
        cwd=str(ROOT / "backend"),
        check=True,
    )
    task = tmp_path / "var" / "task"
    shutil.copytree(
        ROOT / "backend" / "app",
        task / "app",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    env = os.environ.copy()
    env["VERCEL"] = "1"
    env.pop("PYTHONPATH", None)
    env["PYTHONPATH"] = str(task)
    script = (
        "import fastapi\n"
        "from fastapi.testclient import TestClient\n"
        "import app.main\n"
        "assert app.main.app.title == 'Fraud-Spike Investigator'\n"
        "import agent, tools\n"
        "client = TestClient(app.main.app)\n"
        "real = client.get('/api/real/status')\n"
        "assert real.status_code == 200, real.text\n"
        "assert real.json()['ready'] is True\n"
        "assert real.json()['artifacts']['anomalies'] is True\n"
        "profile = client.get('/api/real/profile')\n"
        "assert profile.status_code == 200, profile.text\n"
        "recent = client.get('/api/recent/benchmark')\n"
        "assert recent.status_code == 200, recent.text\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok" in result.stdout
