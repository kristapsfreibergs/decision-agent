from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_monitor_outcome import MonitorOutcomeOperator
from decision_agent.modules.operators.det_validate_state import ValidateStateOperator
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState


class StateValidationAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id="state_validation",
            operators=[
                ValidateStateOperator(),
                MonitorOutcomeOperator(),
                LogOperator(),
            ],
            target_phase=DecisionPhase.VALIDATED,
        )

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "validate_state":
            return {"required_fields": ["requirements", "recommendation"]}
        if op_name == "monitor_outcome":
            return {}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}
