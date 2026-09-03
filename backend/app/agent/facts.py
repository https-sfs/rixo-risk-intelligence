"""Turn Phase 2A evidence into reasoning facts. No ledger dump. No scenario tags."""

from __future__ import annotations

from typing import Any


def extract_reasoning_facts(evidence: dict[str, Any]) -> dict[str, Any]:
    window = evidence["window"]
    entities = evidence["entities"]
    concentration = evidence["concentration"]
    relationships = evidence["relationships"]
    velocity = evidence["velocity"]
    baseline = evidence["baseline_comparison"]
    spike = evidence["spike"]
    return {
        "spike_id": spike["spike_id"],
        "window_start": spike["window_start"],
        "window_end": spike["window_end"],
        "detector_type": spike["detector_type"],
        "severity": spike["severity"],
        "anomaly_reasons": list(spike.get("anomaly_reasons") or []),
        "anomaly_score": spike.get("anomaly_score"),
        "coordination_score": spike.get("coordination_score"),
        "window": {
            "transaction_count": window["transaction_count"],
            "total_amount": window["total_amount"],
            "mean_amount": window["mean_amount"],
            "status_counts": window["status_counts"],
            "status_rates": window["status_rates"],
            "payment_methods": window["payment_methods"],
            "fraud_label_rate": {
                "value": window["fraud_label_rate"]["value"],
                "labelled_count": window["fraud_label_rate"]["labelled_count"],
                "interpretation": window["fraud_label_rate"]["interpretation"],
            },
        },
        "entities": entities,
        "concentration": {
            "devices": concentration.get("devices", [])[:3],
            "subnets": concentration.get("subnets", [])[:3],
            "pincodes": concentration.get("pincodes", [])[:3],
            "skus": concentration.get("skus", [])[:3],
        },
        "relationships": {
            "device_to_accounts": relationships.get("device_to_accounts", [])[:3],
            "subnet_to_accounts": relationships.get("subnet_to_accounts", [])[:3],
            "pincode_to_accounts": relationships.get("pincode_to_accounts", [])[:3],
            "sku_to_accounts": relationships.get("sku_to_accounts", [])[:3],
        },
        "velocity": {
            "account_tx_count_1h": {
                "mean": velocity["account_tx_count_1h"]["mean"],
                "maximum": velocity["account_tx_count_1h"]["maximum"],
            },
            "device_tx_count_1h": {
                "mean": velocity["device_tx_count_1h"]["mean"],
                "maximum": velocity["device_tx_count_1h"]["maximum"],
            },
            "ip_subnet_tx_count_1h": {
                "mean": velocity["ip_subnet_tx_count_1h"]["mean"],
                "maximum": velocity["ip_subnet_tx_count_1h"]["maximum"],
            },
        },
        "baseline_comparison": {
            "hourly_baseline": baseline["hourly_baseline"],
            "normal_baseline": baseline["normal_baseline"],
            "festive_period": baseline["festive_period"],
        },
    }


def build_llm_prompt(facts: dict[str, Any]) -> str:
    """Compatibility wrapper around the Phase 3A prompt builder."""
    from agent.prompts import build_investigation_prompt

    return build_investigation_prompt(facts)
