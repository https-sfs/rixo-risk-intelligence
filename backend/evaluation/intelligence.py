"""Investigation intelligence from existing evidence and small hourly artifacts.

Does not scan ledgers. Does not invent metrics, money-saved claims, or identities.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from evaluation.paths import HELDOUT_DIR
from tools.paths import DATA_DIR, HOURLY_WINDOWS_PATH, REPO_ROOT

SYNTHETIC_WORLD = "SYNTHETIC SCENARIO"
IEEE_WORLD = "REAL PUBLIC DATA"
JANUARY_WORLD = "RECENT PUBLIC DATA"
BYOD_WORLD = "BRING YOUR DATA"

OBSERVED = "OBSERVED"
DERIVED = "DERIVED"
BASELINE = "BASELINE"
EVALUATION = "EVALUATION"
SCENARIO = "SCENARIO ASSUMPTION"
MODEL = "MODEL PREDICTION"

STATUS_UNSUPPORTED = "UNAVAILABLE"
STATUS_LIMITED = "LIMITED"
STATUS_TRANSFERRED = "TRANSFERRED"
STATUS_CONTEXTUAL = "CONTEXTUAL"
STATUS_SUPPORTED = "SUPPORTED"
FEATURE_COVERAGE_LIMIT = 0.05

CLASSIFIER_EVIDENCE_KIND = "evidence_quality"

HELD_OUT_DETECTION = HELDOUT_DIR / "detection_metrics.json"
INVESTIGATION_METRICS = REPO_ROOT / "evaluation" / "investigation_metrics.json"
IEEE_HOURLY = DATA_DIR / "real" / "hourly_metrics.csv"
IEEE_EVALUATION = DATA_DIR / "real" / "evaluation.json"
JANUARY_HOURLY = DATA_DIR / "real_2026" / "hourly_metrics.csv"
JANUARY_EVALUATION = DATA_DIR / "real_2026" / "evaluation.json"
IEEE_MODEL_EVAL = DATA_DIR / "real" / "model" / "model_evaluation.json"

NEIGHBOR_HOURS = 6


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _int(value: Any) -> int | None:
    number = _num(value)
    return None if number is None else int(number)


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _metric(value: Any, *, provenance: str, source: str, status: str = "available") -> dict[str, Any]:
    return {
        "value": value,
        "provenance": provenance,
        "source": source,
        "evaluation_status": status,
    }


@lru_cache(maxsize=8)
def _read_hourly_csv(path: str) -> tuple[tuple[str, ...], tuple[tuple[Any, ...], ...]]:
    frame = pd.read_csv(path)
    columns = tuple(str(name) for name in frame.columns)
    rows = tuple(tuple(row) for row in frame.itertuples(index=False, name=None))
    return columns, rows


def _hourly_frame(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    columns, rows = _read_hourly_csv(str(path.resolve()))
    return pd.DataFrame(list(rows), columns=list(columns))


def _evidence_quality_policy(**flags: Any) -> dict[str, Any]:
    """Shared invariants for classifier evidence status. Not a fraud or action verdict."""
    return {
        "kind": CLASSIFIER_EVIDENCE_KIND,
        "not_a_fraud_verdict": True,
        "not_a_governance_authorization": True,
        "not_an_approval": True,
        "not_an_execution_permit": True,
        "used_for_action_selection": False,
        "coverage_not_upgraded_by_scored_rows": True,
        "not_fraud_confirmed": True,
        "not_the_anomaly_detector": True,
        "not_the_action_decision": True,
        **flags,
    }


def classifier_evidence_status(
    classifier: dict[str, Any] | None,
    *,
    world: str,
    sample_scope: str | None = None,
) -> dict[str, Any]:
    """Map existing classifier fields to an evidence-quality status.

    Coverage quality is independent of scored-row count and fraud-risk score.
    Status never authorizes an action, approval, or simulation.
    """
    block = _as_record(classifier)
    status = str(block.get("status") or "")
    coverage = _num(block.get("feature_coverage"))
    scored_rows = _int(block.get("scored_rows"))
    high_risk = _int(block.get("high_risk_count"))
    scope = sample_scope or (str(block.get("sample_scope")) if block.get("sample_scope") else None)
    missing = block.get("features_unavailable") or block.get("missing_features") or []
    low_coverage = coverage is not None and coverage < FEATURE_COVERAGE_LIMIT
    if status != "scored":
        return {
            "status": STATUS_UNSUPPORTED,
            "headline": "MODEL EVIDENCE: UNAVAILABLE",
            "detail": str(block.get("reason") or "Classifier output was not scored for this case. This is not model support."),
            "feature_coverage": coverage,
            "model": block.get("model"),
            "model_version": block.get("model_version"),
            "sample_scope": scope,
            "world": world,
            "provenance": MODEL,
            **_evidence_quality_policy(not_model_support=True, applied_outside_native_world=world != IEEE_WORLD),
        }
    if scope == "IN_SAMPLE_MODEL_OVERLAY":
        label, headline, detail = (
            STATUS_CONTEXTUAL,
            "MODEL EVIDENCE: CONTEXTUAL",
            "IN_SAMPLE_MODEL_OVERLAY — supporting evidence for this investigation. It is not held-out test performance, not model accuracy, and not production performance.",
        )
        extras = _evidence_quality_policy(
            not_held_out_test_performance=True,
            not_model_accuracy=True,
            applied_outside_native_world=False,
            not_reliable_native_evidence=True,
        )
    elif world != IEEE_WORLD:
        if low_coverage:
            label, headline, detail = (
                STATUS_LIMITED,
                "MODEL EVIDENCE: LIMITED",
                "The shared IEEE-CIS classifier was applied outside its native training and evaluation world with low feature coverage. Score calibration is not established here. Scored-row count does not upgrade LIMITED coverage. This is not reliable native model evidence.",
            )
            extras = _evidence_quality_policy(
                not_model_support=False,
                not_reliable_native_evidence=True,
                applied_outside_native_world=True,
                native_training_world=IEEE_WORLD,
            )
        else:
            label, headline, detail = (
                STATUS_TRANSFERRED,
                "MODEL EVIDENCE: TRANSFERRED",
                "The shared IEEE-CIS classifier was applied outside its native training and evaluation world. It is supporting evidence only. A high score is not a fraud confirmation.",
            )
            extras = _evidence_quality_policy(
                not_reliable_native_evidence=True,
                applied_outside_native_world=True,
                native_training_world=IEEE_WORLD,
            )
    elif low_coverage:
        label, headline, detail = (
            STATUS_LIMITED,
            "MODEL EVIDENCE: LIMITED",
            "Native IEEE-CIS scoring has low feature coverage on this window. Scored-row count does not upgrade LIMITED coverage. This is not reliable native model evidence.",
        )
        extras = _evidence_quality_policy(
            not_reliable_native_evidence=True,
            applied_outside_native_world=False,
        )
    else:
        label, headline, detail = (
            STATUS_SUPPORTED,
            "MODEL EVIDENCE: SUPPORTED",
            "Native IEEE-CIS classifier output is available as supporting evidence. It is not the anomaly detector and not a payment decision.",
        )
        extras = _evidence_quality_policy(
            not_reliable_native_evidence=False,
            applied_outside_native_world=False,
            native_ieee=True,
        )
    return {
        "status": label,
        "headline": headline,
        "detail": detail,
        "feature_coverage": coverage,
        "scored_rows": scored_rows,
        "high_risk_count": high_risk,
        "operating_threshold": _num(block.get("operating_threshold")),
        "fraud_risk_score": _num(block.get("fraud_risk_score")),
        "classification": block.get("classification"),
        "model": block.get("model"),
        "model_version": block.get("model_version"),
        "sample_scope": scope,
        "features_unavailable_count": len(missing) if isinstance(missing, list) else None,
        "world": world,
        "provenance": MODEL,
        **extras,
    }


def false_positive_impact(
    *,
    transaction_count: int | None,
    high_risk_count: int | None,
    recommended_action: str | None,
    labelled_fraud_count: int | None = None,
) -> dict[str, Any]:
    """Operational false-positive interpretation. No money-saved claims."""
    review_count = high_risk_count if high_risk_count else transaction_count
    action = str(recommended_action or "review")
    impacts = [
        f"Unnecessary human review of about {review_count} transactions in this window."
        if review_count
        else "Unnecessary human review of this window.",
        "Possible customer friction if a live review or rule change were later applied.",
        "Possible operational workload for the risk team.",
        "Possible merchant investigation of this window.",
    ]
    if action in {"monitor", "monitor_only", "take_no_simulated_action", "no_action"}:
        note = (
            "The current recommendation is monitor-only, so a false positive would mainly "
            "create investigation time rather than a simulated rule change."
        )
    else:
        note = (
            "If this case is a false positive, the recommended review or rule tightening "
            "would be unnecessary work."
        )
    payload: dict[str, Any] = {
        "kind": "operational_scenario",
        "provenance": SCENARIO,
        "source": "investigation window counts and recommended action",
        "evaluation_status": "scenario_assumption",
        "monetary_estimate": None,
        "not_money_saved": True,
        "not_loss_avoided": True,
        "headline": "Potential false-positive impact",
        "note": note,
        "impacts": impacts,
        "review_workload": _metric(review_count, provenance=DERIVED, source="high_risk_count or window volume"),
    }
    if labelled_fraud_count is not None:
        payload["labelled_fraud_count"] = _metric(
            labelled_fraud_count,
            provenance=EVALUATION,
            source="delayed / user-provided labels; not a live decision input",
            status="evaluation_only",
        )
    return payload


def _neighbors(
    frame: pd.DataFrame,
    *,
    key: str,
    target: Any,
    count_col: str,
    amount_col: str | None,
    intensity_col: str | None,
    window: int = NEIGHBOR_HOURS,
) -> list[dict[str, Any]]:
    if key not in frame.columns or frame.empty:
        return []
    work = frame.copy()
    if key == "window_start" or "time" in key or "hour_start" in key:
        parsed = pd.to_datetime(work[key], errors="coerce")
        if parsed.notna().any():
            work["_sort"] = parsed
        else:
            work["_sort"] = pd.to_numeric(work[key], errors="coerce")
    else:
        work["_sort"] = pd.to_numeric(work[key], errors="coerce")
    work = work.dropna(subset=["_sort"]).sort_values("_sort")
    if work.empty:
        return []
    if pd.api.types.is_datetime64_any_dtype(work["_sort"]):
        want = pd.Timestamp(target)
        loc = int((work["_sort"] - want).abs().to_numpy().argmin())
    else:
        want = float(target)
        loc = int((work["_sort"] - want).abs().to_numpy().argmin())
    start = max(0, loc - window)
    end = min(len(work), loc + window + 1)
    slice_ = work.iloc[start:end]
    rows: list[dict[str, Any]] = []
    for offset, (_, item) in enumerate(slice_.iterrows()):
        stamp = item[key]
        if hasattr(stamp, "isoformat"):
            stamp = stamp.isoformat()
        rows.append(
            {
                "label": str(stamp),
                "transaction_count": _int(item.get(count_col)),
                "amount": _num(item.get(amount_col)) if amount_col and amount_col in item.index else None,
                "intensity": _num(item.get(intensity_col)) if intensity_col and intensity_col in item.index else None,
                "is_selected": (start + offset) == loc,
            }
        )
    return rows


def temporal_breakdown(
    *,
    world: str,
    selected_label: str,
    selected_count: int | None,
    selected_amount: float | None,
    selected_intensity: float | None,
    neighbors: list[dict[str, Any]],
    baseline_note: str | None,
    unavailable: str | None = None,
) -> dict[str, Any]:
    if unavailable:
        return {
            "available": False,
            "reason": unavailable,
            "provenance": DERIVED,
            "source": "hourly artifact",
        }
    return {
        "available": True,
        "provenance": DERIVED,
        "source": "precomputed hourly artifact; not a ledger dump",
        "selected": {
            "label": selected_label,
            "transaction_count": _metric(selected_count, provenance=OBSERVED, source="window row count"),
            "amount": _metric(selected_amount, provenance=OBSERVED, source="window amount sum")
            if selected_amount is not None
            else None,
            "intensity": _metric(selected_intensity, provenance=DERIVED, source="detector live score or volume ratio")
            if selected_intensity is not None
            else None,
        },
        "neighbors": neighbors,
        "baseline_note": baseline_note,
        "count_kind": OBSERVED,
        "amount_kind": OBSERVED,
        "intensity_kind": DERIVED,
    }


def _entity_items(rows: list[Any], *, name_key: str, count_key: str, extra_key: str | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "id": str(row.get(name_key) or row.get("entity_id") or row.get("value") or "—"),
                "count": _int(row.get(count_key) or row.get("transaction_count") or row.get("count")),
                "related": _int(row.get(extra_key)) if extra_key else None,
                "provenance": OBSERVED,
            }
        )
    return items


def entity_relationships(
    *,
    world: str,
    groups: dict[str, list[dict[str, Any]]],
    missing: list[str],
) -> dict[str, Any]:
    available = {key: value for key, value in groups.items() if value}
    return {
        "available": bool(available),
        "provenance": OBSERVED,
        "source": "identifiers present in this world's mapped window",
        "groups": available,
        "missing": missing,
        "note": None
        if available
        else "This world does not contain identifiers that support entity clustering.",
    }


def historical_baseline(
    *,
    current: dict[str, Any],
    baseline: dict[str, Any],
    definition: str,
    provenance: str = BASELINE,
    unavailable: str | None = None,
) -> dict[str, Any]:
    if unavailable:
        return {
            "available": False,
            "reason": unavailable,
            "provenance": provenance,
        }
    current_vol = _num(current.get("volume"))
    base_vol = _num(baseline.get("volume"))
    deviation = None
    if current_vol is not None and base_vol not in (None, 0):
        deviation = {
            "ratio": current_vol / base_vol,
            "delta": current_vol - base_vol,
            "provenance": DERIVED,
            "source": "current volume versus baseline volume",
        }
    return {
        "available": True,
        "provenance": provenance,
        "source": definition,
        "current": current,
        "baseline": baseline,
        "deviation": deviation,
        "definition": definition,
    }


def investigator_brief(
    *,
    flagged: list[str],
    supports: list[str],
    observed: list[str],
    derived: list[str],
    uncertain: list[str],
    next_checks: list[str],
) -> dict[str, Any]:
    return {
        "why_flagged": flagged,
        "what_supports_risk": supports,
        "observed": observed,
        "derived": derived,
        "uncertain": uncertain,
        "next_checks": next_checks,
        "not_an_llm_paragraph": True,
    }


def build_intelligence(
    *,
    world: str,
    case_id: str,
    classifier: dict[str, Any] | None,
    sample_scope: str | None = None,
    brief: dict[str, Any],
    temporal: dict[str, Any],
    entities: dict[str, Any],
    baseline: dict[str, Any],
    case_metrics: list[dict[str, Any]],
    fp_impact: dict[str, Any],
) -> dict[str, Any]:
    status = classifier_evidence_status(classifier, world=world, sample_scope=sample_scope)
    return {
        "world": world,
        "case_id": case_id,
        "classifier_status": status,
        "brief": brief,
        "temporal": temporal,
        "entities": entities,
        "baseline": baseline,
        "case_metrics": case_metrics,
        "false_positive_impact": fp_impact,
        "not_money_saved": True,
        "classifier_is_not_detector": True,
        "classifier_is_not_action": True,
    }


def synthetic_hourly_neighbors(window_start: str) -> list[dict[str, Any]]:
    frame = _hourly_frame(HOURLY_WINDOWS_PATH)
    if frame is None:
        return []
    return _neighbors(
        frame,
        key="window_start",
        target=window_start,
        count_col="volume",
        amount_col="avg_amount",
        intensity_col="anomaly_score",
    )


def january_hourly_neighbors(hour_start: str) -> list[dict[str, Any]]:
    frame = _hourly_frame(JANUARY_HOURLY)
    if frame is None:
        return []
    return _neighbors(
        frame,
        key="hour_start",
        target=hour_start,
        count_col="transaction_count",
        amount_col="amount_usd",
        intensity_col="labelled_fraud_rate",
    )


def ieee_hourly_neighbors(bucket: int) -> list[dict[str, Any]]:
    frame = _hourly_frame(IEEE_HOURLY)
    if frame is None:
        return []
    return _neighbors(
        frame,
        key="relative_hour_bucket",
        target=bucket,
        count_col="transaction_count",
        amount_col="amount_usd",
        intensity_col="product_top_share",
    )


def custom_hourly_neighbors(hourly: list[dict[str, Any]] | None, hour_start: str) -> list[dict[str, Any]]:
    if not hourly:
        return []
    frame = pd.DataFrame(hourly)
    amount_col = "amount_sum" if "amount_sum" in frame.columns else ("amount" if "amount" in frame.columns else None)
    return _neighbors(
        frame,
        key="hour_start",
        target=hour_start,
        count_col="transaction_count",
        amount_col=amount_col,
        intensity_col=None,
    )


def load_heldout_overview() -> dict[str, Any] | None:
    path = HELD_OUT_DETECTION
    if not path.is_file():
        return None
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    any_vs = payload.get("any_injected_scenario_vs_any_spike") or {}
    festive = (payload.get("per_class") or {}).get("legitimate_festive") or {}
    coordinated = (payload.get("per_class") or {}).get("coordinated_abuse") or {}
    return {
        "seed": payload.get("seed"),
        "provenance": EVALUATION,
        "source": "data/heldout/detection_metrics.json",
        "evaluation_status": "held-out seed 2027; not the seed-42 demo ledger",
        "not_production_accuracy": True,
        "n_windows": payload.get("n_windows"),
        "coordinated_f1": coordinated.get("f1"),
        "festive_f1": festive.get("f1"),
        "any_precision": any_vs.get("precision"),
        "any_recall": any_vs.get("recall"),
        "any_fp": any_vs.get("fp"),
        "any_fn": any_vs.get("fn"),
    }


def load_investigation_overview() -> dict[str, Any] | None:
    path = INVESTIGATION_METRICS
    if not path.is_file():
        return None
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "seed": payload.get("seed"),
        "provenance": EVALUATION,
        "source": "evaluation/investigation_metrics.json",
        "evaluation_status": "held-out seed 2027 deterministic reasoner",
        "not_production_accuracy": True,
        "n_detected_spikes": payload.get("n_detected_spikes"),
        "accuracy": payload.get("accuracy"),
        "n_correct": payload.get("n_correct"),
        "n_incorrect": payload.get("n_incorrect"),
    }


def load_ieee_detector_holdout() -> dict[str, Any] | None:
    path = IEEE_EVALUATION
    if not path.is_file():
        return None
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    holdout = payload.get("temporal_holdout") or {}
    return {
        "provenance": EVALUATION,
        "source": "data/real/evaluation.json temporal_holdout",
        "evaluation_status": "hour-detector vs delayed isFraud hours; not classifier test performance",
        "precision": holdout.get("precision"),
        "recall": holdout.get("recall"),
        "tp": (holdout.get("counts") or {}).get("tp"),
        "fp": (holdout.get("counts") or {}).get("fp"),
        "fn": (holdout.get("counts") or {}).get("fn"),
        "not_model_accuracy": True,
    }


def load_ieee_test_operating_point() -> dict[str, Any] | None:
    path = IEEE_MODEL_EVAL
    if not path.is_file():
        return None
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    point = payload.get("operating_point") or {}
    confusion = point.get("confusion") or {}
    return {
        "provenance": EVALUATION,
        "source": "data/real/model/model_evaluation.json operating_point",
        "evaluation_status": "untouched chronological test set vs isFraud",
        "not_in_sample_overlay": True,
        "not_production_accuracy": True,
        "precision": point.get("precision"),
        "recall": point.get("recall"),
        "f1": point.get("f1"),
        "threshold": point.get("threshold"),
        "tp": confusion.get("tp"),
        "fp": confusion.get("fp"),
        "tn": confusion.get("tn"),
        "fn": confusion.get("fn"),
    }
