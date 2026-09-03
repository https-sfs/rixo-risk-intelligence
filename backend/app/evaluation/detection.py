"""Held-out detection evaluation. Uses seed-2027 artifacts only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.labels import (
    LABEL_BACKGROUND,
    LABEL_COORDINATED,
    LABEL_FESTIVE,
    label_hour,
    map_detector_prediction,
)
from evaluation.metrics import (
    binary_counts,
    binary_scores,
    class_breakdown,
    confusion_matrix,
    json_number,
)
from evaluation.paths import (
    EVALUATION_SEED,
    HELDOUT_META_PATH,
    HELDOUT_WINDOWS_PATH,
)

EVAL_LABELS = (LABEL_COORDINATED, LABEL_FESTIVE, LABEL_BACKGROUND)


def _require_heldout_seed(meta_path: Path) -> int:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    seed = int(meta["seed"])
    if seed != EVALUATION_SEED:
        raise ValueError(f"Detection evaluation requires held-out seed {EVALUATION_SEED}, got {seed}")
    return seed


def load_labelled_windows(windows_path: Path = HELDOUT_WINDOWS_PATH) -> pd.DataFrame:
    windows = pd.read_csv(windows_path)
    if "spike_type" not in windows.columns:
        raise ValueError("hourly_windows.csv must include detector spike_type predictions")
    frame = windows.loc[:, ["window_start", "spike_type"]].copy()
    frame["truth"] = [label_hour(start) for start in frame["window_start"]]
    frame["prediction"] = [map_detector_prediction(str(value)) for value in frame["spike_type"]]
    return frame


def evaluate_heldout_detection(
    windows_path: Path = HELDOUT_WINDOWS_PATH,
    meta_path: Path = HELDOUT_META_PATH,
) -> dict[str, Any]:
    seed = _require_heldout_seed(meta_path)
    labelled = load_labelled_windows(windows_path)
    truths = labelled["truth"].tolist()
    predictions = labelled["prediction"].tolist()
    matrix = confusion_matrix(truths, predictions, EVAL_LABELS)
    per_class = class_breakdown(truths, predictions, EVAL_LABELS)
    festive_as_abuse = int(
        ((labelled["truth"] == LABEL_FESTIVE) & (labelled["prediction"] == LABEL_COORDINATED)).sum()
    )
    coordinated_detected = int(
        ((labelled["truth"] == LABEL_COORDINATED) & (labelled["prediction"] == LABEL_COORDINATED)).sum()
    )
    coordinated_total = int((labelled["truth"] == LABEL_COORDINATED).sum())
    any_scenario_counts = binary_counts(
        ["scenario" if truth != LABEL_BACKGROUND else "background" for truth in truths],
        ["scenario" if prediction != LABEL_BACKGROUND else "background" for prediction in predictions],
        "scenario",
    )
    return {
        "seed": seed,
        "evaluation_unit": "hourly_window",
        "ground_truth": {
            "source": "data.scenarios attack and festive calendars",
            "not_used": ["detector spike_type", "fraud_label", "event_type column"],
            "labels": {
                LABEL_COORDINATED: "hour overlaps an injected AttackSpec window",
                LABEL_FESTIVE: "hour is inside the festive sale calendar and is not an attack hour",
                LABEL_BACKGROUND: "hour is outside festive and attack calendars",
            },
            "note": (
                "Festive positives are sale-calendar hours, including low-volume night hours. "
                "The generator does not mark a separate festive-surge subset. "
                "fraud_label is delayed transaction truth and is not the spike label."
            ),
        },
        "prediction": {
            "source": "held-out hourly_windows.spike_type written by the existing detector",
            "mapping": {
                "suspicious_coordinated_spike": LABEL_COORDINATED,
                "legitimate_festive_spike": LABEL_FESTIVE,
                "ordinary": LABEL_BACKGROUND,
            },
        },
        "n_windows": int(len(labelled)),
        "truth_counts": labelled["truth"].value_counts().to_dict(),
        "prediction_counts": labelled["prediction"].value_counts().to_dict(),
        "confusion_matrix": matrix,
        "per_class": {
            label: {
                **{key: per_class[label][key] for key in ("tp", "fp", "tn", "fn")},
                "precision": json_number(per_class[label]["precision"]),
                "recall": json_number(per_class[label]["recall"]),
                "f1": json_number(per_class[label]["f1"]),
            }
            for label in EVAL_LABELS
        },
        "any_injected_scenario_vs_any_spike": {
            **any_scenario_counts,
            "precision": json_number(binary_scores(any_scenario_counts)["precision"]),
            "recall": json_number(binary_scores(any_scenario_counts)["recall"]),
            "f1": json_number(binary_scores(any_scenario_counts)["f1"]),
        },
        "product_checks": {
            "festive_hours_predicted_as_coordinated_abuse": festive_as_abuse,
            "coordinated_hours_detected_as_coordinated_abuse": coordinated_detected,
            "coordinated_hours_total": coordinated_total,
        },
    }


def write_detection_report(
    report: dict[str, Any] | None = None,
    output_path: Path | None = None,
) -> Path:
    payload = report if report is not None else evaluate_heldout_detection()
    dest = output_path or HELDOUT_WINDOWS_PATH.parent / "detection_metrics.json"
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def main() -> None:
    report = evaluate_heldout_detection()
    path = write_detection_report(report)
    print(json.dumps(report, indent=2))
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()

