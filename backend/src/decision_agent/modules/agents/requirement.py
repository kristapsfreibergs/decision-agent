from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decision_agent.modules.agents.base import AgentBase, AgentResult
from decision_agent.modules.operators.base import OperatorContext, OperatorResult
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.operators.llm_extract import ExtractOperator
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState


class RequirementAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id="requirement",
            operators=[
                ExtractOperator(),
                UpdateStateOperator(),
                LogOperator(),
            ],
            target_phase=DecisionPhase.EVIDENCE_INCOMPLETE,
        )

    def run(self, state: DecisionState, context: OperatorContext) -> AgentResult:
        result = super().run(state, context)
        if not result.success:
            return result

        constraints_doc = self._load_hard_constraints(context.project_root)
        hard_constraints = constraints_doc.get("hard_constraints") or constraints_doc.get("constraints")
        if isinstance(hard_constraints, list) and hard_constraints:
            requirements = {
                **result.state_after.requirements,
                "hard_constraints": hard_constraints,
                "constraint_count": len(hard_constraints),
            }
            state_after = result.state_after.apply_patch({"requirements": requirements})
            return AgentResult(
                success=True,
                agent_id=result.agent_id,
                state_before=result.state_before,
                state_after=state_after,
                operator_results=result.operator_results,
            )
        return result

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "extract":
            return {
                "contract": self._make_contract(state),
                "state_patch_key": "requirements",
            }
        if op_name == "update_state":
            return {"patch": {"requirements": state.requirements}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def _make_contract(self, state: DecisionState) -> dict[str, Any]:
        workspace_file = f"data/runs/{state.run_id}/workspace/requirements.md"
        return {
            "worker_id": f"{self.agent_id}_extract",
            "goal": (
                "Read the requirements documents and hard_constraints.json. "
                "Treat hard_constraints.json as the authoritative source for constraints; "
                "do not derive constraints from prose if that JSON file is available.\n\n"
                f"Write a structured requirements analysis to {workspace_file}. "
                "Use compact bullets for subject, quantity, hard constraints, timeline, budget, "
                "compliance, and gaps.\n\n"
                "After writing the file, return ONLY this JSON:\n"
                '{"status": "ok", "written_to": "<path>", "procurement_subject": "<one sentence>", '
                '"budget_ceiling": "<amount or unknown>", "constraint_count": <int>, '
                '"hard_constraints": [{"field": "<field>", "op": "<eq|lte|gte>", "value": <value>}]}'
            ),
            "read_paths": [
                "archive/knowledge/procurement/2_requirements/**",
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
                    "procurement_subject": {"type": "string"},
                    "budget_ceiling": {"type": "string"},
                    "constraint_count": {"type": "integer"},
                    "hard_constraints": {"type": "array"},
                },
                "required": ["status", "written_to"],
            },
            "context": {
                "task_title": state.requirements.get("task_title", ""),
                "task_summary": state.requirements.get("task_summary", ""),
            },
        }

    def _load_hard_constraints(self, project_root: Path) -> dict[str, Any]:
        path = (
            project_root
            / "archive"
            / "knowledge"
            / "procurement"
            / "2_requirements"
            / "hard_constraints.json"
        )
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
