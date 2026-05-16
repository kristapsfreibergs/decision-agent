from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

DEFAULT_MAX_TOKENS = 8192
EXTENDED_MAX_TOKENS = 32000
DEFAULT_TIMEOUT_SECONDS = 180
DOMAIN_DETECTION_MAX_TOKENS = 64
GOAL_CLASSIFICATION_MAX_TOKENS = 256
CLARIFICATION_MAX_TOKENS = 512


class LLMProvider(ABC):
    """Minimal interface all providers must implement."""

    @abstractmethod
    def complete(self, system: str, user: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
        """Return the assistant text response for a single turn."""
        ...

    def complete_with_tools(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        tool_choice: dict | None = None,
    ) -> dict:
        """
        Return a tool-aware provider response.

        Shape:
        {"stop_reason": "end_turn"|"tool_use", "content": str|list, "tool_use": dict|None}

        Providers without native tool support fall back to a single text completion.
        """
        user_text = "\n\n".join(
            str(message.get("content", ""))
            for message in messages
            if message.get("role") == "user"
        )
        text = self.complete(system, user_text, max_tokens=max_tokens)
        return {
            "stop_reason": "end_turn",
            "content": text,
            "tool_use": None,
            "tool_capable": False,
        }

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider identifier."""
        ...
