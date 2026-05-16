from __future__ import annotations

from typing import Any

from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult


class UpdateStateOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("update_state", is_deterministic=True)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        patch = config.get("patch", {})
        return OperatorResult(
            success=True,
            state_patch=patch,
            audit_entries=[{"event": "state_patched", "keys": list(patch.keys())}],
        )
