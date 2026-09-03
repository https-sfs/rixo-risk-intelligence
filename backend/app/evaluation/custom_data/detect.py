"""Deterministic anomaly signals from fields that actually exist."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.custom_data import WORLD
from evaluation.custom_data.schema import CustomDataError
from evaluation.custom_data.stream import iter_mapped_chunks

VOLUME_Z = 2.5
AMOUNT_Z = 2.5
MIN_TRANSACTIONS = 15
ENTITY_SHARE = 0.35
ENTITY_ROLES = (
    ("account_id", "entity concentration", "OBSERVED"),
    ("device_id", "entity concentration", "OBSERVED"),
    ("ip_address", "entity concentration", "PROXY"),
    ("merchant", "merchant concentration", "OBSERVED"),
    ("product_sku", "product concentration", "OBSERVED"),
)
SECONDS_PER_HOUR = 3600


def relative_hour_key(bucket: int) -> str:
    return f"relative-hour-{int(bucket)}"


def relative_hour_display(bucket: int) -> str:
    return f"Relative hour {int(bucket):,}"


def hour_display(hour_key: str, time_kind: str | None = None) -> str:
    key = str(hour_key or "")
    if time_kind == "relative_elapsed" or key.startswith("relative-hour-"):
        try:
            return relative_hour_display(int(key.rsplit("-", 1)[-1]))
        except ValueError:
            return "Relative hour (dataset elapsed time)"
    return key


def _safe_amount_sum(group: pd.DataFrame) -> float | None:
    if "amount" not in group.columns:
        return None
    total = pd.to_numeric(group["amount"], errors="coerce").sum(min_count=1)
    if pd.isna(total):
        return None
    return float(total)


def _robust_z(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    median = float(values.median()) if values.notna().any() else 0.0
    mad = float((values - median).abs().median()) if values.notna().any() else 0.0
    if mad > 0:
        return 0.6745 * (values - median) / mad
    std = float(values.std(ddof=0)) if values.notna().any() else 0.0
    if std == 0:
        return pd.Series(0.0, index=series.index)
    return (values - values.mean()) / std


def prepare_analysis_frame(mapped: pd.DataFrame) -> pd.DataFrame:
    work = mapped.copy()
    leaked = [name for name in ("fraud_label", "is_fraud", "isFraud") if name in work.columns]
    live = work.drop(columns=leaked, errors="ignore")
    if "amount" in live.columns:
        live["amount"] = pd.to_numeric(live["amount"], errors="coerce")
    if "timestamp" in live.columns:
        if pd.api.types.is_datetime64_any_dtype(live["timestamp"]):
            live["event_time"] = live["timestamp"]
            live["time_provenance"] = "OBSERVED"
            live["time_kind"] = "calendar"
            live["hour_start"] = live["event_time"].dt.floor("h").dt.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            numeric = pd.to_numeric(live["timestamp"], errors="coerce")
            numeric_share = float(numeric.notna().mean()) if len(live) else 0.0
            looks_elapsed = pd.api.types.is_numeric_dtype(live["timestamp"]) or (
                numeric_share >= 0.8
                and not live["timestamp"].astype(str).str.contains(r"[-/T:]", regex=True).any()
            )
            if looks_elapsed:
                buckets = (numeric // SECONDS_PER_HOUR).astype("Int64")
                live["relative_hour_bucket"] = buckets
                live["hour_start"] = buckets.map(
                    lambda value: None if pd.isna(value) else relative_hour_key(int(value))
                )
                live["time_provenance"] = "PROXY"
                live["time_kind"] = "relative_elapsed"
            else:
                parsed = pd.to_datetime(live["timestamp"], errors="coerce")
                if parsed.notna().mean() >= 0.5:
                    live["event_time"] = parsed
                    live["time_provenance"] = "OBSERVED"
                    live["time_kind"] = "calendar"
                    live["hour_start"] = parsed.dt.floor("h").dt.strftime("%Y-%m-%dT%H:%M:%S")
                elif numeric_share >= 0.5:
                    buckets = (numeric // SECONDS_PER_HOUR).astype("Int64")
                    live["relative_hour_bucket"] = buckets
                    live["hour_start"] = buckets.map(
                        lambda value: None if pd.isna(value) else relative_hour_key(int(value))
                    )
                    live["time_provenance"] = "PROXY"
                    live["time_kind"] = "relative_elapsed"
                else:
                    live["hour_start"] = pd.Series(pd.NA, index=live.index)
                    live["time_provenance"] = "OBSERVED"
                    live["time_kind"] = "calendar"
    return live


def _entity_share(group: pd.DataFrame, column: str) -> dict[str, Any] | None:
    if column not in group.columns:
        return None
    series = group[column].dropna()
    if series.empty:
        return None
    nunique = int(series.nunique())
    if nunique <= 1 or nunique >= len(group):
        return None
    counts = series.astype(str).value_counts()
    top_value = str(counts.index[0])
    share = float(counts.iloc[0] / len(group))
    if share < ENTITY_SHARE:
        return None
    return {"value": top_value, "share": share, "unique": nunique}


def detect_anomalies(mapped: pd.DataFrame, limit: int = 25) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    live = prepare_analysis_frame(mapped)
    if "fraud_label" in live.columns:
        raise CustomDataError("Fraud labels leaked into custom-data live scoring.")

    hourly_rows: list[dict[str, Any]] = []
    if "hour_start" in live.columns:
        timed = live.dropna(subset=["hour_start"])
        for hour, group in timed.groupby("hour_start", sort=True):
            time_kind = (
                str(group["time_kind"].iloc[0]) if "time_kind" in group.columns else "calendar"
            )
            hour_key = str(hour)
            row: dict[str, Any] = {
                "hour_start": hour_key,
                "time_kind": time_kind,
                "time_display": hour_display(hour_key, time_kind),
                "transaction_count": int(len(group)),
                "amount_sum": _safe_amount_sum(group),
                "time_provenance": str(group["time_provenance"].iloc[0])
                if "time_provenance" in group.columns
                else "DERIVED",
            }
            for role, _kind, provenance in ENTITY_ROLES:
                share = _entity_share(group, role)
                if share:
                    row[f"{role}_top"] = {**share, "provenance": provenance}
            hourly_rows.append(row)

    hourly = pd.DataFrame(hourly_rows)
    return _anomalies_from_hourly(hourly, analyzed=int(len(mapped)), limit=limit)


def detect_from_path(
    path: str | Path,
    mapping: dict[str, str],
    limit: int = 25,
    max_rows: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, dict[str, Any]]]:
    """Hour-level detection from mapped CSV chunks. Labels are never detector inputs."""
    hours: dict[str, dict[str, Any]] = {}
    analyzed = 0
    for chunk in iter_mapped_chunks(path, mapping):
        next_rows = analyzed + int(len(chunk))
        if max_rows is not None and next_rows > max_rows:
            raise CustomDataError(f"Upload rejected: CSV contains more than {max_rows:,} rows.")
        labels = None
        if "fraud_label" in chunk.columns:
            labels = pd.to_numeric(chunk["fraud_label"], errors="coerce")
        live = prepare_analysis_frame(chunk)
        if "fraud_label" in live.columns:
            raise CustomDataError("Fraud labels leaked into custom-data live scoring.")
        analyzed += int(len(chunk))
        if "hour_start" not in live.columns:
            continue
        timed = live.dropna(subset=["hour_start"])
        for hour, group in timed.groupby("hour_start", sort=True):
            key = str(hour)
            slot = hours.setdefault(
                key,
                {
                    "count": 0,
                    "amount": 0.0,
                    "has_amount": False,
                    "time_provenance": "DERIVED",
                    "time_kind": str(group["time_kind"].iloc[0])
                    if "time_kind" in group.columns
                    else "calendar",
                    "entities": {},
                    "label_count": 0,
                    "label_fraud": 0,
                },
            )
            slot["count"] += int(len(group))
            amount = _safe_amount_sum(group)
            if amount is not None:
                slot["amount"] += amount
                slot["has_amount"] = True
            if "time_provenance" in group.columns:
                slot["time_provenance"] = str(group["time_provenance"].iloc[0])
            if "time_kind" in group.columns:
                slot["time_kind"] = str(group["time_kind"].iloc[0])
            if labels is not None:
                window_labels = labels.loc[group.index]
                slot["label_count"] += int(window_labels.notna().sum())
                slot["label_fraud"] += int((window_labels == 1).sum())
            for role, _kind, provenance in ENTITY_ROLES:
                if role not in group.columns:
                    continue
                counts = group[role].dropna().astype(str).value_counts()
                counter: Counter[str] = slot["entities"].setdefault(role, Counter())
                if len(counter) < 5_000:
                    counter.update(counts.to_dict())
                    slot["entities"][f"{role}_provenance"] = provenance
    hourly_rows: list[dict[str, Any]] = []
    label_hours: dict[str, dict[str, Any]] = {}
    for hour, slot in hours.items():
        hour_key = str(hour)
        time_kind = str(slot.get("time_kind") or "calendar")
        row: dict[str, Any] = {
            "hour_start": hour_key,
            "time_kind": time_kind,
            "time_display": hour_display(hour_key, time_kind),
            "transaction_count": slot["count"],
            "amount_sum": slot["amount"] if slot["has_amount"] else None,
            "time_provenance": slot["time_provenance"],
        }
        for role, _kind, provenance in ENTITY_ROLES:
            counter = slot["entities"].get(role)
            if not isinstance(counter, Counter) or not counter:
                continue
            top_value, top_count = counter.most_common(1)[0]
            share = top_count / slot["count"] if slot["count"] else 0.0
            unique = len(counter)
            if unique > 1 and unique < slot["count"] and share >= ENTITY_SHARE:
                row[f"{role}_top"] = {
                    "value": top_value,
                    "share": share,
                    "unique": unique,
                    "provenance": slot["entities"].get(f"{role}_provenance") or provenance,
                }
        hourly_rows.append(row)
        if slot["label_count"]:
            label_hours[hour_key] = {
                "label": "USER-PROVIDED GROUND TRUTH",
                "fraud_count": slot["label_fraud"],
                "fraud_rate": slot["label_fraud"] / slot["count"] if slot["count"] else None,
                "used_as_detector_input": False,
                "used_as_model_feature": False,
                "note": (
                    "USER-PROVIDED GROUND TRUTH is evaluation only. "
                    "It is not a model feature and not the system's fraud decision."
                ),
            }
    hourly = pd.DataFrame(hourly_rows)
    anomalies, summary = _anomalies_from_hourly(hourly, analyzed=analyzed, limit=limit)
    summary["chunked"] = True
    return anomalies, summary, label_hours


def _anomalies_from_hourly(
    hourly: pd.DataFrame,
    analyzed: int,
    limit: int = 25,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    if not hourly.empty:
        hourly = hourly.copy()
        hourly["volume_z"] = _robust_z(hourly["transaction_count"])
        if hourly["amount_sum"].notna().any():
            hourly["amount_z"] = _robust_z(hourly["amount_sum"])
        else:
            hourly["amount_z"] = 0.0
        for row in hourly.to_dict("records"):
            signals: list[dict[str, Any]] = []
            kinds: list[str] = []
            volume_z = float(row.get("volume_z") or 0.0)
            amount_z = float(row.get("amount_z") or 0.0)
            count = int(row["transaction_count"])
            amount_sum = row.get("amount_sum")
            amount_value = (
                None
                if amount_sum is None or pd.isna(amount_sum)
                else float(amount_sum)
            )
            if volume_z >= VOLUME_Z and count >= MIN_TRANSACTIONS:
                signals.append(
                    {
                        "name": "elevated transaction volume",
                        "provenance": "DERIVED",
                        "detail": f"hour volume z={volume_z:.2f}",
                    }
                )
                kinds.append("Temporal anomaly")
            if amount_value is not None and amount_z >= AMOUNT_Z and count >= MIN_TRANSACTIONS:
                signals.append(
                    {
                        "name": "elevated transaction amount",
                        "provenance": "DERIVED",
                        "detail": f"hour amount z={amount_z:.2f}",
                    }
                )
                kinds.append("Amount concentration")
            for role, kind, _provenance in ENTITY_ROLES:
                packed = row.get(f"{role}_top")
                if isinstance(packed, dict):
                    signals.append(
                        {
                            "name": kind,
                            "provenance": packed.get("provenance"),
                            "detail": (
                                f"{role} {packed.get('value')} share "
                                f"{packed.get('share')}"
                            ),
                            "entity_role": role,
                            "entity_value": packed.get("value"),
                        }
                    )
                    kinds.append(kind)
            if not signals:
                continue
            hour = str(row["hour_start"])
            time_kind = str(
                row.get("time_kind")
                or ("relative_elapsed" if hour.startswith("relative-hour-") else "calendar")
            )
            display = str(row.get("time_display") or hour_display(hour, time_kind))
            if hour.startswith("relative-hour-"):
                anomaly_id = f"cda-rel-{hour.rsplit('-', 1)[-1]}"
            else:
                try:
                    anomaly_id = f"cda-{pd.Timestamp(hour):%Y%m%d-%H}"
                except (ValueError, TypeError):
                    anomaly_id = f"cda-{hour}"
            anomalies.append(
                {
                    "anomaly_id": anomaly_id,
                    "kind": kinds[0],
                    "kinds": kinds,
                    "world": WORLD,
                    "hour_start": hour,
                    "time_kind": time_kind,
                    "time_display": display,
                    "transactions": count,
                    "amount": amount_value,
                    "live_score": float(max(volume_z, amount_z)),
                    "signals": [item["name"] for item in signals],
                    "signal_details": signals,
                    "detection_inputs": (
                        "Only mapped available fields. User-provided labels were not used."
                    ),
                    "not_claimed": [
                        "live production detection",
                        "money saved",
                        "Razorpay payment action",
                    ],
                }
            )
    anomalies.sort(key=lambda item: item.get("live_score") or 0.0, reverse=True)
    anomalies = anomalies[:limit]
    summary = {
        "world": WORLD,
        "transactions_analyzed": analyzed,
        "temporal_anomalies": sum(1 for item in anomalies if "Temporal anomaly" in item["kinds"]),
        "amount_concentration_anomalies": sum(
            1 for item in anomalies if "Amount concentration" in item["kinds"]
        ),
        "entity_concentration_anomalies": sum(
            1
            for item in anomalies
            if any("concentration" in kind and kind != "Amount concentration" for kind in item["kinds"])
        ),
        "count": len(anomalies),
        "labels_used_as_detector_input": False,
        "hourly_context": [
            {
                "hour_start": str(row.get("hour_start")),
                "transaction_count": int(row["transaction_count"]),
                "amount_sum": (
                    None
                    if row.get("amount_sum") is None or pd.isna(row.get("amount_sum"))
                    else float(row["amount_sum"])
                ),
                "time_display": row.get("time_display"),
            }
            for row in (hourly.to_dict("records") if not hourly.empty else [])
        ],
    }
    return anomalies, summary


def build_evidence(
    anomaly: dict[str, Any],
    mapped: pd.DataFrame | None = None,
    label_overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    live: dict[str, Any] = {
        "transaction_count": {
            "value": anomaly.get("transactions"),
            "label": "OBSERVED",
            "source": "row count in the mapped time window",
        },
        "temporal_window": {
            "value": anomaly.get("time_display") or hour_display(
                str(anomaly.get("hour_start") or ""),
                str(anomaly.get("time_kind") or ""),
            ),
            "label": "DERIVED",
            "source": (
                "IEEE-CIS TransactionDT relative hour"
                if str(anomaly.get("time_kind")) == "relative_elapsed"
                else "floor(mapped timestamp to hour)"
            ),
        },
    }
    amount_value = anomaly.get("amount")
    if amount_value is not None and not pd.isna(amount_value):
        live["amount"] = {
            "value": amount_value,
            "label": "OBSERVED",
            "source": "mapped amount field",
        }
    for item in anomaly.get("signal_details") or []:
        live[item["name"]] = {
            "value": item.get("detail"),
            "label": item.get("provenance") or "DERIVED",
            "source": item.get("entity_role") or item.get("name"),
        }
    overlay = label_overlay
    if overlay is None and mapped is not None and "fraud_label" in mapped.columns and anomaly.get("hour_start"):
        labels = pd.to_numeric(mapped["fraud_label"], errors="coerce")
        work = prepare_analysis_frame(mapped)
        if "hour_start" in work.columns:
            hour = str(anomaly["hour_start"])
            mask = work["hour_start"].astype(str) == hour
            window_labels = labels.loc[mask]
            if window_labels.notna().any():
                fraud_count = int((window_labels == 1).sum())
                overlay = {
                    "label": "USER-PROVIDED GROUND TRUTH",
                    "fraud_count": fraud_count,
                    "fraud_rate": fraud_count / int(mask.sum()) if int(mask.sum()) else None,
                    "used_as_detector_input": False,
                    "used_as_model_feature": False,
                    "note": (
                        "USER-PROVIDED GROUND TRUTH is evaluation only. "
                        "It is not a model feature and not the system's fraud decision."
                    ),
                }
    return {
        "world": WORLD,
        "anomaly_id": anomaly.get("anomaly_id"),
        "kind": anomaly.get("kind"),
        "hour_start": anomaly.get("hour_start"),
        "time_kind": anomaly.get("time_kind"),
        "time_display": anomaly.get("time_display")
        or hour_display(str(anomaly.get("hour_start") or ""), str(anomaly.get("time_kind") or "")),
        "live_evidence": live,
        "evaluation_overlay": overlay,
        "signals": anomaly.get("signals") or [],
        "ieee_model_used": False,
    }
