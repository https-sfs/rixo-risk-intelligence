"""LLM investigation provider. Missing keys and bad output fail closed."""

from __future__ import annotations

import os
from typing import Any, Protocol

from agent.errors import LLMOutputError, LLMProviderError
from agent.facts import build_llm_prompt
from agent.prompts import build_investigation_messages, prepare_llm_facts
from agent.providers.client import OpenAICompatibleClient
from agent.schema import InvestigationReport
from agent.validation import parse_and_validate_llm_report

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 30.0


class LLMClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return model text. Test doubles must use this method."""


def read_llm_api_key() -> str:
    return os.environ.get("LLM_API_KEY", "").strip()


class LLMInvestigationProvider:
    """OpenAI-compatible reasoning provider. Not used unless configured."""

    name = "llm"

    def __init__(
        self,
        client: LLMClient | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._client = client
        self._api_key = read_llm_api_key() if api_key is None else api_key.strip()
        self._base_url = (base_url or os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._model = model or os.environ.get("LLM_MODEL") or DEFAULT_MODEL
        self._timeout_seconds = timeout_seconds

    def reason(self, facts: dict[str, Any]) -> InvestigationReport:
        client = self._require_client()
        system_prompt, user_prompt = build_investigation_messages(facts)
        try:
            raw = client.complete(system_prompt, user_prompt)
        except LLMOutputError:
            raise
        except LLMProviderError:
            raise
        except TimeoutError as exc:
            raise LLMProviderError("LLM request timed out") from exc
        except Exception as exc:
            raise LLMProviderError(f"LLM provider request failed: {exc.__class__.__name__}") from exc
        report = parse_and_validate_llm_report(raw, prepare_llm_facts(facts))
        report.provider = self.name
        report.human_approval_required = True
        return report

    def _require_client(self) -> LLMClient:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise LLMProviderError(
                "No investigation LLM is configured. Set LLM_API_KEY. "
                "Automated tests use a test double or DeterministicReasoner "
                "and do not need an API key."
            )
        return OpenAICompatibleClient(
            api_key=self._api_key,
            base_url=self._base_url,
            model=self._model,
            timeout_seconds=self._timeout_seconds,
        )


class UnconfiguredLLMProvider:
    """Phase 2B placeholder. Still fails closed when no key is present."""

    name = "llm_unconfigured"

    def reason(self, facts: dict[str, Any]) -> InvestigationReport:
        _ = build_llm_prompt(facts)
        key = os.environ.get("INVESTIGATION_LLM_API_KEY", "").strip() or read_llm_api_key()
        if not key:
            raise RuntimeError(
                "No investigation LLM is configured. "
                "Automated tests use DeterministicReasoner and do not need an API key."
            )
        raise RuntimeError(
            "Use LLMInvestigationProvider with LLM_API_KEY for real model calls."
        )
