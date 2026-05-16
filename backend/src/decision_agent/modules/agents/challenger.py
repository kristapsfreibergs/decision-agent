from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.operators.llm_extract import ExtractOperator
from decision_agent.modules.state.decision_state import DecisionState


class ChallengerAgent(AgentBase):
    """Reads the original task requirements and the advocate's cases.
    Challenges each vendor against what was actually asked for.
    Pushes toward the vendor that best satisfies the original need."""

    def __init__(self) -> None:
        super().__init__(
            agent_id="challenger",
            operators=[
                ExtractOperator(),
                UpdateStateOperator(),
                LogOperator(),
            ],
            target_phase=None,
        )

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "extract":
            return {
                "contract": self._make_contract(state),
                "state_patch_key": "comparison",
            }
        if op_name == "update_state":
            return {"patch": {}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def _make_contract(self, state: DecisionState) -> dict[str, Any]:
        eligible = state.eligible_options
        vendor_names = [v.get("name", "?") for v in eligible]
        workspace_file = f"data/runs/{state.run_id}/workspace/challenger_position.md"

        advocate_output = state.scores
        preferred = ""
        if isinstance(advocate_output, dict):
            preferred = advocate_output.get("preferred_vendor", "")

        return {
            "worker_id": f"{self.agent_id}_challenge",
            "goal": (
                "You are the CHALLENGER in a procurement debate. "
                f"The eligible vendors are: {vendor_names}.\n"
                f"The advocate preferred: {preferred}\n\n"
                "Read the ORIGINAL REQUIREMENTS (requirements.md) first. "
                "Then read the advocate's position (advocate_position.md) and "
                "the market research.\n\n"
                "Your job is to challenge each vendor case AGAINST THE ORIGINAL "
                "TASK REQUIREMENTS:\n"
                "1. For each vendor the advocate presented, ask: does this vendor "
                "actually deliver what was asked for? Use specific evidence.\n"
                "2. Find gaps between what the task requires and what each vendor "
                "offers — things the advocate glossed over or missed\n"
                "3. Challenge the advocate's preferred pick — is it truly the best "
                "match for what was originally requested?\n"
                "4. If another vendor better matches the original requirements, "
                "argue for it with evidence\n"
                "5. If the advocate's pick IS the best match, concede — but list "
                "every risk and condition that must be addressed\n"
                "6. Do NOT disagree for the sake of disagreeing. Follow the evidence.\n\n"
                f"Write your full challenge to {workspace_file}.\n\n"
                "Then return ONLY this JSON:\n"
                '{"concede": true|false, '
                '"advocate_vendor": "<the vendor advocate preferred>", '
                '"best_match": "<vendor that best matches original requirements>", '
                '"challenges": [{"vendor": "<name>", '
                '"gap": "<specific gap vs original requirements>"}], '
                '"counter_argument": "<your position in 2-3 sentences>", '
                '"unresolved_risks": ["<risk that must be addressed regardless of winner>"]}'
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
                    "concede": {"type": "boolean"},
                    "advocate_vendor": {"type": "string"},
                    "best_match": {"type": "string"},
                    "challenges": {"type": "array"},
                    "counter_argument": {"type": "string"},
                    "unresolved_risks": {"type": "array"},
                },
                "required": ["concede", "advocate_vendor", "best_match", "counter_argument"],
            },
            "context": {
                "task_title": state.requirements.get("task_title", ""),
                "task_summary": state.requirements.get("procurement_subject", ""),
            },
        }
