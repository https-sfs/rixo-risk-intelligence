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


def search_roots() -> tuple[Path, ...]:
    """Candidate roots for data/ artifacts across local and Vercel layouts."""
    seen: list[Path] = []
    for candidate in (REPO_ROOT, _APP_DIR, _APP_DIR.parent, *_APP_DIR.parents[:3]):
        if candidate not in seen:
            seen.append(candidate)
    return tuple(seen)


def resolve_data_subdir(*parts: str, marker: str | None = None) -> Path:
    """Find data/<parts> that contains a committed artifact, else the repo-root path."""
    fallback = REPO_ROOT.joinpath("data", *parts)
    for root in search_roots():
        candidate = root.joinpath("data", *parts)
        if marker and (candidate / marker).is_file():
            return candidate
        if marker is None and candidate.is_dir():
            return candidate
    return fallback
