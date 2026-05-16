from __future__ import annotations

from typing import Any

from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult


class FilterOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("filter", is_deterministic=True)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        candidates = config.get("candidates", [])
        hard_constraints = config.get("hard_constraints", [])

        eligible: list[dict[str, Any]] = []
        eliminated: list[dict[str, Any]] = []

        for candidate in candidates:
            failed = []
            for constraint in hard_constraints:
                field = constraint.get("field")
                op = constraint.get("op", "eq")
                expected = constraint.get("value")
                actual = candidate.get(field)

                if op == "eq" and actual != expected:
                    failed.append(f"{field}: expected {expected}, got {actual}")
                elif op == "gte" and (actual is None or actual < expected):
                    failed.append(f"{field}: expected >= {expected}, got {actual}")
                elif op == "in" and actual not in expected:
                    failed.append(f"{field}: expected in {expected}, got {actual}")
                elif op == "contains" and expected not in (actual or ""):
                    failed.append(f"{field}: expected to contain {expected}")
                elif op == "truthy" and not actual:
                    failed.append(f"{field}: expected truthy value")

            if failed:
                eliminated.append({**candidate, "_elimination_reasons": failed})
            else:
                eligible.append(candidate)

        return OperatorResult(
            success=True,
            data={"eligible": eligible, "eliminated": eliminated},
            state_patch={"eligible_options": eligible},
        )
