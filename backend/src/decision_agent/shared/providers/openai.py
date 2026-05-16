from __future__ import annotations

import os

from decision_agent.shared.providers.base import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TIMEOUT_SECONDS,
    LLMProvider,
)
from decision_agent.shared.providers.retry import with_retry


class OpenAIProvider(LLMProvider):
    """Calls OpenAI via the Responses API."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self._timeout = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        self._max_tokens = int(os.environ.get("OPENAI_MAX_TOKENS", "8000"))
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY is not set.")

    @property
    def name(self) -> str:
        return f"openai/{self._model}"

    def complete(self, system: str, user: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        client = _client(self._api_key, self._timeout)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
        # Use configured max_tokens, cap at environment setting if needed
        effective_max_tokens = min(max_tokens, self._max_tokens)
        response = with_retry(lambda: client.chat.completions.create(
            model=self._model,
            max_tokens=effective_max_tokens,
            messages=messages,
            # Sampling parameters — set explicitly to API defaults for reproducibility.
            temperature=1.0,       # default: 1.0 — not reduced, preserves natural decision variance
            top_p=1.0,             # default: 1.0 — full token distribution, no nucleus truncation
        ))
        text = response.choices[0].message.content if response.choices else ""
        return text


def _client(api_key: str, timeout: float):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is not installed. Run: pip install openai") from exc
    return OpenAI(api_key=api_key, timeout=timeout, max_retries=0)
