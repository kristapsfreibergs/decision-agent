from __future__ import annotations

import os

from decision_agent.shared.providers.base import DEFAULT_MAX_TOKENS, DEFAULT_TIMEOUT_SECONDS, LLMProvider
from decision_agent.shared.providers.retry import with_retry


class AnthropicProvider(LLMProvider):
    """Calls Claude via the Anthropic SDK."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        self._timeout = float(os.environ.get("ANTHROPIC_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
        self._prompt_cache = os.environ.get("ANTHROPIC_PROMPT_CACHE", "false").lower() == "true"
        if not self._api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set.")

    @property
    def name(self) -> str:
        return f"anthropic/{self._model}"

    def complete(self, system: str, user: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        text, _ = self.complete_with_usage(system, user, max_tokens=max_tokens)
        return text

    def complete_with_usage(
        self, system: str, user: str, *, max_tokens: int = DEFAULT_MAX_TOKENS
    ) -> tuple[str, dict]:
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package is not installed. Run: pip install anthropic"
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key, timeout=self._timeout, max_retries=1)
        system_param = (
            [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
            if self._prompt_cache else system
        )
        message = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_param,
            messages=[{"role": "user", "content": user}],
            # Sampling parameters — set explicitly to API defaults for reproducibility.
            # These values are cited in thesis Table A.1 (Experimental Configuration).
            temperature=1.0,       # default: 1.0 — not reduced, preserves natural decision variance
            # top_p is not set — Anthropic API rejects requests with both temperature and top_p
            # top_k is not set — Anthropic default is disabled (no top-k filtering applied)
            # stop_sequences is not set — generation runs until max_tokens or end_turn
            # stream is not set (defaults to False) — full response returned in one payload
            # metadata is not set — no user_id attribution passed to the API
        )
        usage = {
            "input_tokens": getattr(message.usage, "input_tokens", 0),
            "output_tokens": getattr(message.usage, "output_tokens", 0),
            "cache_read_tokens": getattr(message.usage, "cache_read_input_tokens", 0),
            "cache_write_tokens": getattr(message.usage, "cache_creation_input_tokens", 0),
        }
        return message.content[0].text, usage

    def complete_with_tools(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        tool_choice: dict | None = None,
    ) -> dict:
        if not tools:
            return super().complete_with_tools(
                system,
                messages,
                tools,
                max_tokens=max_tokens,
                tool_choice=tool_choice,
            )

        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "anthropic package is not installed. Run: pip install anthropic"
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key, timeout=self._timeout, max_retries=0)
        request: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "tools": tools,
            "messages": messages,
        }
        if tool_choice is not None:
            request["tool_choice"] = tool_choice

        response = with_retry(lambda: client.messages.create(**request))
        if response.stop_reason == "tool_use":
            tool_blocks = [block for block in response.content if block.type == "tool_use"]
            tool_uses = [
                {
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
                for block in tool_blocks
            ]
            return {
                "stop_reason": "tool_use",
                "content": [_content_block_to_dict(block) for block in response.content],
                "tool_use": tool_uses[0] if tool_uses else None,
                "tool_uses": tool_uses,
                "tool_capable": True,
                "usage": {
                    "input_tokens": getattr(response.usage, "input_tokens", 0),
                    "output_tokens": getattr(response.usage, "output_tokens", 0),
                },
            }

        text = next((block.text for block in response.content if hasattr(block, "text")), "")
        return {
            "stop_reason": "end_turn",
            "content": text,
            "tool_use": None,
            "tool_capable": True,
            "usage": {
                "input_tokens": getattr(response.usage, "input_tokens", 0),
                "output_tokens": getattr(response.usage, "output_tokens", 0),
            },
        }


def _content_block_to_dict(block: object) -> dict:
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    if isinstance(block, dict):
        return block
    return {
        "type": getattr(block, "type", "text"),
        "text": getattr(block, "text", ""),
    }
