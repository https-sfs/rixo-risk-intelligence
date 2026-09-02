"""Action-layer failures. Never converted into a simulated success."""


class ActionError(ValueError):
    """Bounded action proposal, approval, or execution was rejected."""
