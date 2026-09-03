"""Copy repo-root local packages and derived world artifacts into backend/app."""

from __future__ import annotations

import shutil
from pathlib import Path

PACKAGES = ("agent", "data", "detection", "evaluation", "models", "tools")
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEST_ROOT = HERE / "app"

# Derived artifacts only. Never vendor raw IEEE-CIS / Zenodo CSVs or the joblib.
REAL_ARTIFACTS = (
    "profile.json",
    "benchmark.json",
    "hourly_metrics.csv",
    "entity_metrics.csv",
    "anomalies.json",
    "evidence.json",
    "evaluation.json",
    "README.md",
)
REAL_MODEL_ARTIFACTS = (
    "feature_spec.json",
    "encoder.json",
    "model_evaluation.json",
    "hour_risk_overlay.json",
    "README.md",
)
RECENT_ARTIFACTS = (
    "profile.json",
    "benchmark.json",
    "hourly_metrics.csv",
    "anomalies.json",
    "evidence.json",
    "evaluation.json",
    "classifier_overlay.json",
    "README.md",
)


def _copy_named_files(src_dir: Path, dest_dir: Path, names: tuple[str, ...]) -> int:
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in names:
        src = src_dir / name
        if not src.is_file():
            continue
        shutil.copy2(src, dest_dir / name)
        copied += 1
        print(f"vendored artifact {src.relative_to(src_dir.parent.parent)} -> {dest_dir / name}")
    return copied


def vendor_world_artifacts(src_root: Path) -> None:
    data_src = src_root / "data"
    data_dest = DEST_ROOT / "data"
    copied = 0
    copied += _copy_named_files(data_src / "real", data_dest / "real", REAL_ARTIFACTS)
    copied += _copy_named_files(
        data_src / "real" / "model",
        data_dest / "real" / "model",
        REAL_MODEL_ARTIFACTS,
    )
    copied += _copy_named_files(data_src / "real_2026", data_dest / "real_2026", RECENT_ARTIFACTS)
    print(f"vendored {copied} derived world artifacts")


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
    vendor_world_artifacts(src_root)


if __name__ == "__main__":
    main()
