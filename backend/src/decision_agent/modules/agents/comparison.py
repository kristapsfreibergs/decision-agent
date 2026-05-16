from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.operators.llm_compare import CompareOperator
from decision_agent.modules.operators.llm_explain import ExplainOperator
from decision_agent.modules.state.decision_state import DecisionState


class ComparisonAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id="comparison",
            operators=[
                CompareOperator(),
                ExplainOperator(),
                UpdateStateOperator(),
                LogOperator(),
            ],
            target_phase=None,
        )

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "compare":
            return {
                "contract": self._make_contract(state),
                "state_patch_key": "comparison",
            }
        if op_name == "explain":
            return {
                "contract": self._make_explain_contract(state),
                "state_patch_key": "comparison",
            }
        if op_name == "update_state":
            return {"patch": {"comparison": state.comparison}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def _make_contract(self, state: DecisionState) -> dict[str, Any]:
        return {
            "worker_id": f"{self.agent_id}_compare",
            "goal": (
                "Compare the top-ranked vendors side by side. "
                "Highlight trade-offs between price, delivery, quality, and risk."
            ),
            "read_paths": [f"data/runs/{state.run_id}/workspace/*"],
            "write_paths": [],
            "allowed_tools": ["read_file", "list_files"],
            "validators": [],
            "max_steps": 4,
            "output_schema": {"type": "object"},
            "context": {
                "task_title": state.requirements.get("task_title", ""),
                "task_summary": "Compare ranked vendors",
            },
        }

    def _make_explain_contract(self, state: DecisionState) -> dict[str, Any]:
        return {
            "worker_id": f"{self.agent_id}_explain",
            "goal": "Explain the comparison results and trade-offs clearly.",
            "read_paths": [],
            "write_paths": [],
            "allowed_tools": [],
            "validators": [],
            "max_steps": 2,
            "output_schema": {"type": "object"},
            "context": {"task_title": "Explain comparison", "task_summary": ""},
        }
