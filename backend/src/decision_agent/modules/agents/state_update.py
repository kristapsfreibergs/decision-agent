from __future__ import annotations

from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.operators.det_log import LogOperator
from decision_agent.modules.operators.det_update_state import UpdateStateOperator
from decision_agent.modules.operators.mem_write import MemoryWriteOperator
from decision_agent.modules.state.decision_state import DecisionPhase, DecisionState


class StateUpdateAgent(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id="state_update",
            operators=[
                UpdateStateOperator(),
                MemoryWriteOperator(),
                LogOperator(),
            ],
            target_phase=DecisionPhase.STATE_UPDATED,
        )

    def _operator_config(self, op_name: str, state: DecisionState) -> dict[str, Any]:
        if op_name == "update_state":
            return {"patch": {}}
        if op_name == "mem_write":
            return {"evidence_items": self._build_evidence_items(state)}
        if op_name == "log":
            return {"event": "agent_completed", "extra": {"agent_id": self.agent_id}}
        return {}

    def _build_evidence_items(self, state: DecisionState) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for ranking in state.rankings[:3]:
            if isinstance(ranking, dict):
                items.append({
                    "evidence_class": "evaluation_score",
                    "content": f"Rank {ranking.get('rank', '?')}: {ranking.get('name', ranking.get('vendor', '?'))} — score {ranking.get('total_score', '?')}",
                    "authority_score": 0.3,
                })
        return items
