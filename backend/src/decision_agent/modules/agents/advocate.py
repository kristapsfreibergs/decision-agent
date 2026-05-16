from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.operators.llm_extract import ExtractOperator
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState


class AdvocateAgent(AgentBase):
    """Reads eligible vendors and workspace files. Picks the strongest vendor
    and builds a detailed argument for why it should be chosen."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="advocate",
            operators=[
                ExtractOperator(),
                UpdateStateOperator(),
                LogOperator(),
            ],
            target_phase=DecisionPhase.EVALUATED,
        )

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "extract":
            return {
                "contract": self._make_contract(state),
                "state_patch_key": "scores",
            }
        if op_name == "update_state":
            return {"patch": {}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def _make_contract(self, state: DecisionState) -> dict[str, Any]:
        eligible = state.eligible_options
        vendor_names = [v.get("name", "?") for v in eligible]
        workspace_file = f"data/runs/{state.run_id}/workspace/advocate_position.md"

        return {
            "worker_id": f"{self.agent_id}_argue",
            "goal": (
                "You are the ADVOCATE in a procurement debate. "
                f"The eligible vendors are: {vendor_names}.\n\n"
                "Read the workspace files (requirements.md, market_research.md, "
                "risk_assessment.md) to understand the full context.\n\n"
                "Your job:\n"
                "1. Build a case FOR EACH eligible vendor — what makes it strong\n"
                "2. Use SPECIFIC EVIDENCE: exact prices, dates, certifications, "
                "specs, track record, compliance details\n"
                "3. For each vendor, state its strongest advantages and "
                "what it offers that others do not\n"
                "4. After presenting all cases, state which vendor you believe "
                "is the strongest pick and why\n\n"
                f"Write your full argued position to {workspace_file}.\n\n"
                "Then return ONLY this JSON:\n"
                '{"vendor_cases": [{"vendor": "<name>", '
                '"strengths": "<key strengths with evidence>", '
                '"unique_advantages": "<what this vendor offers that others do not>"}], '
                '"preferred_vendor": "<your pick>", '
                '"argument": "<your core argument in 2-3 sentences>"}'
            ),
            "read_paths": [
                f"data/runs/{state.run_id}/workspace/requirements.md",
                f"data/runs/{state.run_id}/workspace/market_research.md",
                f"data/runs/{state.run_id}/workspace/risk_assessment.md",
            ],
            "write_paths": [workspace_file],
            "allowed_tools": ["read_file", "write_file", "list_files"],
            "validators": ["write_scope"],
            "max_steps": 8,
            "output_schema": {
                "type": "object",
                "properties": {
                    "vendor_cases": {"type": "array"},
                    "preferred_vendor": {"type": "string"},
                    "argument": {"type": "string"},
                },
                "required": ["vendor_cases", "preferred_vendor", "argument"],
            },
            "context": {
                "task_title": state.requirements.get("task_title", ""),
                "task_summary": state.requirements.get("procurement_subject", ""),
            },
        }
