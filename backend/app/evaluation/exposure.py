"""Held-out business-impact / exposure evaluation.

Observed activity only. Does not claim money saved, prevented, or avoided.
Does not execute actions, call APIs, or run the optional LLM.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from detection.scoring import SPIKE_TYPE_COORDINATED
from evaluation.labels import (
    LABEL_BACKGROUND,
    LABEL_COORDINATED,
    LABEL_FESTIVE,
    label_hour,
)
from evaluation.metrics import json_number, safe_divide
from evaluation.paths import (
    EVALUATION_SEED,
    HELDOUT_EXPOSURE_PATH,
    HELDOUT_META_PATH,
    HELDOUT_SPIKES_CSV_PATH,
    HELDOUT_TRANSACTIONS_PATH,
)
from tools.load import filter_window

CATEGORIES = (LABEL_COORDINATED, LABEL_FESTIVE, LABEL_BACKGROUND)
STATUSES = ("success", "failed", "declined")
VERDICTS = ("coordinated_abuse", "likely_festive", "inconclusive")
INVESTIGATION_METRICS_PATH = Path(__file__).resolve().parent / "investigation_metrics.json"

EXPOSURE_COLUMNS = (
    "transaction_id",
    "timestamp",
    "account_id",
    "device_id",
    "ip_address",
    "ip_subnet",
    "pincode",
    "sku_id",
    "amount",
    "transaction_status",
)

FORBIDDEN_IMPACT_KEYS = (
    "money_saved",
    "money_prevented",
    "losses_avoided",
    "loss_avoided",
    "avoided_loss",
    "revenue_protected",
    "roi",
    "roi_of_blocking",
)


def json_amount(value: object) -> float:
    return round(float(value), 2)


def load_exposure_transactions(path: Path = HELDOUT_TRANSACTIONS_PATH) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = [column for column in EXPOSURE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Held-out transactions missing columns: {missing}")
    out = frame.loc[:, list(EXPOSURE_COLUMNS)].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
    out["pincode"] = out["pincode"].astype(str)
    return out


def load_exposure_spikes(path: Path = HELDOUT_SPIKES_CSV_PATH) -> pd.DataFrame:
    spikes = pd.read_csv(path)
    spikes["window_start"] = pd.to_datetime(spikes["window_start"])
    spikes["window_end"] = pd.to_datetime(spikes["window_end"])
    return spikes


def assign_transaction_ground_truth(timestamp: object) -> str | None:
    """Hourly scenario-calendar label. None if the timestamp cannot be parsed."""
    stamp = pd.Timestamp(timestamp)
    if pd.isna(stamp):
        return None
    return label_hour(stamp.tz_localize(None) if stamp.tzinfo else stamp)


def label_transaction_hours(timestamps: pd.Series) -> tuple[list[str | None], int]:
    labels = [assign_transaction_ground_truth(value) for value in timestamps]
    unassigned = sum(1 for label in labels if label is None)
    return labels, unassigned


def half_open_mask(
    timestamps: pd.Series,
    window_start: object,
    window_end: object,
) -> pd.Series:
    start = pd.Timestamp(window_start)
    end = pd.Timestamp(window_end)
    stamps = pd.to_datetime(timestamps)
    return (stamps >= start) & (stamps < end)


def union_window_mask(
    timestamps: pd.Series,
    windows: list[tuple[pd.Timestamp, pd.Timestamp]],
) -> pd.Series:
    mask = pd.Series(False, index=timestamps.index)
    for start, end in windows:
        mask = mask | half_open_mask(timestamps, start, end)
    return mask


def overlapping_window_pairs(
    windows: list[tuple[pd.Timestamp, pd.Timestamp, str]],
) -> list[dict[str, str]]:
    overlaps: list[dict[str, str]] = []
    for index, (start_a, end_a, id_a) in enumerate(windows):
        for start_b, end_b, id_b in windows[index + 1 :]:
            if start_a < end_b and start_b < end_a:
                overlaps.append({"left": id_a, "right": id_b})
    return overlaps


def _status_amount(frame: pd.DataFrame, status: str) -> float:
    if frame.empty:
        return 0.0
    return json_amount(frame.loc[frame["transaction_status"] == status, "amount"].fillna(0).sum())


def _status_count(frame: pd.DataFrame, status: str) -> int:
    if frame.empty:
        return 0
    return int((frame["transaction_status"] == status).sum())


def _entity_counts(frame: pd.DataFrame) -> dict[str, int]:
    if frame.empty:
        return {
            "unique_accounts": 0,
            "unique_devices": 0,
            "unique_ip_addresses": 0,
            "unique_ip_subnets": 0,
            "unique_pincodes": 0,
            "unique_skus": 0,
        }
    return {
        "unique_accounts": int(frame["account_id"].nunique()),
        "unique_devices": int(frame["device_id"].nunique()),
        "unique_ip_addresses": int(frame["ip_address"].nunique()),
        "unique_ip_subnets": int(frame["ip_subnet"].nunique()),
        "unique_pincodes": int(frame["pincode"].nunique()),
        "unique_skus": int(frame["sku_id"].nunique()),
    }


def _amount_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "transaction_count": 0,
            "total_amount": 0.0,
            "mean_amount": None,
            "median_amount": None,
            "maximum_amount": None,
        }
    amounts = frame["amount"].dropna()
    return {
        "transaction_count": int(len(frame)),
        "total_amount": json_amount(amounts.sum()),
        "mean_amount": json_amount(amounts.mean()) if not amounts.empty else None,
        "median_amount": json_amount(amounts.median()) if not amounts.empty else None,
        "maximum_amount": json_amount(amounts.max()) if not amounts.empty else None,
    }


def _outcome_exposure(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        status: {
            "transaction_count": _status_count(frame, status),
            "total_amount": _status_amount(frame, status),
        }
        for status in STATUSES
    }


def _category_exposure(
    frame: pd.DataFrame,
    label: str,
    total_count: int,
    total_amount: float,
) -> dict[str, Any]:
    subset = frame.loc[frame["ground_truth"] == label]
    summary = _amount_summary(subset)
    success_amount = _status_amount(subset, "success")
    failed_amount = _status_amount(subset, "failed")
    declined_amount = _status_amount(subset, "declined")
    return {
        **summary,
        "transaction_share": json_number(safe_divide(summary["transaction_count"], total_count)),
        "amount_share": json_number(safe_divide(summary["total_amount"], total_amount)),
        "success_amount": success_amount,
        "failed_amount": failed_amount,
        "declined_amount": declined_amount,
        "failed_or_declined_amount": json_amount(failed_amount + declined_amount),
        "outcomes": _outcome_exposure(subset),
        "entities": _entity_counts(subset),
    }


def _spike_exposure(transactions: pd.DataFrame, row: pd.Series) -> dict[str, Any]:
    window = filter_window(transactions, row["window_start"], row["window_end"])
    summary = _amount_summary(window)
    return {
        "spike_id": str(row["spike_id"]),
        "detector_type": str(row["spike_type"]),
        "window_start": pd.Timestamp(row["window_start"]).strftime("%Y-%m-%dT%H:%M:%S"),
        "window_end": pd.Timestamp(row["window_end"]).strftime("%Y-%m-%dT%H:%M:%S"),
        **summary,
        "success_amount": _status_amount(window, "success"),
        "failed_amount": _status_amount(window, "failed"),
        "declined_amount": _status_amount(window, "declined"),
        **_entity_counts(window),
    }


def _windows_from_spikes(spikes: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    return [
        (pd.Timestamp(row["window_start"]), pd.Timestamp(row["window_end"]))
        for _, row in spikes.iterrows()
    ]


def _coverage_for_mask(frame: pd.DataFrame, mask: pd.Series, total_count: int, total_amount: float) -> dict[str, Any]:
    subset = frame.loc[mask]
    summary = _amount_summary(subset)
    return {
        **summary,
        "transaction_share": json_number(safe_divide(summary["transaction_count"], total_count)),
        "amount_share": json_number(safe_divide(summary["total_amount"], total_amount)),
    }


def _contains_forbidden_keys(payload: Any) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(token == lowered or token in lowered for token in FORBIDDEN_IMPACT_KEYS):
                found.append(str(key))
            found.extend(_contains_forbidden_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_contains_forbidden_keys(item))
    return found


def evaluate_heldout_exposure() -> dict[str, Any]:
    meta = json.loads(HELDOUT_META_PATH.read_text(encoding="utf-8"))
    seed = int(meta["seed"])
    if seed != EVALUATION_SEED:
        raise ValueError(f"Exposure evaluation requires held-out seed {EVALUATION_SEED}, got {seed}")

    transactions = load_exposure_transactions()
    if "event_type" in transactions.columns or "fraud_label" in transactions.columns:
        raise ValueError("Exposure working frame must not carry event_type or fraud_label")

    labels, unassigned = label_transaction_hours(transactions["timestamp"])
    transactions = transactions.assign(ground_truth=labels)
    assigned = transactions.loc[transactions["ground_truth"].notna()].copy()

    overall = _amount_summary(assigned)
    total_count = overall["transaction_count"]
    total_amount = float(overall["total_amount"])

    by_category = {
        label: _category_exposure(assigned, label, total_count, total_amount)
        for label in CATEGORIES
    }

    spikes = load_exposure_spikes()
    spike_window_ids = [
        (pd.Timestamp(row["window_start"]), pd.Timestamp(row["window_end"]), str(row["spike_id"]))
        for _, row in spikes.iterrows()
    ]
    overlaps = overlapping_window_pairs(spike_window_ids)
    all_windows = _windows_from_spikes(spikes)
    inside_any = union_window_mask(assigned["timestamp"], all_windows)

    coverage = _coverage_for_mask(assigned, inside_any, total_count, total_amount)
    coverage_by_category = {
        label: _coverage_for_mask(
            assigned,
            inside_any & (assigned["ground_truth"] == label),
            int(by_category[label]["transaction_count"]),
            float(by_category[label]["total_amount"]),
        )
        for label in CATEGORIES
    }

    coordinated = assigned.loc[assigned["ground_truth"] == LABEL_COORDINATED]
    coordinated_spikes = spikes.loc[spikes["spike_type"] == SPIKE_TYPE_COORDINATED]
    inside_coord_spikes = union_window_mask(
        assigned["timestamp"],
        _windows_from_spikes(coordinated_spikes),
    )
    captured_coord = assigned.loc[inside_coord_spikes & (assigned["ground_truth"] == LABEL_COORDINATED)]
    coord_tx = int(len(coordinated))
    coord_amount = float(_amount_summary(coordinated)["total_amount"])
    captured_tx = int(len(captured_coord))
    captured_amount = float(_amount_summary(captured_coord)["total_amount"])

    surfaced = assigned.loc[inside_any]
    non_coordinated = surfaced.loc[surfaced["ground_truth"] != LABEL_COORDINATED]
    surfaced_count = int(len(surfaced))
    surfaced_amount = float(_amount_summary(surfaced)["total_amount"])
    non_coord_summary = _amount_summary(non_coordinated)
    non_coord_by_category = {
        label: _amount_summary(non_coordinated.loc[non_coordinated["ground_truth"] == label])
        for label in (LABEL_FESTIVE, LABEL_BACKGROUND)
    }

    per_spike = [_spike_exposure(assigned, row) for _, row in spikes.iterrows()]
    spike_index = {item["spike_id"]: item for item in per_spike}

    investigation_join: dict[str, Any]
    if INVESTIGATION_METRICS_PATH.is_file():
        investigation = json.loads(INVESTIGATION_METRICS_PATH.read_text(encoding="utf-8"))
        cases = list(investigation.get("cases") or [])
        by_verdict: dict[str, dict[str, Any]] = {}
        for verdict in VERDICTS:
            ids = [str(case["spike_id"]) for case in cases if case.get("actual_verdict") == verdict]
            verdict_spikes = spikes.loc[spikes["spike_id"].astype(str).isin(ids)]
            union = assigned.loc[union_window_mask(assigned["timestamp"], _windows_from_spikes(verdict_spikes))]
            by_verdict[verdict] = {
                "n_spikes": len(ids),
                **_amount_summary(union),
            }
        detector_coord_ids = [str(value) for value in coordinated_spikes["spike_id"].tolist()]
        investigator_coord_ids = [
            str(case["spike_id"])
            for case in cases
            if case.get("actual_verdict") == "coordinated_abuse"
        ]
        investigation_join = {
            "source": "evaluation/investigation_metrics.json",
            "note": "Descriptive only. Investigation verdicts are not ground truth.",
            "by_verdict": by_verdict,
            "detector_coordinated_spikes": {
                "n_spikes": int(len(detector_coord_ids)),
                "spike_ids": detector_coord_ids,
                **_amount_summary(
                    assigned.loc[union_window_mask(assigned["timestamp"], _windows_from_spikes(coordinated_spikes))]
                ),
            },
            "investigator_coordinated_verdicts": {
                "n_spikes": int(len(investigator_coord_ids)),
                "spike_ids": investigator_coord_ids,
                **_amount_summary(
                    assigned.loc[
                        union_window_mask(
                            assigned["timestamp"],
                            _windows_from_spikes(spikes.loc[spikes["spike_id"].astype(str).isin(investigator_coord_ids)]),
                        )
                    ]
                ),
            },
        }
    else:
        investigation_join = {"source": None, "note": "Step 4 investigation artifact was not found"}

    report: dict[str, Any] = {
        "seed": seed,
        "evaluation_unit": "held-out transaction; spike coverage uses detected-spike half-open windows",
        "claim": "observed_exposure_only",
        "not_calculated": list(FORBIDDEN_IMPACT_KEYS),
        "ground_truth": {
            "source": "Step 3 scenario calendars via transaction hour",
            "not_used": ["detector spike_type", "event_type", "fraud_label as category"],
            "unassigned_timestamps": unassigned,
        },
        "overall": overall,
        "by_category": by_category,
        "detected_spikes": {
            "n_spikes": int(len(spikes)),
            "overlapping_window_pairs": overlaps,
            "overlap_count": len(overlaps),
            "per_spike": per_spike,
        },
        "detected_spike_coverage": {
            "union_semantics": "half-open window_start <= timestamp < window_end; overlapping spikes are de-duplicated",
            "inside_any_detected_spike": coverage,
            "inside_any_detected_spike_by_ground_truth": coverage_by_category,
        },
        "coordinated_capture": {
            "denominator": "scenario-calendar coordinated_abuse transactions",
            "total_coordinated_transactions": coord_tx,
            "total_coordinated_amount": json_amount(coord_amount),
            "captured_transactions": captured_tx,
            "captured_amount": json_amount(captured_amount),
            "transaction_capture_rate": json_number(safe_divide(captured_tx, coord_tx)),
            "amount_capture_rate": json_number(safe_divide(captured_amount, coord_amount)),
        },
        "non_coordinated_surfaced_exposure": {
            "terminology": "activity inside detected spikes that is not coordinated-abuse ground truth",
            "transaction_count": non_coord_summary["transaction_count"],
            "total_amount": non_coord_summary["total_amount"],
            "share_of_detected_spike_transactions": json_number(
                safe_divide(non_coord_summary["transaction_count"], surfaced_count)
            ),
            "share_of_detected_spike_amount": json_number(
                safe_divide(float(non_coord_summary["total_amount"]), surfaced_amount)
            ),
            "by_category": {
                LABEL_FESTIVE: {
                    "label": "surfaced legitimate festive exposure",
                    **non_coord_by_category[LABEL_FESTIVE],
                },
                LABEL_BACKGROUND: {
                    "label": "surfaced background exposure",
                    **non_coord_by_category[LABEL_BACKGROUND],
                },
            },
        },
        "entity_impact": {
            "note": "An entity may appear in more than one category; category counts are not additive.",
            "coordinated_abuse": by_category[LABEL_COORDINATED]["entities"],
            "legitimate_festive": by_category[LABEL_FESTIVE]["entities"],
            "background": by_category[LABEL_BACKGROUND]["entities"],
        },
        "payment_outcomes": {
            "note": "Uses explicit transaction_status values only.",
            "coordinated_abuse": by_category[LABEL_COORDINATED]["outcomes"],
            "legitimate_festive": by_category[LABEL_FESTIVE]["outcomes"],
            "background": by_category[LABEL_BACKGROUND]["outcomes"],
        },
        "investigation_comparison": investigation_join,
        "data_quality": {
            "heldout_meta_transactions": int(meta["n_transactions"]),
            "loaded_transactions": int(len(transactions)),
            "assigned_transactions": total_count,
            "unassigned_timestamps": unassigned,
        },
    }
    forbidden = _contains_forbidden_keys(report)
    if forbidden:
        raise ValueError(f"Exposure report must not include intervention-impact keys: {forbidden}")
    return report


def write_exposure_report(
    report: dict[str, Any] | None = None,
    output_path: Path | None = None,
) -> Path:
    payload = report if report is not None else evaluate_heldout_exposure()
    dest = output_path or HELDOUT_EXPOSURE_PATH
    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return dest


def write_exposure_markdown(report: dict[str, Any], output_path: Path) -> Path:
    overall = report["overall"]
    capture = report["coordinated_capture"]
    coverage = report["detected_spike_coverage"]["inside_any_detected_spike"]
    surfaced = report["non_coordinated_surfaced_exposure"]
    lines = [
        "# Phase 7 Step 5 — Exposure evaluation",
        "",
        "Held-out seed **2027** only. Observed exposure. Not money saved, prevented, or avoided.",
        "",
        f"- Transactions: {overall['transaction_count']}",
        f"- Observed amount: {overall['total_amount']}",
        f"- Mean / median / max amount: {overall['mean_amount']} / {overall['median_amount']} / {overall['maximum_amount']}",
        "",
        "## Exposure by ground-truth category",
        "",
        "| Category | Transactions | Tx share | Amount | Amount share |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, row in report["by_category"].items():
        lines.append(
            f"| {label} | {row['transaction_count']} | {row['transaction_share']} | "
            f"{row['total_amount']} | {row['amount_share']} |"
        )
    lines.extend(
        [
            "",
            "## Detected-spike coverage",
            "",
            f"- Transactions inside any detected spike: {coverage['transaction_count']} ({coverage['transaction_share']})",
            f"- Amount inside any detected spike: {coverage['total_amount']} ({coverage['amount_share']})",
            f"- Overlapping spike window pairs: {report['detected_spikes']['overlap_count']}",
            "",
            "## Coordinated-abuse capture",
            "",
            f"- Calendar coordinated transactions: {capture['total_coordinated_transactions']}",
            f"- Calendar coordinated amount: {capture['total_coordinated_amount']}",
            f"- Inside detected coordinated spikes: {capture['captured_transactions']} txs / {capture['captured_amount']}",
            f"- Transaction capture rate: {capture['transaction_capture_rate']}",
            f"- Amount capture rate: {capture['amount_capture_rate']}",
            "",
            "## Non-coordinated surfaced exposure",
            "",
            f"- Transactions: {surfaced['transaction_count']} ({surfaced['share_of_detected_spike_transactions']} of detected-spike txs)",
            f"- Amount: {surfaced['total_amount']} ({surfaced['share_of_detected_spike_amount']} of detected-spike amount)",
            f"- Surfaced legitimate festive: {surfaced['by_category']['legitimate_festive']['transaction_count']} txs / {surfaced['by_category']['legitimate_festive']['total_amount']}",
            f"- Surfaced background: {surfaced['by_category']['background']['transaction_count']} txs / {surfaced['by_category']['background']['total_amount']}",
            "",
            "## Entity impact",
            "",
            "Category-specific unique-entity counts are not additive.",
            "",
        ]
    )
    entities = report["entity_impact"]
    lines.append("| Category | Accounts | Devices | Subnets | Pincodes | SKUs |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for label in ("coordinated_abuse", "legitimate_festive", "background"):
        row = entities[label]
        lines.append(
            f"| {label} | {row['unique_accounts']} | {row['unique_devices']} | "
            f"{row['unique_ip_subnets']} | {row['unique_pincodes']} | {row['unique_skus']} |"
        )
    comparison = report["investigation_comparison"]
    lines.extend(
        [
            "",
            "## Detector vs investigator (descriptive)",
            "",
            f"- Detector coordinated spikes: {comparison['detector_coordinated_spikes']['n_spikes']} "
            f"/ {comparison['detector_coordinated_spikes']['transaction_count']} txs / "
            f"{comparison['detector_coordinated_spikes']['total_amount']}",
            f"- Investigator coordinated_abuse verdicts: {comparison['investigator_coordinated_verdicts']['n_spikes']} "
            f"/ {comparison['investigator_coordinated_verdicts']['transaction_count']} txs / "
            f"{comparison['investigator_coordinated_verdicts']['total_amount']}",
            "",
            "Investigation verdicts are not ground truth. No intervention was executed.",
            "",
            "Run: `python -m evaluation.exposure`",
            "",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    report = evaluate_heldout_exposure()
    json_path = write_exposure_report(report)
    md_path = write_exposure_markdown(
        report,
        Path(__file__).resolve().parent.parent / "docs" / "phase-7-exposure.md",
    )
    printable = {key: value for key, value in report.items() if key != "detected_spikes"}
    printable["detected_spikes"] = {
        "n_spikes": report["detected_spikes"]["n_spikes"],
        "overlap_count": report["detected_spikes"]["overlap_count"],
        "overlapping_window_pairs": report["detected_spikes"]["overlapping_window_pairs"],
    }
    print(json.dumps(printable, indent=2))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
