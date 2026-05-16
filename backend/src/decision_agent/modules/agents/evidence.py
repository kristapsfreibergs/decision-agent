from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_normalize import NormalizeOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.operators.det_verify import VerifyOperator
from decision_agent.modules.operators.llm_classify import ClassifyOperator
from decision_agent.modules.operators.llm_extract import ExtractOperator
from decision_agent.modules.operators.mem_search import MemorySearchOperator
from decision_agent.modules.state.decision_state import DecisionState


class EvidenceAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id="evidence",
            operators=[
                MemorySearchOperator(),
                ExtractOperator(),
                ClassifyOperator(),
                VerifyOperator(),
                NormalizeOperator(),
                UpdateStateOperator(),
                LogOperator(),
            ],
            target_phase=None,
        )

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "mem_search":
            return {"query": state.requirements.get("procurement_subject", "")}
        if op_name == "extract":
            return {
                "contract": self._make_contract(state),
                "state_patch_key": "evidence",
            }
        if op_name == "classify":
            return {
                "contract": self._make_classify_contract(state),
                "state_patch_key": "evidence",
            }
        if op_name == "verify":
            return {"output": state.evidence, "schema": {}}
        if op_name == "normalize":
            return {"data": state.evidence}
        if op_name == "update_state":
            return {"patch": {"evidence": state.evidence}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def _make_contract(self, state: DecisionState) -> dict[str, Any]:
        return {
            "worker_id": f"{self.agent_id}_extract",
            "goal": (
                "Research the supply market for this procurement. "
                "Find active vendors, typical market pricing and lead times, "
                "supply constraints, and recent procurement outcomes."
            ),
            "read_paths": ["archive/knowledge/procurement/markets/**"],
            "write_paths": [f"data/runs/{state.run_id}/workspace/market_research.md"],
            "allowed_tools": ["read_file", "write_file", "list_files"],
            "validators": ["write_scope"],
            "max_steps": 6,
            "output_schema": {"type": "object"},
            "context": {
                "task_title": state.requirements.get("task_title", ""),
                "task_summary": state.requirements.get("procurement_subject", ""),
            },
        }

    def _make_classify_contract(self, state: DecisionState) -> dict[str, Any]:
        return {
            "worker_id": f"{self.agent_id}_classify",
            "goal": (
                "Assess the risk profile of this procurement. "
                "Rate vendor concentration, delivery, compliance, budget, "
                "and reputational risks as LOW / MEDIUM / HIGH."
            ),
            "read_paths": ["archive/knowledge/procurement/risk-register/**"],
            "write_paths": [f"data/runs/{state.run_id}/workspace/risk_assessment.md"],
            "allowed_tools": ["read_file", "write_file", "list_files"],
            "validators": ["write_scope"],
            "max_steps": 6,
            "output_schema": {"type": "object"},
            "context": {
                "task_title": state.requirements.get("task_title", ""),
                "task_summary": state.requirements.get("procurement_subject", ""),
            },
        }
