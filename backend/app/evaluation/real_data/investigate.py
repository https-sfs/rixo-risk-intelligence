"""Real-data investigation: deterministic evidence analysis, optional real LLM."""

from __future__ import annotations

import json
from typing import Any

from agent.errors import LLMProviderError
from agent.providers.llm import read_llm_api_key

from evaluation.real_data.mapper import AMOUNT_CURRENCY, DATASET_NAME, WORLD
from models.ieee_fraud.copy import sanitize_reasoning_text


LLM_SYSTEM_PROMPT = (
    "You analyze IEEE-CIS public fraud-data aggregates. "
    "Use only the supplied live evidence and MODEL PREDICTION evidence. "
    "The IEEE-CIS classifier is the sole source of fraud_risk_score, the operating "
    "threshold, high_risk_count, and whether a score is above threshold. "
    "Do not calculate, invent, or replace those values. "
    "You may mention MODEL PREDICTION only as supporting evidence. "
    "Do not say the classifier detected this anomaly or determined the action. "
    "Do not claim coordinated abuse, festive/Diwali sales, IP subnets, SKUs, "
    "or production payment outcomes. "
    "Do not treat delayed fraud labels as live evidence. "
    "Reply with JSON keys: summary, signals, limitations."
)


def llm_configured() -> bool:
    return bool(read_llm_api_key())


def build_llm_context(evidence: dict[str, Any]) -> dict[str, Any]:
    """Investigation context for the LLM. Classifier scores are supplied, never requested."""
    model = evidence.get("model_prediction") or {}
    model_evidence = None
    if model:
        tops = []
        for item in model.get("top_transactions") or []:
            tops.append(
                {
                    "transaction_id": item.get("transaction_id"),
                    "fraud_risk_score": item.get("fraud_risk_score"),
                    "provenance": item.get("provenance") or "MODEL PREDICTION",
                }
            )
        model_evidence = {
            "provenance": "MODEL PREDICTION",
            "note": (
                "Supplied by the IEEE-CIS classifier. Do not recalculate fraud_risk_score, "
                "threshold, high_risk_count, or above-threshold decisions."
            ),
            "high_risk_count": model.get("high_risk_count"),
            "p95_score": model.get("p95_score"),
            "threshold": model.get("threshold"),
            "sample_scope": model.get("sample_scope"),
            "top_transactions": tops,
        }
    return {
        "anomaly_id": evidence.get("anomaly_id"),
        "relative_hour_bucket": evidence.get("relative_hour_bucket"),
        "live_evidence": evidence.get("live_evidence"),
        "unavailable": evidence.get("unavailable"),
        "model_prediction_evidence": model_evidence,
    }


def deterministic_analysis(evidence: dict[str, Any]) -> dict[str, Any]:
    live = evidence.get("live_evidence", {})
    temporal = (live.get("temporal_anomaly") or {}).get("value") or {}
    product = (live.get("product_concentration") or {}).get("value") or {}
    signals = list(temporal.get("signals") or [])
    summary_parts = [
        f"Relative hour bucket {evidence.get('relative_hour_bucket')} is a REAL DATA ANOMALY "
        f"from {DATASET_NAME}.",
        f"Observed transactions: {(live.get('transaction_count') or {}).get('value')}.",
        f"Observed amount: {(live.get('amount_usd') or {}).get('value')} {AMOUNT_CURRENCY}.",
    ]
    if product:
        summary_parts.append(
            f"Top ProductCD {product.get('value')} share {product.get('share')}."
        )
    model = evidence.get("model_prediction")
    classifier = evidence.get("classifier") or {}
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "anomaly_id": evidence.get("anomaly_id"),
        "provider": "deterministic",
        "provider_label": "DETERMINISTIC",
        "headline": "REAL DATA ANOMALY",
        "summary": " ".join(summary_parts),
        "signals": signals,
        "limitations": evidence.get("missing_signal_warnings", []),
        "evaluation_overlay": evidence.get("evaluation_overlay"),
        "model_prediction": model,
        "classifier": evidence.get("classifier"),
        "model_is_not_llm": True,
        "uses_delayed_ground_truth_as_live_input": False,
        "llm_used": False,
    }


def _llm_analysis(evidence: dict[str, Any]) -> dict[str, Any]:
    from agent.providers.client import OpenAICompatibleClient
    from agent.providers.llm import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_TIMEOUT_SECONDS

    client = OpenAICompatibleClient(
        api_key=read_llm_api_key(),
        base_url=DEFAULT_BASE_URL,
        model=DEFAULT_MODEL,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    )
    raw = client.complete(LLM_SYSTEM_PROMPT, json.dumps(build_llm_context(evidence)))
    parsed = json.loads(raw)
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "anomaly_id": evidence.get("anomaly_id"),
        "provider": "llm",
        "provider_label": "LLM",
        "headline": "REAL DATA ANOMALY",
        "summary": str(parsed.get("summary") or ""),
        "signals": parsed.get("signals") or [],
        "limitations": parsed.get("limitations") or evidence.get("missing_signal_warnings", []),
        "evaluation_overlay": evidence.get("evaluation_overlay"),
        "uses_delayed_ground_truth_as_live_input": False,
        "llm_used": True,
    }


def investigate_real_anomaly(evidence: dict[str, Any], provider: str = "auto") -> dict[str, Any]:
    requested = provider.strip().lower()
    report: dict[str, Any]
    if requested in {"llm", "auto"} and llm_configured():
        try:
            report = _llm_analysis(evidence)
        except (LLMProviderError, json.JSONDecodeError, ValueError):
            if requested == "llm":
                raise
            report = deterministic_analysis(evidence)
    else:
        report = deterministic_analysis(evidence)
    report["model_prediction"] = evidence.get("model_prediction")
    report["classifier"] = evidence.get("classifier")
    report["model_is_not_llm"] = True
    report["summary"] = sanitize_reasoning_text(str(report.get("summary") or ""), report.get("classifier"))
    return report
