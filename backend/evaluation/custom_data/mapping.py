"""Schema-first field mapping. Exact names outrank aliases; heuristics are never silent."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from evaluation.custom_data.schema import (
    CANONICAL_FIELDS,
    FIELD_ALIASES,
    FIELD_LABELS,
    FIELD_QUESTIONS,
    IDENTIFICATION_FIELDS,
    IEEE_EXACT_FIELDS,
    REQUIRED_USEFUL,
    CustomDataError,
    normalize_name,
)
from models.ieee_fraud.features import discover_feature_columns

IEEE_FEATURE_BLOCKLIST = re.compile(r"^(card[1-6]|C\d+|D\d+|M\d+|V\d+|id_\d+|addr[12])$")

IEEE_REASONS = {
    "TransactionID": "Official IEEE-CIS transaction identifier.",
    "TransactionAmt": "Official IEEE-CIS transaction amount.",
    "TransactionAMT": "Official IEEE-CIS transaction amount.",
    "TransactionDT": (
        "Official IEEE-CIS elapsed-time field. It is relative seconds from an unpublished "
        "origin, not a calendar date."
    ),
    "ProductCD": "Official IEEE-CIS product code.",
    "isFraud": "Official IEEE-CIS evaluation label. Used only as user-provided ground truth.",
}


def _column_lookup(columns: list[str]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for name in columns:
        lookup.setdefault(normalize_name(name), name)
        lookup.setdefault(name, name)
    return lookup


def _exact_schema_match(target: str, columns: list[str], used: set[str]) -> str | None:
    available = [name for name in columns if name not in used]
    if target in available:
        return target
    for official in IEEE_EXACT_FIELDS.get(target, ()):
        if official in available:
            return official
    lookup = _column_lookup(available)
    if target != "timestamp":
        hit = lookup.get(normalize_name(target))
        if hit and hit not in used:
            return hit
    for official in IEEE_EXACT_FIELDS.get(target, ()):
        hit = lookup.get(normalize_name(official))
        if hit and hit not in used:
            return hit
    return None


def _alias_matches(target: str, columns: list[str], used: set[str]) -> list[str]:
    aliases = {normalize_name(alias) for alias in FIELD_ALIASES[target]}
    matches: list[str] = []
    for name in columns:
        if name in used:
            continue
        if normalize_name(name) in aliases:
            matches.append(name)
    return matches


def _heuristic_match(target: str, columns: list[str], used: set[str]) -> list[str]:
    hits: list[str] = []
    for name in columns:
        if name in used or IEEE_FEATURE_BLOCKLIST.match(name):
            continue
        normalized = normalize_name(name)
        if target == "amount" and ("amount" in normalized or normalized == "value"):
            hits.append(name)
        elif target == "timestamp" and any(token in normalized for token in ("time", "date", "when")):
            hits.append(name)
        elif target == "transaction_id" and (
            normalized in {"id", "txid"} or ("txn" in normalized and "id" in normalized)
        ):
            hits.append(name)
    return hits


def _proposal(
    target: str,
    suggested: str | None,
    candidates: list[str],
    confidence: str,
    tier: str,
    reason: str,
    ambiguous: bool,
) -> dict[str, Any]:
    auto_accepted = bool(suggested) and confidence == "high" and not ambiguous
    status = (
        "ambiguous"
        if ambiguous
        else "detected"
        if suggested
        else "unmapped"
    )
    return {
        "target": target,
        "label": FIELD_LABELS[target],
        "question": FIELD_QUESTIONS[target],
        "suggested": suggested,
        "candidates": candidates,
        "ambiguous": ambiguous,
        "confidence": confidence if suggested or ambiguous else "unmapped",
        "tier": tier,
        "reason": reason,
        "auto_accepted": auto_accepted,
        "required": target in REQUIRED_USEFUL,
        "optional": target not in REQUIRED_USEFUL,
        "status": status,
    }


def propose_mappings(columns: list[str]) -> list[dict[str, Any]]:
    used: set[str] = set()
    proposals: list[dict[str, Any]] = []
    for target in CANONICAL_FIELDS:
        exact = _exact_schema_match(target, columns, used)
        if exact:
            used.add(exact)
            reason = IEEE_REASONS.get(
                exact,
                f"{exact} matches the {FIELD_LABELS[target].lower()} field exactly.",
            )
            proposals.append(
                _proposal(
                    target,
                    exact,
                    [exact],
                    "high",
                    "exact_schema",
                    reason,
                    ambiguous=False,
                )
            )
            continue

        aliases = _alias_matches(target, columns, used)
        if len(aliases) == 1:
            chosen = aliases[0]
            used.add(chosen)
            proposals.append(
                _proposal(
                    target,
                    chosen,
                    aliases,
                    "high",
                    "strong_alias",
                    f"{chosen} is a strong alias for {FIELD_LABELS[target].lower()}.",
                    ambiguous=False,
                )
            )
            continue
        if len(aliases) > 1:
            proposals.append(
                _proposal(
                    target,
                    None,
                    aliases,
                    "unmapped",
                    "strong_alias",
                    (
                        f"{FIELD_QUESTIONS[target]} More than one column could match "
                        f"{FIELD_LABELS[target].lower()}, so nothing was assumed."
                    ),
                    ambiguous=True,
                )
            )
            continue

        heuristics = _heuristic_match(target, columns, used)
        if len(heuristics) == 1:
            proposals.append(
                _proposal(
                    target,
                    heuristics[0],
                    heuristics,
                    "low",
                    "heuristic",
                    (
                        f"{FIELD_QUESTIONS[target]} {heuristics[0]} is only a low-confidence "
                        "guess and was not accepted automatically."
                    ),
                    ambiguous=False,
                )
            )
            continue
        if len(heuristics) > 1:
            proposals.append(
                _proposal(
                    target,
                    None,
                    heuristics,
                    "unmapped",
                    "heuristic",
                    f"{FIELD_QUESTIONS[target]} Several columns look possible; none were assumed.",
                    ambiguous=True,
                )
            )
            continue

        proposals.append(
            _proposal(
                target,
                None,
                [],
                "unmapped",
                "none",
                f"{FIELD_QUESTIONS[target]} No matching column was found.",
                ambiguous=False,
            )
        )
    return proposals


def high_confidence_mapping(proposals: list[dict[str, Any]]) -> dict[str, str]:
    return {
        str(item["target"]): str(item["suggested"])
        for item in proposals
        if item.get("auto_accepted") and item.get("suggested")
    }


def summarize_proposals(proposals: list[dict[str, Any]]) -> dict[str, Any]:
    identified = []
    for item in proposals:
        if item["target"] not in IDENTIFICATION_FIELDS:
            continue
        identified.append(
            {
                "target": item["target"],
                "label": item["label"],
                "column": item.get("suggested") if item.get("auto_accepted") else None,
                "confidence": item.get("confidence"),
                "identified": bool(item.get("auto_accepted")),
                "question": item["question"],
                "reason": item.get("reason"),
            }
        )
    accepted = sum(1 for item in identified if item["identified"])
    return {
        "fields": identified,
        "identified_count": accepted,
        "identification_total": len(IDENTIFICATION_FIELDS),
        "headline": (
            f"{accepted}/{len(IDENTIFICATION_FIELDS)} required fields identified automatically."
        ),
        "needs_review": any(
            item.get("ambiguous") or item.get("confidence") == "low" for item in proposals
        ),
    }


def mapping_readiness(mapping: dict[str, str] | None) -> dict[str, Any]:
    current = mapping or {}
    missing = [field for field in REQUIRED_USEFUL if not current.get(field)]
    return {
        "ready": not missing,
        "missing": [
            {
                "target": field,
                "label": FIELD_LABELS[field],
                "question": FIELD_QUESTIONS[field],
            }
            for field in missing
        ],
        "reason": (
            None
            if not missing
            else "Map "
            + ", ".join(FIELD_LABELS[field].lower() for field in missing)
            + " before analysis. Incorrect mappings are not guessed."
        ),
    }


def validate_mapping(columns: list[str], mapping: dict[str, Any]) -> dict[str, str]:
    confirmed: dict[str, str] = {}
    assigned: dict[str, str] = {}
    for target in CANONICAL_FIELDS:
        source = mapping.get(target)
        if source in (None, "", False):
            continue
        source_name = str(source)
        if source_name not in columns:
            raise CustomDataError(f"Mapped column {source_name!r} is not in the uploaded CSV.")
        if source_name in assigned and assigned[source_name] != target:
            raise CustomDataError(
                f"Column {source_name!r} is mapped to both {assigned[source_name]} and {target}. "
                "Choose one target."
            )
        confirmed[target] = source_name
        assigned[source_name] = target
    return confirmed


def apply_mapping(frame: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    confirmed = validate_mapping([str(name) for name in frame.columns], mapping)
    out = pd.DataFrame(index=frame.index)
    for target, source in confirmed.items():
        out[target] = frame[source]
    for name in discover_feature_columns(frame.columns):
        if name not in out.columns:
            out[name] = frame[name]
    return out
