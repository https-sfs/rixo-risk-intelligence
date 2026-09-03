"""Dataset inspection for an uploaded CSV. Reports only what is present."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.custom_data import WORLD
from evaluation.custom_data.mapping import high_confidence_mapping, propose_mappings, summarize_proposals
from evaluation.custom_data.schema import REQUIRED_USEFUL, CustomDataError
from evaluation.custom_data.stream import iter_csv_chunks, read_columns
from models.ieee_fraud.features import discover_feature_columns
from models.ieee_fraud.predict import RECENT_PCA

UNIQUE_CAP = 50_000


def _missingness(frame: pd.DataFrame, limit: int = 12) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in frame.columns:
        missing = int(frame[name].isna().sum())
        if missing == 0:
            empty = frame[name].astype(str).str.strip().isin({"", "nan", "None", "NULL"})
            missing = int(empty.sum())
        rate = missing / len(frame) if len(frame) else 0.0
        rows.append({"column": str(name), "missing": missing, "missing_rate": rate})
    rows.sort(key=lambda item: item["missing_rate"], reverse=True)
    return rows[:limit]


def inspect_schema(path: str | Path, filename: str) -> dict[str, Any]:
    """Header-only inspect. Does not scan rows or load the CSV body."""
    columns = read_columns(path)
    proposals = propose_mappings(columns)
    suggested = high_confidence_mapping(proposals)
    summary = summarize_proposals(proposals)
    ieee_official = discover_feature_columns(columns)
    lowercase_pca = [name for name in columns if RECENT_PCA.fullmatch(str(name))]
    return {
        "world": WORLD,
        "filename": filename,
        "schema_only": True,
        "inspected_in_chunks": False,
        "rows": None,
        "columns": columns,
        "column_count": len(columns),
        "amount_coverage": None,
        "timestamp_coverage": None,
        "timestamp_kind": (
            "elapsed_seconds" if suggested.get("timestamp") == "TransactionDT" else None
        ),
        "duplicate_row_count": None,
        "duplicate_id_count": None,
        "missingness": [],
        "detected_candidate_fields": suggested,
        "fraud_label_available": "fraud_label" in suggested,
        "fraud_label_column": suggested.get("fraud_label"),
        "identity_entity_coverage": {},
        "ieee_official_columns": ieee_official,
        "january_style_pca_columns": lowercase_pca,
        "minimum_useful_fields": list(REQUIRED_USEFUL),
        "mapping_summary": summary,
        "isolation": {
            "mixed_with_benchmarks": False,
            "modifies_seed_42": False,
            "modifies_ieee_cis": False,
            "modifies_january_2026": False,
            "labels_invented": False,
        },
    }


def inspect_frame(frame: pd.DataFrame, filename: str) -> dict[str, Any]:
    columns = [str(name) for name in frame.columns]
    proposals = propose_mappings(columns)
    suggested = high_confidence_mapping(proposals)
    amount_col = suggested.get("amount")
    time_col = suggested.get("timestamp")
    id_col = suggested.get("transaction_id")
    label_col = suggested.get("fraud_label")
    amount_coverage = None
    if amount_col and amount_col in frame.columns:
        numeric = pd.to_numeric(frame[amount_col], errors="coerce")
        amount_coverage = float(numeric.notna().mean())
    timestamp_coverage = None
    timestamp_kind = None
    if time_col and time_col in frame.columns:
        if time_col == "TransactionDT":
            numeric = pd.to_numeric(frame[time_col], errors="coerce")
            timestamp_coverage = float(numeric.notna().mean())
            timestamp_kind = "elapsed_seconds"
        else:
            parsed = pd.to_datetime(frame[time_col], errors="coerce")
            timestamp_coverage = float(parsed.notna().mean())
            timestamp_kind = "calendar" if timestamp_coverage else None
    duplicate_rows = int(frame.duplicated().sum())
    duplicate_ids = None
    if id_col and id_col in frame.columns:
        duplicate_ids = int(frame[id_col].duplicated().sum())
    entity_fields = {
        key: suggested[key]
        for key in ("account_id", "device_id", "ip_address", "merchant", "product_sku")
        if suggested.get(key)
    }
    entity_coverage = {}
    for role, column in entity_fields.items():
        series = frame[column]
        nunique = int(series.nunique(dropna=True))
        entity_coverage[role] = {
            "column": column,
            "unique": nunique,
            "coverage": float(series.notna().mean()),
            "repeatable": nunique < len(frame) and nunique > 1,
        }
    ieee_official = discover_feature_columns(columns)
    lowercase_pca = [name for name in columns if RECENT_PCA.fullmatch(str(name))]
    return {
        "world": WORLD,
        "filename": filename,
        "rows": int(len(frame)),
        "columns": columns,
        "column_count": len(columns),
        "amount_coverage": amount_coverage,
        "timestamp_coverage": timestamp_coverage,
        "timestamp_kind": timestamp_kind,
        "duplicate_row_count": duplicate_rows,
        "duplicate_id_count": duplicate_ids,
        "missingness": _missingness(frame),
        "detected_candidate_fields": suggested,
        "fraud_label_available": bool(label_col),
        "fraud_label_column": label_col,
        "identity_entity_coverage": entity_coverage,
        "ieee_official_columns": ieee_official,
        "january_style_pca_columns": lowercase_pca,
        "minimum_useful_fields": list(REQUIRED_USEFUL),
        "isolation": {
            "mixed_with_benchmarks": False,
            "modifies_seed_42": False,
            "modifies_ieee_cis": False,
            "modifies_january_2026": False,
            "labels_invented": False,
        },
    }


def inspect_path(path: str | Path, filename: str, max_rows: int) -> dict[str, Any]:
    """Inspect a CSV in chunks. Stops and fails closed if row limit is exceeded."""
    columns = read_columns(path)
    proposals = propose_mappings(columns)
    suggested = high_confidence_mapping(proposals)
    amount_col = suggested.get("amount")
    time_col = suggested.get("timestamp")
    id_col = suggested.get("transaction_id")
    label_col = suggested.get("fraud_label")
    entity_roles = {
        key: suggested[key]
        for key in ("account_id", "device_id", "ip_address", "merchant", "product_sku")
        if suggested.get(key)
    }

    rows = 0
    missing = defaultdict(int)
    amount_present = 0
    time_present = 0
    timestamp_kind = None
    duplicate_rows = 0
    seen_ids: set[str] | None = set() if id_col else None
    duplicate_ids = 0
    entity_uniques: dict[str, set[str]] = {role: set() for role in entity_roles}
    entity_capped = {role: False for role in entity_roles}
    entity_present = defaultdict(int)

    for chunk in iter_csv_chunks(path):
        next_rows = rows + int(len(chunk))
        if next_rows > max_rows:
            raise CustomDataError(f"Upload rejected: CSV contains more than {max_rows:,} rows.")
        rows = next_rows
        duplicate_rows += int(chunk.duplicated().sum())
        for name in columns:
            if name in chunk.columns:
                missing[name] += int(chunk[name].isna().sum())
        if amount_col and amount_col in chunk.columns:
            amount_present += int(pd.to_numeric(chunk[amount_col], errors="coerce").notna().sum())
        if time_col and time_col in chunk.columns:
            if time_col == "TransactionDT" or pd.api.types.is_numeric_dtype(chunk[time_col]):
                time_present += int(pd.to_numeric(chunk[time_col], errors="coerce").notna().sum())
                timestamp_kind = "elapsed_seconds"
            else:
                parsed = pd.to_datetime(chunk[time_col], errors="coerce")
                time_present += int(parsed.notna().sum())
                if timestamp_kind is None:
                    timestamp_kind = "calendar"
        if seen_ids is not None and id_col in chunk.columns:
            values = chunk[id_col].dropna().astype(str)
            duplicate_ids += int(values.duplicated().sum())
            for value in values:
                if value in seen_ids:
                    duplicate_ids += 1
                elif len(seen_ids) < UNIQUE_CAP:
                    seen_ids.add(value)
        for role, column in entity_roles.items():
            series = chunk[column].dropna().astype(str)
            entity_present[role] += int(len(series))
            bucket = entity_uniques[role]
            if entity_capped[role]:
                continue
            for value in series.unique():
                bucket.add(str(value))
                if len(bucket) >= UNIQUE_CAP:
                    entity_capped[role] = True
                    break

    if rows == 0:
        raise CustomDataError("The CSV has no rows or columns.")

    missingness = [
        {"column": name, "missing": missing[name], "missing_rate": missing[name] / rows}
        for name in columns
    ]
    missingness.sort(key=lambda item: item["missing_rate"], reverse=True)
    entity_coverage = {}
    for role, column in entity_roles.items():
        unique = len(entity_uniques[role])
        entity_coverage[role] = {
            "column": column,
            "unique": unique,
            "unique_capped": entity_capped[role],
            "coverage": entity_present[role] / rows if rows else 0.0,
            "repeatable": unique < rows and unique > 1,
        }
    ieee_official = discover_feature_columns(columns)
    lowercase_pca = [name for name in columns if RECENT_PCA.fullmatch(str(name))]
    return {
        "world": WORLD,
        "filename": filename,
        "rows": rows,
        "columns": columns,
        "column_count": len(columns),
        "amount_coverage": (amount_present / rows) if amount_col else None,
        "timestamp_coverage": (time_present / rows) if time_col else None,
        "timestamp_kind": timestamp_kind,
        "duplicate_row_count": duplicate_rows,
        "duplicate_id_count": duplicate_ids if id_col else None,
        "missingness": missingness[:12],
        "detected_candidate_fields": suggested,
        "fraud_label_available": bool(label_col),
        "fraud_label_column": label_col,
        "identity_entity_coverage": entity_coverage,
        "ieee_official_columns": ieee_official,
        "january_style_pca_columns": lowercase_pca,
        "minimum_useful_fields": list(REQUIRED_USEFUL),
        "inspected_in_chunks": True,
        "isolation": {
            "mixed_with_benchmarks": False,
            "modifies_seed_42": False,
            "modifies_ieee_cis": False,
            "modifies_january_2026": False,
            "labels_invented": False,
        },
    }
