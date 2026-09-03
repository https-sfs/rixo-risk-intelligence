"""OpenAI-compatible chat client using the existing httpx dependency."""

from __future__ import annotations

from typing import Any

import httpx

from agent.errors import LLMProviderError


class OpenAICompatibleClient:
    """Real HTTP client for OpenAI-compatible /chat/completions endpoints."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key:
            raise LLMProviderError("LLM_API_KEY is missing")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = httpx.Timeout(timeout_seconds)

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self._base_url}/chat/completions"
        body: dict[str, Any] = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(url, json=body, headers=headers, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise LLMProviderError("LLM request timed out") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"LLM provider request failed: {exc.__class__.__name__}") from exc
        except ValueError as exc:
            raise LLMProviderError("LLM provider returned a non-JSON HTTP body") from exc

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("LLM provider response was missing message content") from exc
        if not isinstance(content, str):
            raise LLMProviderError("LLM provider response content was not text")
        return content
