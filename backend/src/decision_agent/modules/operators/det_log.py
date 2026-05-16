from __future__ import annotations

from typing import Any

from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult
from decision_agent.shared.audit_log import append_audit_event


class LogOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("log", is_deterministic=True)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        event = config.get("event", "operator_completed")
        extra = config.get("extra", {})
        append_audit_event(
            context.audit_path,
            {
                "event": event,
                "run_id": context.run_id,
                "agent_id": context.agent_id,
                **extra,
            },
        )
        return OperatorResult(
            success=True,
            audit_entries=[{"event": event, **extra}],
        )
