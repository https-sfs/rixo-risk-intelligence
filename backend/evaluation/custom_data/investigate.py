"""Custom-data investigation: deterministic evidence analysis, optional real LLM."""

from __future__ import annotations

import json
from typing import Any

from agent.errors import LLMProviderError
from agent.providers.llm import read_llm_api_key

from evaluation.custom_data import DATASET_NAME, USER_MODEL_PROVENANCE, WORLD
from models.ieee_fraud.copy import sanitize_reasoning_text


LLM_SYSTEM_PROMPT = (
    "You analyze a user-provided transaction dataset. "
    "Use only the supplied live evidence and, if present, MODEL PREDICTION · USER DATASET. "
    "Do not invent fraud_risk_score, IEEE features, accounts, devices, IPs, merchants, "
    "SKUs, dates, statuses, or labels. "
    "Do not treat user-provided labels as live detector inputs. "
    "You are not the trained fraud model. "
    "If classifier evidence is scored, mention it only as supporting evidence. "
    "Never say the classifier was not applied, detected this anomaly, or determined the action. "
    "Do not claim money saved or live payment blocking. "
    "Reply with JSON keys: summary, signals, limitations."
)


def llm_configured() -> bool:
    return bool(read_llm_api_key())


def build_llm_context(evidence: dict[str, Any]) -> dict[str, Any]:
    model = evidence.get("model_prediction") or {}
    classifier = evidence.get("classifier") or {}
    model_evidence = None
    if classifier or model:
        model_evidence = {
            "status": classifier.get("status"),
            "fraud_risk_score": classifier.get("fraud_risk_score"),
            "classification": classifier.get("classification"),
            "model": classifier.get("model"),
            "model_version": classifier.get("model_version"),
            "feature_coverage": classifier.get("feature_coverage"),
            "provenance": USER_MODEL_PROVENANCE,
            "note": "Supplied by the shared classifier. Missing features were not fabricated.",
            "high_risk_count": model.get("high_risk_count") or classifier.get("high_risk_count"),
            "p95_score": model.get("p95_score") or classifier.get("p95_score"),
            "threshold": model.get("threshold") or classifier.get("operating_threshold"),
        }
    return {
        "anomaly_id": evidence.get("anomaly_id"),
        "hour_start": evidence.get("hour_start"),
        "live_evidence": evidence.get("live_evidence"),
        "classifier_evidence": model_evidence,
        "model_prediction_evidence": model_evidence,
    }


def deterministic_analysis(evidence: dict[str, Any]) -> dict[str, Any]:
    live = evidence.get("live_evidence") or {}
    kind = evidence.get("kind") or "Custom-data anomaly"
    window = evidence.get("time_display") or (live.get("temporal_window") or {}).get("value") or evidence.get("hour_start")
    summary_parts = [
        f"{kind} at {window} on {DATASET_NAME}.",
        f"Observed transactions: {(live.get('transaction_count') or {}).get('value')}.",
    ]
    amount_value = (live.get("amount") or {}).get("value")
    if amount_value is not None and amount_value == amount_value and str(amount_value).lower() != "nan":
        summary_parts.append(f"Observed amount: {amount_value}.")
    model = evidence.get("model_prediction")
    classifier = evidence.get("classifier") or {}
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "anomaly_id": evidence.get("anomaly_id"),
        "provider": "deterministic",
        "provider_label": "DETERMINISTIC",
        "headline": kind,
        "summary": " ".join(summary_parts),
        "signals": list(evidence.get("signals") or []),
        "limitations": [
            "Only user-supplied fields were used.",
            "Missing IEEE-CIS features were not fabricated.",
            "The LLM is not the trained fraud model.",
        ],
        "evaluation_overlay": evidence.get("evaluation_overlay"),
        "model_prediction": model,
        "classifier": classifier or None,
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
        "headline": evidence.get("kind") or "Custom-data anomaly",
        "summary": str(parsed.get("summary") or ""),
        "signals": parsed.get("signals") or evidence.get("signals") or [],
        "limitations": parsed.get("limitations") or ["The LLM is not the trained fraud model."],
        "evaluation_overlay": evidence.get("evaluation_overlay"),
        "model_prediction": evidence.get("model_prediction"),
        "model_is_not_llm": True,
        "uses_delayed_ground_truth_as_live_input": False,
        "llm_used": True,
    }


def investigate_custom_anomaly(evidence: dict[str, Any], provider: str = "auto") -> dict[str, Any]:
    requested = provider.strip().lower()
    if requested in {"llm", "auto"} and llm_configured():
        try:
            report = _llm_analysis(evidence)
        except (LLMProviderError, json.JSONDecodeError, ValueError):
            if requested == "llm":
                raise
            report = deterministic_analysis(evidence)
    else:
        report = deterministic_analysis(evidence)
    report["model_is_not_llm"] = True
    report["classifier"] = evidence.get("classifier")
    report["summary"] = sanitize_reasoning_text(str(report.get("summary") or ""), report.get("classifier"))
    return report
