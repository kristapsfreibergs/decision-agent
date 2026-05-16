from __future__ import annotations

from typing import Any

from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult
from decision_agent.modules.state.decision_state import DecisionState


class ValidateStateOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("validate_state", is_deterministic=True)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        if not isinstance(state, DecisionState):
            return OperatorResult(success=False, error="State is not a DecisionState")

        issues: list[str] = []
        required_fields = config.get("required_fields", [])
        for field_name in required_fields:
            value = getattr(state, field_name, None)
            if not value:
                issues.append(f"Required field '{field_name}' is empty")

        if issues:
            return OperatorResult(
                success=False,
                error="; ".join(issues),
                data={"validation_issues": issues},
            )
        return OperatorResult(
            success=True,
            data={"validated": True, "phase": state.phase.value},
        )
