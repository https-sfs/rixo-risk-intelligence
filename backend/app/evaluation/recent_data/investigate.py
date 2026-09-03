"""January 2026 investigation: deterministic evidence analysis, optional real LLM.

Source CNN-LSTM outputs are not our scores. The shared classifier is separate evidence.
"""

from __future__ import annotations

import json
from typing import Any

from agent.errors import LLMProviderError
from agent.providers.llm import read_llm_api_key

from evaluation.recent_data.mapper import AMOUNT_CURRENCY, DATASET_NAME, SOURCE_MODEL_OUTPUTS, WORLD
from models.ieee_fraud.copy import (
    sanitize_reasoning_text,
    strip_stale_classifier_claims,
)


LLM_SYSTEM_PROMPT = (
    "You analyze January 2026 public online-banking transaction aggregates. "
    "Use only the supplied live evidence and, if present, the Classifier block. "
    "Do not use is_fraud, delayed ground truth, or source-dataset model outputs "
    f"({', '.join(SOURCE_MODEL_OUTPUTS)}) as live inputs. "
    "Do not invent a fraud_risk_score or map January v1–v28 onto V* columns. "
    "If classifier_evidence.status is scored, you may mention it only as supporting "
    "evidence. Never say the classifier was not applied, detected this anomaly, "
    "or determined the action. Classifier output is evidence, not a payment decision. "
    "Do not claim coordinated abuse, festive/Diwali sales, money saved, "
    "or production payment outcomes. "
    "Reply with JSON keys: summary, signals, limitations."
)


def llm_configured() -> bool:
    return bool(read_llm_api_key())


def build_llm_context(evidence: dict[str, Any]) -> dict[str, Any]:
    """Investigation context for the LLM. Classifier scores are supplied when present."""
    classifier = evidence.get("classifier") or {}
    classifier_evidence = None
    if classifier:
        classifier_evidence = {
            "status": classifier.get("status"),
            "fraud_risk_score": classifier.get("fraud_risk_score"),
            "classification": classifier.get("classification"),
            "model": classifier.get("model"),
            "model_version": classifier.get("model_version"),
            "feature_coverage": classifier.get("feature_coverage"),
            "reason": classifier.get("reason"),
            "missing_features": classifier.get("missing_features"),
        }
    return {
        "anomaly_id": evidence.get("anomaly_id"),
        "hour_start": evidence.get("hour_start"),
        "kind": evidence.get("kind"),
        "live_evidence": evidence.get("live_evidence"),
        "classifier_evidence": classifier_evidence,
        "note": (
            "Live evidence only. is_fraud is delayed ground truth. "
            "Source-model outputs are excluded. Classifier output is evidence, not a decision."
        ),
    }


def deterministic_analysis(evidence: dict[str, Any]) -> dict[str, Any]:
    live = evidence.get("live_evidence", {})
    hour = evidence.get("hour_start")
    kind = evidence.get("kind") or "Recent-data anomaly"
    summary_parts = [
        f"{kind} at {hour} in {DATASET_NAME}.",
        f"Observed transactions: {(live.get('transaction_count') or {}).get('value')}.",
        f"Observed amount: {(live.get('amount_usd') or {}).get('value')} {AMOUNT_CURRENCY}.",
        "Detection used hour-level volume and amount only.",
        "is_fraud was not a live input. Source-model outputs were not used.",
    ]
    classifier = evidence.get("classifier") or {}
    return {
        "world": WORLD,
        "dataset": DATASET_NAME,
        "anomaly_id": evidence.get("anomaly_id"),
        "provider": "deterministic",
        "provider_label": "DETERMINISTIC",
        "headline": kind,
        "summary": " ".join(summary_parts),
        "signals": list((evidence.get("signals") if isinstance(evidence.get("signals"), list) else []) or []),
        "limitations": [
            "No account, device, merchant, or SKU identifiers are available.",
            "v1–v28 are source PCA features and are not used as classifier inputs.",
            "Classifier output is independent of deterministic detection and is not a live decision.",
        ],
        "evaluation_overlay": evidence.get("evaluation_overlay"),
        "source_dataset_model_output": evidence.get("source_dataset_model_output"),
        "classifier": classifier or None,
        "ieee_model_used": False,
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
        "headline": evidence.get("kind") or "Recent-data anomaly",
        "summary": sanitize_reasoning_text(str(parsed.get("summary") or ""), evidence.get("classifier")),
        "signals": parsed.get("signals") or [],
        "limitations": parsed.get("limitations")
        or [
            "Classifier output is independent of deterministic detection and is not a live decision.",
        ],
        "evaluation_overlay": evidence.get("evaluation_overlay"),
        "classifier": evidence.get("classifier"),
        "ieee_model_used": False,
        "model_is_not_llm": True,
        "uses_delayed_ground_truth_as_live_input": False,
        "llm_used": True,
    }


def investigate_recent_anomaly(evidence: dict[str, Any], provider: str = "auto") -> dict[str, Any]:
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
    report["ieee_model_used"] = False
    report["model_is_not_llm"] = True
    report["classifier"] = evidence.get("classifier") or report.get("classifier")
    report["summary"] = sanitize_reasoning_text(str(report.get("summary") or ""), report.get("classifier"))
    limitations = report.get("limitations")
    if isinstance(limitations, list):
        report["limitations"] = [strip_stale_classifier_claims(str(item)) for item in limitations if strip_stale_classifier_claims(str(item))]
    return report
