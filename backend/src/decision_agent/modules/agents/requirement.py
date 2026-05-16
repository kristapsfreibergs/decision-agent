from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.operators.llm_extract import ExtractOperator
from decision_agent.modules.operators.llm_classify import ClassifyOperator
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState


class RequirementAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id="requirement",
            operators=[
                ExtractOperator(),
                ClassifyOperator(),
                UpdateStateOperator(),
                LogOperator(),
            ],
            target_phase=DecisionPhase.EVIDENCE_INCOMPLETE,
        )

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "extract":
            return {
                "contract": self._make_contract(state, "extract"),
                "state_patch_key": "requirements",
            }
        if op_name == "classify":
            return {
                "contract": self._make_contract(state, "classify"),
                "state_patch_key": "requirements",
            }
        if op_name == "update_state":
            return {"patch": {"requirements": state.requirements}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def _make_contract(self, state: DecisionState, purpose: str) -> dict[str, Any]:
        return {
            "worker_id": f"{self.agent_id}_{purpose}",
            "goal": (
                "Extract and structure the procurement requirements from the task. "
                "Identify: what is being procured, quantity, quality standards, "
                "delivery timeline, budget ceiling, and compliance requirements."
            ),
            "read_paths": ["archive/knowledge/procurement/requirements/**"],
            "write_paths": [f"data/runs/{state.run_id}/workspace/requirements.md"],
            "allowed_tools": ["read_file", "write_file", "list_files"],
            "validators": ["write_scope"],
            "max_steps": 6,
            "output_schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "procurement_subject": {"type": "string"},
                    "quantity_and_quality": {"type": "string"},
                    "delivery_timeline": {"type": "string"},
                    "budget_ceiling": {"type": "string"},
                    "compliance_requirements": {"type": "array"},
                    "gaps": {"type": "array"},
                },
            },
            "context": {
                "task_title": state.requirements.get("task_title", ""),
                "task_summary": state.requirements.get("task_summary", ""),
            },
        }
