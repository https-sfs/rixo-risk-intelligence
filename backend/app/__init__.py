"""FastAPI application package for Fraud-Spike Investigator."""

from __future__ import annotations

import sys
from pathlib import Path

# Local packages (agent, tools, ...) live at the repository root.
# Local uvicorn uses backend/app → parents[2].
# Vercel hoists this package to /var/task/app → agent is at parents[1].
_HERE = Path(__file__).resolve()
_REPO_ROOT = next(
    (
        ancestor
        for ancestor in (_HERE.parents[1], _HERE.parents[2])
        if (ancestor / "agent" / "__init__.py").is_file()
    ),
    _HERE.parents[2],
)
_repo_root = str(_REPO_ROOT)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

# Static imports so the FastAPI function bundle includes local packages.
import agent  # noqa: F401
import data  # noqa: F401
import detection  # noqa: F401
import evaluation  # noqa: F401
import models  # noqa: F401
import tools  # noqa: F401
