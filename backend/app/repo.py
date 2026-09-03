"""Ensure local packages are importable for uvicorn and the Vercel hoist."""

from __future__ import annotations

import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = next(
    (
        candidate
        for candidate in (_APP_DIR.parents[1], _APP_DIR.parent, _APP_DIR)
        if (candidate / "agent" / "__init__.py").is_file()
    ),
    _APP_DIR.parents[1],
)
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))
