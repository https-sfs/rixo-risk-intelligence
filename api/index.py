import sys
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here.parent, here):
        if (candidate / "agent" / "__init__.py").is_file():
            return candidate
    return here.parent


ROOT = _repo_root()
BACKEND = ROOT / "backend"

for path in (ROOT, BACKEND):
    rendered = str(path)
    if rendered not in sys.path:
        sys.path.insert(0, rendered)

import agent  # noqa: F401
import agent.actions.errors  # noqa: F401
import agent.errors  # noqa: F401
import data  # noqa: F401
import detection  # noqa: F401
import evaluation  # noqa: F401
import models  # noqa: F401

from app.main import app
