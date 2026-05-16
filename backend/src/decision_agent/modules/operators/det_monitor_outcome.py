from __future__ import annotations

from typing import Any

from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult
from decision_agent.shared.audit_log import append_audit_event


class MonitorOutcomeOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("monitor_outcome", is_deterministic=True)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        from decision_agent.modules.state.decision_state import DecisionState

        if not isinstance(state, DecisionState):
            return OperatorResult(success=False, error="State is not a DecisionState")

        outcome: dict[str, Any] = {
            "final_phase": state.phase.value,
            "agents_completed": len(state.agent_history),
            "evidence_sources_count": len(state.evidence_sources),
            "scope_violations_count": len(state.scope_violations),
            "authorization_receipts_count": len(state.authorization_receipts),
            "persisted_evidence_count": len(state.persisted_evidence_ids),
        }

        append_audit_event(
            context.audit_path,
            {
                "event": "decision_outcome_recorded",
                "run_id": context.run_id,
                **outcome,
            },
        )

        return OperatorResult(success=True, data={"outcome": outcome})
