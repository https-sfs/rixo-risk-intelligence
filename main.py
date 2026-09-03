"""Vercel FastAPI entrypoint at the repository root."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_BACKEND = _ROOT / "backend"
for _path in (_ROOT, _BACKEND):
    _rendered = str(_path)
    if _rendered not in sys.path:
        sys.path.insert(0, _rendered)

# Static imports so Vercel marks these packages reachable at build time.
import agent  # noqa: F401
import data  # noqa: F401
import detection  # noqa: F401
import evaluation  # noqa: F401
import models  # noqa: F401
import tools  # noqa: F401

from app.main import app
