"""Prompt construction for LLM investigation. Facts only; no ledger dump."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

DELAYED_LABEL_FOR_MODEL = "delayed ground truth; unavailable at decision time"

SYSTEM_PROMPT = """You are a payment-risk investigation analyst.
You investigate detected anomalies using only verified deterministic evidence.
You do not invent measurements.
You do not perform calculations that are not supplied by the evidence layer.
You distinguish supporting evidence from contradicting evidence.
High transaction volume alone is not proof of abuse.
Festive/sale traffic may legitimately create large spikes.
When evidence is insufficient or conflicting, return inconclusive.
Recommendations must remain narrowly scoped and require human approval.

Rules:
- Cite an exact evidence field/path for every important claim.
- Do not invent entity IDs, percentages, counts, or baseline values.
- If a baseline or metric is marked unavailable, acknowledge that limitation. Do not invent a comparison.
- Distinguish correlation from proof. One signal is not automatic proof of abuse.
- Do not treat labelled-fraud rates as live scores. If a labelled-fraud rate is present, it is delayed ground truth; unavailable at decision time.
- Do not use hidden synthetic scenario labels. They are not supplied and must not be inferred as live evidence.
- Do not recommend blanket blocking, account disablement, refunds, money movement, or production payment-rule changes.
- Prefer narrowly scoped review, tighten_rule, monitor, or no_action.
- human_approval_required must be true.
- Return only a JSON object that matches the required schema. No prose outside JSON.
"""

OUTPUT_SCHEMA_HINT = {
    "spike_id": "string",
    "verdict": "coordinated_abuse | likely_festive | inconclusive",
    "confidence": "number between 0 and 1",
    "summary": "string",
    "supporting_evidence": [{"fact": "string", "source": "exact evidence field/path"}],
    "contradicting_evidence": [{"fact": "string", "source": "exact evidence field/path"}],
    "key_entities": [
        {
            "entity_type": "device | subnet | pincode | sku | account",
            "entity_id": "must exist in supplied evidence",
            "reason": "string",
        }
    ],
    "reasoning": "string",
    "recommended_action": {
        "type": "review | tighten_rule | monitor | no_action",
        "scope": "narrow string",
        "reason": "string",
    },
    "human_approval_required": True,
    "limitations": ["string"],
}


def prepare_llm_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """Copy reasoning facts and mark evaluation labels as unavailable at decision time."""
    prepared = deepcopy(facts)
    window = prepared.get("window")
    if isinstance(window, dict) and isinstance(window.get("fraud_label_rate"), dict):
        window["fraud_label_rate"]["interpretation"] = DELAYED_LABEL_FOR_MODEL
        window["fraud_label_rate"]["live_signal"] = False
    limitations: list[str] = []
    hourly = (
        prepared.get("baseline_comparison", {}).get("hourly_baseline", {})
        if isinstance(prepared.get("baseline_comparison"), dict)
        else {}
    )
    volume = hourly.get("baseline_volume") if isinstance(hourly, dict) else None
    ratio = hourly.get("volume_change_ratio") if isinstance(hourly, dict) else None
    if isinstance(volume, dict) and volume.get("status") == "unavailable":
        limitations.append(
            "Hour-of-day volume baseline is unavailable. Do not invent a volume comparison."
        )
    if isinstance(ratio, dict) and ratio.get("status") == "unavailable":
        limitations.append(
            "Volume change ratio is unavailable because the volume baseline is unavailable."
        )
    limitations.append(
        "Any labelled-fraud rate is delayed ground truth; unavailable at decision time."
    )
    prepared["data_limitations"] = limitations
    return prepared


def build_investigation_messages(facts: dict[str, Any]) -> tuple[str, str]:
    prepared = prepare_llm_facts(facts)
    user_prompt = (
        "Investigate this spike using only the verified facts below.\n"
        "The deterministic investigation layer is the source of truth for measurements.\n"
        "Cite source paths that exist in these facts.\n\n"
        f"Required JSON schema:\n{json.dumps(OUTPUT_SCHEMA_HINT, indent=2)}\n\n"
        f"Verified facts:\n{json.dumps(prepared, indent=2)}\n"
    )
    return SYSTEM_PROMPT, user_prompt


def build_investigation_prompt(facts: dict[str, Any]) -> str:
    system_prompt, user_prompt = build_investigation_messages(facts)
    return f"{system_prompt}\n\n{user_prompt}"
