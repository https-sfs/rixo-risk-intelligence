"""Provider-agnostic investigation interface."""

from __future__ import annotations

from typing import Any, Protocol

from agent.schema import InvestigationReport


class InvestigationProvider(Protocol):
    name: str

    def reason(self, facts: dict[str, Any]) -> InvestigationReport:
        """Produce a report from deterministic facts only."""
