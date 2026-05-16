from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_check import CheckOperator
from decision_agent.modules.operators.det_filter import FilterOperator
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState


class EligibilityAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id="eligibility",
            operators=[
                CheckOperator(),
                FilterOperator(),
                UpdateStateOperator(),
                LogOperator(),
            ],
            target_phase=DecisionPhase.ELIGIBLE,
        )

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "check":
            return {"output": state.evidence, "contract": {}}
        if op_name == "filter":
            candidates = state.evidence.get("active_vendors", [])
            if isinstance(candidates, list) and candidates and isinstance(candidates[0], str):
                candidates = [{"name": v} for v in candidates]
            hard_constraints = self._build_constraints(state)
            return {"candidates": candidates, "hard_constraints": hard_constraints}
        if op_name == "update_state":
            return {"patch": {"eligible_options": state.eligible_options}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def _build_constraints(self, state: DecisionState) -> list[dict[str, Any]]:
        constraints: list[dict[str, Any]] = []
        compliance = state.requirements.get("compliance_requirements", [])
        if compliance:
            for req in compliance:
                if isinstance(req, str):
                    constraints.append({"field": req, "op": "truthy", "value": True})
        return constraints
