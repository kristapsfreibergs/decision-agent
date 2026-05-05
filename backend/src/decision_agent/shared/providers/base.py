from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Minimal interface all providers must implement."""

    @abstractmethod
    def complete(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        """Return the assistant text response for a single turn."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider identifier."""
        ...
