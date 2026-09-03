"""Copy repo-root local packages into backend/app for the hoisted Vercel layout."""

from __future__ import annotations

import shutil
from pathlib import Path

PACKAGES = ("agent", "data", "detection", "evaluation", "models", "tools")
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEST_ROOT = HERE / "app"


def main() -> None:
    src_root = REPO if (REPO / "agent" / "__init__.py").is_file() else HERE
    for name in PACKAGES:
        src = src_root / name
        dest = DEST_ROOT / name
        if not src.is_dir():
            print(f"skip missing {src}")
            continue
        if dest.resolve() == src.resolve():
            print(f"already in place {name}")
            continue
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(
            src,
            dest,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                "real",
                "real_2026",
                "*.egg-info",
                "*.sqlite",
                "*.db",
            ),
        )
        print(f"vendored {name} -> {dest}")


if __name__ == "__main__":
    main()
