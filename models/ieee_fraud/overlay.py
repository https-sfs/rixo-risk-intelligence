"""Hour-level MODEL PREDICTION overlay. Does not create a new anomaly type."""

from __future__ import annotations

from typing import Any

import pandas as pd

from models.ieee_fraud import DATASET_NAME, PROVENANCE, WORLD
from models.ieee_fraud.features import SECONDS_PER_HOUR

IN_SAMPLE_OVERLAY = "IN_SAMPLE_MODEL_OVERLAY"
OUT_OF_SAMPLE_OVERLAY = "OUT_OF_SAMPLE_MODEL_OVERLAY"


def overlay_sample_scope(relative_hour_bucket: int, train_cutoff_elapsed: float | None) -> str | None:
    if train_cutoff_elapsed is None:
        return None
    hour_start = int(relative_hour_bucket) * SECONDS_PER_HOUR
    if hour_start <= float(train_cutoff_elapsed):
        return IN_SAMPLE_OVERLAY
    return OUT_OF_SAMPLE_OVERLAY


def apply_sample_scopes(overlay: dict[str, Any], train_cutoff_elapsed: float | None) -> dict[str, Any]:
    hours = overlay.get("hours") or {}
    for bucket, block in hours.items():
        scope = overlay_sample_scope(int(block.get("relative_hour_bucket", bucket)), train_cutoff_elapsed)
        if scope:
            block["sample_scope"] = scope
            block["not_a_test_metric"] = scope == IN_SAMPLE_OVERLAY
    overlay["train_cutoff_elapsed_seconds"] = train_cutoff_elapsed
    overlay["sample_scope_note"] = (
        "IN_SAMPLE_MODEL_OVERLAY scores hours at or before the train TransactionDT cutoff. "
        "Those scores are investigation display, not untouched test metrics. "
        "OUT_OF_SAMPLE_MODEL_OVERLAY hours are after the train cutoff."
    )
    return overlay


def aggregate_hour_scores(
    scored: pd.DataFrame,
    threshold: float,
    top_k: int = 8,
    train_cutoff_elapsed: float | None = None,
) -> dict[str, Any]:
    required = {"relative_hour_bucket", "fraud_risk_score"}
    missing = required.difference(scored.columns)
    if missing:
        raise ValueError(f"Overlay requires columns: {sorted(missing)}")
    work = scored.dropna(subset=["relative_hour_bucket", "fraud_risk_score"]).copy()
    work["relative_hour_bucket"] = work["relative_hour_bucket"].astype(int)
    hours: dict[str, Any] = {}
    for bucket, group in work.groupby("relative_hour_bucket", sort=True):
        scores = pd.to_numeric(group["fraud_risk_score"], errors="coerce")
        ranked = group.assign(overlay_score=scores).sort_values("overlay_score", ascending=False).head(top_k)
        top = []
        for _, row in ranked.iterrows():
            item = {
                "transaction_id": str(row.get("transaction_id", "")),
                "fraud_risk_score": float(row["overlay_score"]),
                "amount_usd": (
                    float(row["amount_usd"]) if pd.notna(row.get("amount_usd")) else None
                ),
                "provenance": PROVENANCE,
            }
            if "fraud_label" in row and pd.notna(row["fraud_label"]):
                item["delayed_ground_truth"] = int(row["fraud_label"])
            top.append(item)
        hours[str(int(bucket))] = {
            "relative_hour_bucket": int(bucket),
            "label": PROVENANCE,
            "sample_scope": overlay_sample_scope(int(bucket), train_cutoff_elapsed),
            "not_a_test_metric": overlay_sample_scope(int(bucket), train_cutoff_elapsed)
            == IN_SAMPLE_OVERLAY,
            "transaction_count": int(len(group)),
            "mean_score": float(scores.mean()) if scores.notna().any() else None,
            "p95_score": float(scores.quantile(0.95)) if scores.notna().any() else None,
            "high_risk_count": int((scores >= threshold).sum()),
            "high_risk_rate": float((scores >= threshold).mean()) if len(group) else None,
            "threshold": threshold,
            "top_transactions": top,
        }
    return apply_sample_scopes(
        {
            "world": WORLD,
            "dataset": DATASET_NAME,
            "provenance": PROVENANCE,
            "note": (
                "Hour aggregates of our IEEE-CIS classifier. "
                "This overlay does not replace the hour-level anomaly detector. "
                "In-sample hours are not untouched test metrics."
            ),
            "hours": hours,
        },
        train_cutoff_elapsed,
    )


def overlay_for_anomaly(overlay: dict[str, Any], relative_hour_bucket: int) -> dict[str, Any] | None:
    hours = overlay.get("hours") or {}
    return hours.get(str(int(relative_hour_bucket)))
