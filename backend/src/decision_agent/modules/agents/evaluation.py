from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase, AgentResult
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_rank import RankOperator
from decision_agent.modules.operators.det_score import ScoreOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.operators.llm_extract import ExtractOperator
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState

# Default weighted rubric — criteria weights must sum to 1.0.
# Each criterion maps to a field the LLM extracts as a 0-4 integer.
DEFAULT_RUBRIC: dict[str, float] = {
    "price": 0.30,
    "delivery": 0.20,
    "quality": 0.25,
    "compliance": 0.25,
}


def apply_rubric(
    vendor_facts: list[dict[str, Any]],
    rubric: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Pure deterministic scoring. LLM extracts facts, this applies arithmetic."""
    weights = rubric or DEFAULT_RUBRIC
    scored: list[dict[str, Any]] = []
    for vendor in vendor_facts:
        total = 0.0
        criteria_scores: dict[str, float] = {}
        for criterion, weight in weights.items():
            raw = vendor.get(criterion, 0)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = 0.0
            weighted = value * weight
            criteria_scores[criterion] = round(weighted, 4)
            total += weighted
        scored.append({
            **vendor,
            "criteria_scores": criteria_scores,
            "total_score": round(total, 4),
        })
    return scored


class EvaluationAgent(AgentBase):
    """LLM extracts structured facts per vendor. Code scores and ranks."""

    def __init__(self, rubric: dict[str, float] | None = None) -> None:
        super().__init__(
            agent_id="evaluation",
            operators=[
                ExtractOperator(),     # LLM: extract facts per vendor
                ScoreOperator(),       # deterministic: PAAP evidence scoring
                RankOperator(),        # deterministic: sort by total_score
                UpdateStateOperator(),
                LogOperator(),
            ],
            target_phase=DecisionPhase.EVALUATED,
        )
        self.rubric = rubric or DEFAULT_RUBRIC

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "extract":
            return {
                "contract": self._make_extract_contract(state),
                "state_patch_key": "scores",
            }
        if op_name == "score":
            return {"output": self._gather_output(state), "contract": self._score_contract(state)}
        if op_name == "rank":
            return {"scores": state.scores, "sort_key": "total_score", "descending": True}
        if op_name == "update_state":
            return {"patch": {"scores": state.scores, "rankings": state.rankings}}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def run(self, state, context):
        """Override to inject deterministic rubric scoring between extract and score."""
        from decision_agent.modules.operators.base import OperatorResult

        result = super().run(state, context)
        if not result.success:
            return result

        # Apply deterministic rubric to LLM-extracted facts
        raw_scores = result.state_after.scores
        if isinstance(raw_scores, list):
            scored = apply_rubric(raw_scores, self.rubric)
            state_after = result.state_after.apply_patch({"scores": scored})
            # Re-rank after deterministic scoring
            ranked = sorted(scored, key=lambda x: x.get("total_score", 0), reverse=True)
            for i, item in enumerate(ranked, 1):
                item["rank"] = i
            state_after = state_after.apply_patch({"rankings": ranked})
            return AgentResult(
                success=True,
                agent_id=self.agent_id,
                state_before=result.state_before,
                state_after=state_after,
                operator_results=result.operator_results,
            )
        return result

    def _make_extract_contract(self, state: DecisionState) -> dict[str, Any]:
        criteria = ", ".join(self.rubric.keys())
        return {
            "worker_id": f"{self.agent_id}_extract",
            "goal": (
                f"For each eligible vendor, extract factual scores (0-4 integer) for: {criteria}. "
                "0 = no evidence, 1 = poor, 2 = acceptable, 3 = good, 4 = excellent. "
                "Do NOT invent scores. If no evidence exists for a criterion, score it 0. "
                "Return an array of objects, each with 'vendor' (string) and one integer field per criterion. "
                "Also include 'evidence_sources' citing where each fact came from."
            ),
            "read_paths": [
                f"data/runs/{state.run_id}/workspace/requirements.md",
                f"data/runs/{state.run_id}/workspace/market_research.md",
                f"data/runs/{state.run_id}/workspace/risk_assessment.md",
                "archive/knowledge/procurement/evaluation-criteria/**",
            ],
            "write_paths": [f"data/runs/{state.run_id}/workspace/evaluation.md"],
            "allowed_tools": ["read_file", "write_file", "list_files", "memory_search"],
            "validators": ["write_scope", "evidence_sources_declared"],
            "max_steps": 6,
            "output_schema": {"type": "object"},
            "context": {
                "task_title": state.requirements.get("task_title", ""),
                "task_summary": state.requirements.get("procurement_subject", ""),
            },
        }

    def _score_contract(self, state: DecisionState) -> dict[str, Any]:
        return {
            "worker_id": f"{self.agent_id}_score",
            "validators": ["evidence_sources_declared"],
            "evidence_profile": state.evidence.get("evidence_profile", {}),
        }

    def _gather_output(self, state: DecisionState) -> dict[str, Any]:
        output: dict[str, Any] = {}
        if state.scores:
            if isinstance(state.scores, list) and state.scores:
                output = state.scores[0] if isinstance(state.scores[0], dict) else {}
            elif isinstance(state.scores, dict):
                output = state.scores
        output.setdefault("evidence_sources", state.evidence_sources)
        return output
