"""Honest January-2026 transfer boundary. Do not map 2026 PCA onto IEEE V*."""

from __future__ import annotations

from typing import Any

from models.ieee_fraud import FORBIDDEN_FEATURES

TRANSFERABLE_2026 = ("amount", "hour_of_day")
IEEE_ONLY_PREFIXES = ("C", "D", "M", "V", "id_", "card", "addr", "ProductCD", "Device")


class TransferSchemaError(ValueError):
    """2026 schema cannot legally instantiate the IEEE-CIS feature set."""


def refuse_ieee_v_mapping(source_columns: list[str]) -> None:
    lowered = {name.lower() for name in source_columns}
    if "v1" in lowered and "transactionamt" not in lowered:
        if any(name.lower().startswith("v") and name[1:].isdigit() for name in source_columns):
            raise TransferSchemaError(
                "January 2026 v1–v28 are a different PCA space and must not be mapped onto IEEE-CIS V*."
            )
    leaked = [name for name in source_columns if name in FORBIDDEN_FEATURES]
    if leaked:
        raise TransferSchemaError(
            "Source-model outputs cannot be used as IEEE-CIS model features: " + ", ".join(leaked)
        )


def transfer_status(feature_columns: list[str], source_columns: list[str]) -> dict[str, Any]:
    refuse_ieee_v_mapping(source_columns)
    ieee_only = [
        name
        for name in feature_columns
        if name.startswith(IEEE_ONLY_PREFIXES) or name in {"TransactionAmt", "TransactionDT", "relative_hour"}
    ]
    return {
        "scored": False,
        "reason": "schema_mismatch",
        "note": (
            "The trained IEEE-CIS feature set cannot be built honestly from the January 2026 export. "
            "v1–v28 are not IEEE-CIS V*. Source-model outputs are excluded. "
            "This dataset remains an external robustness candidate, not IEEE training data."
        ),
        "transferable_candidates": list(TRANSFERABLE_2026),
        "ieee_feature_count": len(feature_columns),
        "blocked_ieee_only_features": len(ieee_only),
    }
