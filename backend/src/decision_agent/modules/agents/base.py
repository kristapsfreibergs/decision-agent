from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState


@dataclass(frozen=True)
class AgentResult:
    success: bool
    agent_id: str
    state_before: DecisionState
    state_after: DecisionState
    operator_results: list[OperatorResult] = field(default_factory=list)
    error: str | None = None


class AgentBase(ABC):
    agent_id: str
    operators: list[OperatorBase]
    target_phase: DecisionPhase | None

    def __init__(
        self,
        agent_id: str,
        operators: list[OperatorBase],
        *,
        target_phase: DecisionPhase | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.operators = operators
        self.target_phase = target_phase

    def run(self, state: DecisionState, context: OperatorContext) -> AgentResult:
        state_before = state
        op_results: list[OperatorResult] = []

        for op in self.operators:
            config = self._operator_config(op.name, state)
            result = op.execute(state, config, context)
            op_results.append(result)
            if not result.success:
                return AgentResult(
                    success=False,
                    agent_id=self.agent_id,
                    state_before=state_before,
                    state_after=state,
                    operator_results=op_results,
                    error=result.error,
                )
            if result.state_patch:
                state = state.apply_patch(result.state_patch)

        if self.target_phase is not None:
            state = state.transition_to(self.target_phase)

        return AgentResult(
            success=True,
            agent_id=self.agent_id,
            state_before=state_before,
            state_after=state,
            operator_results=op_results,
        )

    @abstractmethod
    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        ...

    def __repr__(self) -> str:
        ops = ", ".join(op.name for op in self.operators)
        return f"{self.__class__.__name__}({self.agent_id!r}, [{ops}])"
