from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.operators.llm_explain import ExplainOperator
from decision_agent.modules.operators.llm_recommend import RecommendOperator
from decision_agent.modules.operators.mem_write import MemoryWriteOperator
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState


class RecommendationAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id="recommendation",
            operators=[
                RecommendOperator(),
                ExplainOperator(),
                MemoryWriteOperator(),
                UpdateStateOperator(),
                LogOperator(),
            ],
            target_phase=DecisionPhase.RECOMMENDED,
        )

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "recommend":
            return {
                "contract": self._make_contract(state),
                "state_patch_key": "recommendation",
            }
        if op_name == "explain":
            return {
                "contract": self._make_explain_contract(state),
                "state_patch_key": "recommendation",
            }
        if op_name == "mem_write":
            return {"evidence_items": self._build_evidence_items(state)}
        if op_name == "update_state":
            return {"patch": {"recommendation": state.recommendation}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def _make_contract(self, state: DecisionState) -> dict[str, Any]:
        return {
            "worker_id": f"{self.agent_id}_recommend",
            "goal": (
                "Produce the final procurement recommendation brief. "
                "Include: recommended vendor(s), key risks and mitigations, "
                "suggested contract conditions, and what the human must approve."
            ),
            "dar_action_type": "publish_recommendation",
            "read_paths": [
                f"data/runs/{state.run_id}/workspace/requirements.md",
                f"data/runs/{state.run_id}/workspace/evaluation.md",
                f"data/runs/{state.run_id}/workspace/risk_assessment.md",
            ],
            "write_paths": [f"data/runs/{state.run_id}/workspace/recommendation_brief.md"],
            "allowed_tools": ["read_file", "write_file", "list_files"],
            "validators": ["write_scope"],
            "max_steps": 6,
            "output_schema": {"type": "object"},
            "context": {
                "task_title": state.requirements.get("task_title", ""),
                "task_summary": state.requirements.get("procurement_subject", ""),
            },
        }

    def _make_explain_contract(self, state: DecisionState) -> dict[str, Any]:
        return {
            "worker_id": f"{self.agent_id}_explain",
            "goal": "Explain the recommendation rationale.",
            "read_paths": [],
            "write_paths": [],
            "allowed_tools": [],
            "validators": [],
            "max_steps": 2,
            "output_schema": {"type": "object"},
            "context": {"task_title": "Explain recommendation", "task_summary": ""},
        }

    def _build_evidence_items(self, state: DecisionState) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        rec = state.recommendation
        if rec.get("recommended_vendor"):
            items.append({
                "evidence_class": "recommendation",
                "content": f"Recommended: {rec['recommended_vendor']}. {rec.get('summary', '')}",
                "authority_score": 0.5,
            })
        return items
