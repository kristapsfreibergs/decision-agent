from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.operators.llm_recommend import RecommendOperator
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState


class RecommendationAgent(AgentBase):
    """Reads the advocate and challenger positions, resolves the debate,
    and writes the final recommendation with full argument trail."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="recommendation",
            operators=[
                RecommendOperator(),
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
        if op_name == "update_state":
            return {"patch": {}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def _make_contract(self, state: DecisionState) -> dict[str, Any]:
        workspace_file = f"data/runs/{state.run_id}/workspace/recommendation_brief.md"

        # Pass debate context
        advocate_output = state.scores
        challenger_output = state.comparison
        advocate_vendor = ""
        challenger_best = ""
        challenger_conceded = None
        if isinstance(advocate_output, dict):
            advocate_vendor = advocate_output.get("preferred_vendor", "")
        if isinstance(challenger_output, dict):
            challenger_conceded = challenger_output.get("concede")
            challenger_best = challenger_output.get("best_match", "")

        return {
            "worker_id": f"{self.agent_id}_recommend",
            "goal": (
                "You are the JUDGE resolving a procurement debate.\n\n"
                "Two agents have debated which vendor to recommend:\n"
                f"- The ADVOCATE presented cases for all eligible vendors and preferred: {advocate_vendor}\n"
                f"- The CHALLENGER {'conceded' if challenger_conceded else 'disagreed'}"
                f"{' and argued for: ' + challenger_best if challenger_best and not challenger_conceded else ''}\n\n"
                "Read both positions (advocate_position.md, challenger_position.md) "
                "and the ORIGINAL REQUIREMENTS (requirements.md).\n\n"
                "Your job:\n"
                "1. Evaluate both arguments on their EVIDENCE, not rhetoric\n"
                "2. Check disputed claims against the original requirements and source documents\n"
                "3. The vendor that best matches the ORIGINAL TASK REQUIREMENTS wins\n"
                "4. Write a final recommendation that:\n"
                "   - Names the recommended vendor\n"
                "   - Explains WHY in one paragraph citing specific evidence\n"
                "   - Acknowledges valid points from the losing side\n"
                "   - Lists risks identified by the challenger that must be mitigated\n"
                "   - States contract conditions\n\n"
                f"Write the final brief to {workspace_file}.\n\n"
                "Then return ONLY this JSON:\n"
                '{"status": "ok", "written_to": "<path>", '
                '"recommended_vendor": "<vendor name>", '
                '"rationale": "<one-paragraph argument citing evidence>", '
                '"runner_up": "<vendor name or null>", '
                '"debate_resolved": "<how you resolved the debate>", '
                '"risks": ["<risk and mitigation>"], '
                '"conditions": ["<contract condition>"]}'
            ),
            "read_paths": [
                f"data/runs/{state.run_id}/workspace/*",
            ],
            "write_paths": [workspace_file],
            "allowed_tools": ["read_file", "write_file", "list_files"],
            "validators": ["write_scope"],
            "max_steps": 8,
            "output_schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "written_to": {"type": "string"},
                    "recommended_vendor": {"type": "string"},
                    "rationale": {"type": "string"},
                    "runner_up": {},
                    "debate_resolved": {"type": "string"},
                    "risks": {"type": "array"},
                    "conditions": {"type": "array"},
                },
                "required": ["status", "written_to", "recommended_vendor", "rationale"],
            },
            "context": {
                "task_title": state.requirements.get("task_title", ""),
                "task_summary": state.requirements.get("procurement_subject", ""),
            },
        }
