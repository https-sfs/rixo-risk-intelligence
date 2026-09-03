"""Transparent rule-based reasoner over verified facts.

This is not an LLM. It scores multiple operational signals and can return
inconclusive when they conflict. Verdicts are not copied from detector_type.
"""

from __future__ import annotations

from typing import Any

from agent.schema import (
    EvidenceCitation,
    InvestigationReport,
    KeyEntity,
    RecommendedAction,
)


def _top(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    return items[0] if items else None


def _share(item: dict[str, Any] | None) -> float:
    if not item:
        return 0.0
    return float(item.get("share_of_transactions") or 0.0)


class DeterministicReasoner:
    name = "deterministic_reasoner"

    def reason(self, facts: dict[str, Any]) -> InvestigationReport:
        window = facts["window"]
        entities = facts["entities"]
        concentration = facts["concentration"]
        relationships = facts["relationships"]
        velocity = facts["velocity"]
        hourly = facts["baseline_comparison"]["hourly_baseline"]
        festive = facts["baseline_comparison"]["festive_period"]

        supporting: list[EvidenceCitation] = []
        contradicting: list[EvidenceCitation] = []
        limitations: list[str] = []
        abuse_points = 0
        festive_points = 0

        fail_rate = float(window["status_rates"]["failed"]) + float(
            window["status_rates"]["declined"]
        )
        success_rate = float(window["status_rates"]["success"])
        if fail_rate >= 0.35:
            abuse_points += 1
            supporting.append(
                EvidenceCitation(
                    fact=(
                        f"Failed rate is {window['status_rates']['failed']} and "
                        f"declined rate is {window['status_rates']['declined']}"
                    ),
                    source="window.status_rates",
                )
            )
        elif fail_rate < 0.22:
            festive_points += 1
            contradicting.append(
                EvidenceCitation(
                    fact=f"Authorization outcomes remain mostly successful ({success_rate})",
                    source="window.status_rates.success",
                )
            )

        device = _top(concentration.get("devices", []))
        accounts = max(int(entities["unique_accounts"]), 1)
        devices = max(int(entities["unique_devices"]), 1)
        device_account_ratio = accounts / devices
        if device and _share(device) >= 0.20 and int(device.get("distinct_accounts") or 0) >= 5:
            abuse_points += 1
            supporting.append(
                EvidenceCitation(
                    fact=(
                        f"Device {device['entity_id']} accounts for {device['share_of_transactions']} of "
                        f"window transactions across {device['distinct_accounts']} accounts"
                    ),
                    source="concentration.devices",
                )
            )
        if device_account_ratio < 1.4 and devices / accounts >= 0.8:
            festive_points += 1
            contradicting.append(
                EvidenceCitation(
                    fact=(
                        f"Account/device mix is diverse "
                        f"({entities['unique_accounts']} accounts, {entities['unique_devices']} devices)"
                    ),
                    source="entities.unique_accounts",
                )
            )

        subnet = _top(concentration.get("subnets", []))
        if (
            subnet
            and _share(subnet) >= 0.55
            and int(entities["unique_subnets"]) <= 8
        ):
            abuse_points += 1
            supporting.append(
                EvidenceCitation(
                    fact=(
                        f"Subnet {subnet['entity_id']} holds {subnet['share_of_transactions']} of transactions "
                        f"with only {entities['unique_subnets']} unique subnets"
                    ),
                    source="concentration.subnets",
                )
            )
        elif int(entities["unique_subnets"]) >= 8 and _share(subnet) < 0.35:
            festive_points += 1
            contradicting.append(
                EvidenceCitation(
                    fact=f"IP diversity remains broad ({entities['unique_subnets']} unique subnets)",
                    source="entities.unique_subnets",
                )
            )

        sku = _top(concentration.get("skus", []))
        if sku and _share(sku) >= 0.50:
            abuse_points += 1
            supporting.append(
                EvidenceCitation(
                    fact=f"SKU {sku['entity_id']} is {sku['share_of_transactions']} of window volume",
                    source="concentration.skus",
                )
            )
        elif int(entities["unique_skus"]) >= 8 and (not sku or _share(sku) < 0.28):
            festive_points += 1
            contradicting.append(
                EvidenceCitation(
                    fact=f"SKU mix is broad ({entities['unique_skus']} unique SKUs)",
                    source="entities.unique_skus",
                )
            )

        pincode = _top(concentration.get("pincodes", []))
        if (
            pincode
            and _share(pincode) >= 0.40
            and int(entities["unique_pincodes"]) <= 8
        ):
            abuse_points += 1
            supporting.append(
                EvidenceCitation(
                    fact=(
                        f"Pincode {pincode['entity_id']} holds {pincode['share_of_transactions']} of transactions"
                    ),
                    source="concentration.pincodes",
                )
            )
        elif int(entities["unique_pincodes"]) >= 10 and _share(pincode) < 0.25:
            festive_points += 1
            contradicting.append(
                EvidenceCitation(
                    fact=f"Pincode diversity is high ({entities['unique_pincodes']} unique pincodes)",
                    source="entities.unique_pincodes",
                )
            )

        shared = _top(relationships.get("device_to_accounts", []))
        if shared and int(shared.get("distinct_related") or 0) >= 8:
            abuse_points += 1
            supporting.append(
                EvidenceCitation(
                    fact=(
                        f"Device {shared['entity_id']} is linked to {shared['distinct_related']} accounts"
                    ),
                    source="relationships.device_to_accounts",
                )
            )

        device_velocity = velocity["device_tx_count_1h"]
        if device_velocity["maximum"] is not None and int(device_velocity["maximum"]) >= 15:
            abuse_points += 1
            supporting.append(
                EvidenceCitation(
                    fact=f"Peak device 1h velocity is {device_velocity['maximum']}",
                    source="velocity.device_tx_count_1h.maximum",
                )
            )

        volume_baseline = hourly["baseline_volume"]
        volume_ratio = hourly["volume_change_ratio"]
        if volume_baseline.get("status") == "unavailable":
            limitations.append(
                "Hour-of-day volume baseline is unavailable; volume change is not used as proof."
            )
        elif volume_ratio.get("status") == "available" and float(volume_ratio["value"]) >= 2.0:
            if festive_points >= 2:
                festive_points += 1
                contradicting.append(
                    EvidenceCitation(
                        fact=f"Volume is {volume_ratio['value']}x the hour-of-day baseline with preserved diversity",
                        source="baseline_comparison.hourly_baseline.volume_change_ratio",
                    )
                )
            else:
                supporting.append(
                    EvidenceCitation(
                        fact=f"Volume is {volume_ratio['value']}x the hour-of-day baseline",
                        source="baseline_comparison.hourly_baseline.volume_change_ratio",
                    )
                )

        festive_fail = festive.get("mean_failure_rate") or {}
        if festive_fail.get("status") == "available" and fail_rate >= 0.35:
            if float(festive_fail["value"]) < 0.22:
                abuse_points += 1
                supporting.append(
                    EvidenceCitation(
                        fact=(
                            f"Window failed rate {window['status_rates']['failed']} and declined "
                            f"rate {window['status_rates']['declined']} exceed festive-hour mean "
                            f"failure rate {festive_fail['value']}"
                        ),
                        source="baseline_comparison.festive_period.mean_failure_rate",
                    )
                )

        label = window["fraud_label_rate"]
        limitations.append(
            f"Labelled-fraud rate {label['value']} is {label['interpretation']}"
        )

        if abuse_points >= 3 and festive_points <= 1:
            verdict: Any = "coordinated_abuse"
            confidence = min(0.55 + 0.08 * abuse_points, 0.88)
            action = RecommendedAction(
                type="tighten_rule",
                scope=_action_scope(device, subnet, sku),
                reason="Multiple concentration and outcome signals align; a narrow review rule is warranted.",
            )
            summary = "Multiple independent concentration and failure signals support coordinated activity."
        elif festive_points >= 3 and abuse_points <= 1:
            verdict = "likely_festive"
            confidence = min(0.55 + 0.08 * festive_points, 0.86)
            action = RecommendedAction(
                type="monitor",
                scope="window-level volume only; no entity block",
                reason="Diversity and success patterns resemble a high-volume shopping period.",
            )
            summary = "High or elevated volume appears with diverse entities and healthy outcomes."
        else:
            verdict = "inconclusive"
            confidence = 0.42
            action = RecommendedAction(
                type="review",
                scope="analyst review of this window only",
                reason="Signals conflict or are insufficient for a coordination or festive finding.",
            )
            summary = "Evidence is mixed or incomplete; no single-pattern finding is justified."

        key_entities = _key_entities(device, subnet, pincode, sku, shared)
        reasoning = _reasoning_text(
            verdict,
            abuse_points,
            festive_points,
            limitations,
            facts.get("detector_type"),
        )
        return InvestigationReport(
            spike_id=str(facts["spike_id"]),
            verdict=verdict,
            confidence=round(confidence, 3),
            summary=summary,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            key_entities=key_entities,
            reasoning=reasoning,
            recommended_action=action,
            human_approval_required=True,
            limitations=limitations,
            provider=self.name,
        )


def _action_scope(
    device: dict[str, Any] | None,
    subnet: dict[str, Any] | None,
    sku: dict[str, Any] | None,
) -> str:
    parts: list[str] = []
    if device:
        parts.append(f"device {device['entity_id']}")
    if subnet:
        parts.append(f"subnet {subnet['entity_id']}")
    if sku:
        parts.append(f"sku {sku['entity_id']}")
    if not parts:
        return "this spike window only"
    return "review " + ", ".join(parts)


def _key_entities(
    device: dict[str, Any] | None,
    subnet: dict[str, Any] | None,
    pincode: dict[str, Any] | None,
    sku: dict[str, Any] | None,
    shared: dict[str, Any] | None,
) -> list[KeyEntity]:
    entities: list[KeyEntity] = []
    if device:
        entities.append(
            KeyEntity(
                "device",
                str(device["entity_id"]),
                f"{device['transaction_count']} txs, {device.get('distinct_accounts')} accounts",
            )
        )
    if subnet:
        entities.append(
            KeyEntity(
                "subnet",
                str(subnet["entity_id"]),
                f"{subnet['transaction_count']} txs, share {subnet['share_of_transactions']}",
            )
        )
    if pincode:
        entities.append(
            KeyEntity(
                "pincode",
                str(pincode["entity_id"]),
                f"{pincode['transaction_count']} txs, share {pincode['share_of_transactions']}",
            )
        )
    if sku:
        entities.append(
            KeyEntity(
                "sku",
                str(sku["entity_id"]),
                f"{sku['transaction_count']} txs, share {sku['share_of_transactions']}",
            )
        )
    if shared and all(item.entity_id != shared["entity_id"] for item in entities):
        entities.append(
            KeyEntity(
                "device",
                str(shared["entity_id"]),
                f"{shared['distinct_related']} linked accounts",
            )
        )
    return entities


def _reasoning_text(
    verdict: str,
    abuse_points: int,
    festive_points: int,
    limitations: list[str],
    detector_type: Any,
) -> str:
    parts = [
        f"Operational abuse signals={abuse_points}; festive/diversity signals={festive_points}.",
        f"Detector classified the window as {detector_type}; that label is context, not the verdict.",
        "No single signal is treated as proof.",
        f"Working verdict is {verdict}.",
        " ".join(limitations),
    ]
    return " ".join(part for part in parts if part)
