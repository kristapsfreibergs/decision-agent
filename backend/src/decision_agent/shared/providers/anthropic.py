from __future__ import annotations

import os

from decision_agent.shared.providers.base import LLMProvider


class AnthropicProvider(LLMProvider):
    """Calls Claude via the Anthropic SDK."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        if not self._api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set.")

    @property
    def name(self) -> str:
        return f"anthropic/{self._model}"

    def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package is not installed. Run: pip install anthropic"
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text
