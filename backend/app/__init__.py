"""FastAPI application package for Fraud-Spike Investigator."""

from __future__ import annotations

import sys
from pathlib import Path

# Vercel hoists this package to /var/task/app/main.py. Local packages vendored
# beside this file are importable only if this directory is on sys.path.
_APP_DIR = Path(__file__).resolve().parent
for _candidate in (_APP_DIR.parents[1], _APP_DIR.parent, _APP_DIR):
    if (_candidate / "agent" / "__init__.py").is_file():
        _path = str(_candidate)
        if _path not in sys.path:
            sys.path.append(_path)

# Static imports so the FastAPI function bundle includes local packages.
import agent  # noqa: F401
import data  # noqa: F401
import detection  # noqa: F401
import evaluation  # noqa: F401
import models  # noqa: F401
import tools  # noqa: F401
