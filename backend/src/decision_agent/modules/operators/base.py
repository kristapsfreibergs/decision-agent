from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.shared.memory.base import MemoryProvider
from decision_agent.shared.providers.base import LLMProvider


@dataclass(frozen=True)
class OperatorResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    state_patch: dict[str, Any] = field(default_factory=dict)
    audit_entries: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass
class OperatorContext:
    run_id: str
    agent_id: str
    project_root: Path
    audit_path: Path
    provider: LLMProvider | None
    layer_config: LayerConfig
    policies: dict[str, Any] = field(default_factory=dict)
    memory: MemoryProvider | None = None


class OperatorBase(ABC):
    name: str
    is_deterministic: bool

    def __init__(self, name: str, *, is_deterministic: bool) -> None:
        self.name = name
        self.is_deterministic = is_deterministic

    @abstractmethod
    def execute(
        self,
        state: Any,
        config: dict[str, Any],
        context: OperatorContext,
    ) -> OperatorResult:
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name!r})"
