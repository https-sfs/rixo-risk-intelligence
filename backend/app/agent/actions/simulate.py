"""Simulation-only executor. No payment, bank, or production APIs."""

from __future__ import annotations

from agent.actions.errors import ActionError
from agent.actions.models import ALLOWED_ACTION_TYPES

SIMULATION_MESSAGES = {
    "tighten_rule": "SIMULATED: narrowed review/risk rule to {scope}.",
    "monitor": "SIMULATED: monitoring policy attached to {scope}.",
    "review": "SIMULATED: investigation case queued for human review of {scope}.",
    "no_action": "SIMULATED: no intervention applied.",
}


def simulate_action(action_type: str, scope: str) -> str:
    if action_type not in ALLOWED_ACTION_TYPES:
        raise ActionError(f"Executor rejected unsupported action type: {action_type}")
    template = SIMULATION_MESSAGES[action_type]
    return template.format(scope=scope)
