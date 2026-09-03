"""Investigation LLM failures. These are never turned into fabricated reports."""


class LLMProviderError(RuntimeError):
    """Provider is missing, unreachable, or returned an unusable response."""


class LLMOutputError(LLMProviderError):
    """Model output was malformed or failed citation/schema validation."""
