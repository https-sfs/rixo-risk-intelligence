"""FastAPI application package for Fraud-Spike Investigator."""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root sits two levels above this file (backend/app/__init__.py).
# Uvicorn started from backend/ can import `app` but not sibling packages
# such as `agent`. Inserting the root keeps those imports as the real
# repository packages. Tests already set pythonpath = . backend.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_repo_root = str(_REPO_ROOT)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
