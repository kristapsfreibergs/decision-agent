from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class MemoryItem:
    source_run_id: str
    worker_id: str
    evidence_class: str
    content: str
    created_at: str
    domain: str
    authority_score: float = 0.0
    extra: dict[str, Any] | None = None


@dataclass
class MemoryHit:
    memory_id: str
    source_run_id: str
    worker_id: str
    evidence_class: str
    excerpt: str
    authority_score: float
    created_at: str
    relevance_score: float


class MemoryProvider(ABC):
    """Interface for cross-run evidence memory.

    search() always takes a scope dict so retrieval is bounded to the current
    decision domain and allowed evidence classes — DSC enforced at the interface.
    """

    @abstractmethod
    def search(
        self,
        query: str,
        scope: dict[str, Any],
        limit: int = 10,
    ) -> list[MemoryHit]:
        """Return MemoryHits matching query within the scope boundary."""
        ...

    @abstractmethod
    def write(self, item: MemoryItem) -> str:
        """Persist a MemoryItem; return its memory_id."""
        ...

    @abstractmethod
    def count(self, domain: str) -> int:
        """Return number of memory items for a domain."""
        ...
