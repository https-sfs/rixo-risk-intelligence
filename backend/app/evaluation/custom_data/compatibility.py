"""IEEE-CIS model compatibility gate for user-provided datasets.

Generic amount + timestamp is never enough to score with the persisted classifier.
Official IEEE-CIS column names must already be present. Missing features are not fabricated.
"""

from __future__ import annotations

from typing import Any

from evaluation.custom_data import WORLD
from evaluation.custom_data.schema import IEEE_EXACT_CORE
from models.ieee_fraud.features import NAMED_FEATURES, discover_feature_columns
from models.ieee_fraud.predict import CORE_TRANSACTION_FIELDS, RECENT_PCA

MIN_SUPPORTING_IEEE = 5


def official_ieee_columns(columns: list[str]) -> list[str]:
    """Exact IEEE-CIS feature names only. Lowercase v1–v28 do not count."""
    official = discover_feature_columns(columns)
    return [name for name in official if not RECENT_PCA.fullmatch(name)]


def assess_compatibility(
    raw_columns: list[str],
    mapping: dict[str, str],
) -> dict[str, Any]:
    official = official_ieee_columns(raw_columns)
    core_present = [name for name in CORE_TRANSACTION_FIELDS if name in official]
    supporting = [name for name in official if name not in CORE_TRANSACTION_FIELDS]
    has_product_and_card = "ProductCD" in official and "card1" in official
    has_amount_or_dt = "TransactionAmt" in official or "TransactionDT" in official
    has_mapped_amount = bool(mapping.get("amount"))
    has_mapped_time = bool(mapping.get("timestamp"))
    anomaly_ready = has_mapped_amount or has_mapped_time
    january_pca = [name for name in raw_columns if RECENT_PCA.fullmatch(str(name))]

    compatible = (
        has_product_and_card
        and has_amount_or_dt
        and len(supporting) >= MIN_SUPPORTING_IEEE
    )
    may_score_classifier = bool(
        (mapping.get("amount") and mapping.get("timestamp"))
        or ("TransactionAmt" in official and "TransactionDT" in official)
    )
    if compatible:
        status = "compatible"
        headline = "READY"
        reason = (
            "The uploaded columns include the IEEE-CIS supervised-model feature contract "
            f"({', '.join(core_present)} plus {len(supporting)} supporting IEEE columns). "
            "The persisted classifier may be used. Missing IEEE fields stay missing; "
            "they are not fabricated."
        )
    elif anomaly_ready:
        status = "partial"
        headline = "PARTIAL"
        reason = (
            "Official IEEE-CIS columns are incomplete. We will not fabricate missing "
            "IEEE-CIS features. The shared classifier still scores when amount and time "
            "can be derived; remaining canonical fields stay unavailable."
        )
    else:
        status = "incompatible"
        headline = "INCOMPATIBLE"
        reason = (
            "The upload cannot be scored by the IEEE-CIS classifier and does not include "
            "a usable amount or timestamp field for anomaly investigation. "
            "Map amount and a time field to continue, or upload a dataset that already "
            "contains official IEEE-CIS columns."
        )

    reasons_detail = []
    if january_pca:
        reasons_detail.append(
            "Lowercase v1–v28 columns are not IEEE-CIS V* and cannot unlock the classifier."
        )
    if mapping.get("amount") and "TransactionAmt" not in official:
        reasons_detail.append(
            "A mapped amount field is derived into TransactionAmt. Other missing IEEE "
            "fields stay unavailable."
        )
    if mapping.get("timestamp") and "TransactionDT" not in official:
        reasons_detail.append(
            "A mapped timestamp is derived into elapsed TransactionDT. It is not treated "
            "as a fabricated IEEE calendar feature beyond that derivation."
        )
    if not has_product_and_card:
        reasons_detail.append("ProductCD and card1 are required for a compatible IEEE payload.")
    if len(supporting) < MIN_SUPPORTING_IEEE:
        reasons_detail.append(
            f"Fewer than {MIN_SUPPORTING_IEEE} supporting IEEE-CIS columns "
            f"(C*, D*, M*, V*, card*, addr*, Device*, email) are present."
        )

    return {
        "world": WORLD,
        "status": status,
        "headline": headline,
        "may_use_ieee_model": compatible,
        "may_score_classifier": may_score_classifier,
        "anomaly_ready": anomaly_ready,
        "reason": reason,
        "details": reasons_detail,
        "official_ieee_columns": official,
        "core_ieee_present": core_present,
        "supporting_ieee_count": len(supporting),
        "required_core_fields": list(IEEE_EXACT_CORE),
        "named_ieee_features": list(NAMED_FEATURES),
        "features_fabricated": False,
        "mapped_amount": mapping.get("amount"),
        "mapped_timestamp": mapping.get("timestamp"),
        "not_a_live_production_decision": True,
    }
