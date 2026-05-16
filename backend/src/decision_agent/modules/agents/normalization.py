from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_normalize import NormalizeOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.state.decision_state import DecisionState


class NormalizationAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id="normalization",
            operators=[
                NormalizeOperator(),
                UpdateStateOperator(),
                LogOperator(),
            ],
            target_phase=None,
        )

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "normalize":
            return {"data": {**state.requirements, **state.evidence}}
        if op_name == "update_state":
            return {"patch": {"normalized_data": state.normalized_data}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}
