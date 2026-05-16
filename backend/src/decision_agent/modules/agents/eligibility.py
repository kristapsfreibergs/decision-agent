from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_filter import FilterOperator
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState


class EligibilityAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id="eligibility",
            operators=[
                FilterOperator(),
                UpdateStateOperator(),
                LogOperator(),
            ],
            target_phase=DecisionPhase.ELIGIBLE,
        )

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "filter":
            candidates = state.evidence.get("active_vendors", [])
            if isinstance(candidates, list) and candidates and isinstance(candidates[0], str):
                candidates = [{"name": v} for v in candidates]
            hard_constraints = self._load_hard_constraints(state)
            return {"candidates": candidates, "hard_constraints": hard_constraints}
        if op_name == "update_state":
            return {"patch": {}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def _load_hard_constraints(self, state: DecisionState) -> list[dict[str, Any]]:
        for key in ("hard_constraints", "constraints"):
            raw = state.requirements.get(key)
            if isinstance(raw, list):
                valid = [c for c in raw if isinstance(c, dict) and c.get("field")]
                if valid:
                    return valid
        result: list[dict[str, Any]] = []
        for req in state.requirements.get("compliance_requirements", []):
            if isinstance(req, str):
                result.append({"field": req, "op": "truthy", "value": True})
        return result
