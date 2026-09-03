"""User-facing classifier copy derived from classifier state, not world name."""

from __future__ import annotations

import re
from typing import Any

SCORED_REASONING = "Classifier output is available as supporting evidence."
UNSCORED_REASONING = (
    "Classifier output was unavailable because the required feature coverage was not satisfied."
)

_STALE_SENTENCES = re.compile(
    r"[^.]*("
    r"IEEE-CIS classifier was not applied"
    r"|IEEE-CIS (?:supervised )?model (?:was|is) not applied"
    r"|classifier was not applied"
    r"|This world has no supervised overlay"
    r"|no supervised overlay from our trained model"
    r")[^.]*\.?",
    re.IGNORECASE,
)


def classifier_reasoning_copy(classifier: dict[str, Any] | None) -> str:
    status = str((classifier or {}).get("status") or "")
    if status == "scored":
        return SCORED_REASONING
    if status == "not_scored":
        return UNSCORED_REASONING
    return ""


def strip_stale_classifier_claims(text: str | None) -> str:
    cleaned = _STALE_SENTENCES.sub("", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def sanitize_reasoning_text(text: str | None, classifier: dict[str, Any] | None = None) -> str:
    """Strip stale classifier-not-applied claims. Do not inject classifier copy.

    Detection reasoning and classifier evidence are separate surfaces.
    ``classifier`` is accepted for call-site compatibility and ignored.
    """
    del classifier
    return strip_stale_classifier_claims(text)
