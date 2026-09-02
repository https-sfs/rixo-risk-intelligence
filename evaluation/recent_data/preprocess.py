"""Write derived recent-data artifacts once. API reads these, not the raw CSV on every request."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.recent_data.benchmark import benchmark_from_raw
from evaluation.recent_data.detect import build_hourly, detect_anomalies
from evaluation.recent_data.evaluate import build_evaluation
from evaluation.recent_data.mapper import (
    AMOUNT_CURRENCY,
    DATASET_NAME,
    WORLD,
    assert_not_locked_path,
    load_raw,
    map_collection,
)
from evaluation.recent_data.profile import write_profile


def _hour_slice(mapped: pd.DataFrame, hour: str) -> pd.DataFrame:
    target = pd.Timestamp(hour)
    hours = pd.to_datetime(mapped["hour_start"], errors="coerce").dt.floor("h")
    return mapped.loc[hours == target]


def build_evidence(mapped, anomaly: dict[str, Any]) -> dict[str, Any]:
    hour = anomaly["hour_start"]
    slice_ = _hour_slice(mapped, hour)
    fraud = slice_["fraud_label"] == 1 if "fraud_label" in slice_.columns else None
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "amount_currency": AMOUNT_CURRENCY,
        "anomaly_id": anomaly["anomaly_id"],
        "kind": anomaly["kind"],
        "hour_start": hour,
        "live_evidence": {
            "transaction_count": {
                "value": int(len(slice_)),
                "label": "OBSERVED",
                "source": "January collection timestamp hour",
            },
            "amount_usd": {
                "value": float(slice_["amount_usd"].sum(min_count=1) or 0.0),
                "label": "OBSERVED",
                "source": "amount",
            },
            "temporal_window": {
                "value": hour,
                "label": "DERIVED",
                "source": "floor(timestamp to hour)",
            },
        },
        "evaluation_overlay": {
            "label": "DELAYED GROUND TRUTH",
            "fraud_count": int(fraud.sum()) if fraud is not None else None,
            "fraud_rate": float(fraud.mean()) if fraud is not None and len(slice_) else None,
            "fraud_amount_usd": (
                float(slice_.loc[fraud, "amount_usd"].sum(min_count=1) or 0.0) if fraud is not None else None
            ),
            "note": "is_fraud was not used to detect this anomaly.",
        },
        "source_dataset_model_output": {
            "used": False,
            "note": "Source CNN-LSTM probability, risk, confidence, and recommendation are excluded.",
        },
    }


def preprocess(data_dir: Path) -> dict[str, Any]:
    dest = Path(data_dir)
    profile = write_profile(dest, dest / "profile.json")
    raw = load_raw(dest)
    mapped = map_collection(raw)
    hourly = build_hourly(mapped)
    anomalies = detect_anomalies(hourly)
    benchmark = benchmark_from_raw(raw)
    evidence = {item["anomaly_id"]: build_evidence(mapped, item) for item in anomalies}
    evaluation = build_evaluation()
    artifacts = {
        "benchmark.json": {k: v for k, v in benchmark.items() if k != "anomalies"},
        "anomalies.json": {
            "world": WORLD,
            "dataset": DATASET_NAME,
            "count": len(anomalies),
            "anomalies": anomalies,
        },
        "hourly_metrics.csv": hourly,
        "evidence.json": evidence,
        "evaluation.json": evaluation,
    }
    for name, payload in artifacts.items():
        target = dest / name
        assert_not_locked_path(target)
        if name.endswith(".csv"):
            payload.to_csv(target, index=False)
        else:
            target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "world": WORLD,
        "january_rows": int(len(mapped)),
        "anomalies": len(anomalies),
        "profile": profile["january_collection"],
        "artifacts": [
            "profile.json",
            "benchmark.json",
            "hourly_metrics.csv",
            "anomalies.json",
            "evidence.json",
            "evaluation.json",
        ],
    }


if __name__ == "__main__":
    from evaluation.recent_data import RECENT_DATA_DIR

    print(json.dumps(preprocess(RECENT_DATA_DIR), indent=2))
