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

    def complete_with_tools(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int = 4096,
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

        client = anthropic.Anthropic(api_key=self._api_key)
        request: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "tools": tools,
            "messages": messages,
        }
        if tool_choice is not None:
            request["tool_choice"] = tool_choice

        response = client.messages.create(**request)
        if response.stop_reason == "tool_use":
            tool_block = next(block for block in response.content if block.type == "tool_use")
            return {
                "stop_reason": "tool_use",
                "content": [_content_block_to_dict(block) for block in response.content],
                "tool_use": {
                    "id": tool_block.id,
                    "name": tool_block.name,
                    "input": tool_block.input,
                },
            }

        text = next((block.text for block in response.content if hasattr(block, "text")), "")
        return {"stop_reason": "end_turn", "content": text, "tool_use": None}


def _content_block_to_dict(block: object) -> dict:
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    if isinstance(block, dict):
        return block
    return {
        "type": getattr(block, "type", "text"),
        "text": getattr(block, "text", ""),
    }
