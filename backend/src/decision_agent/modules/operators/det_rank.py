from __future__ import annotations

from typing import Any

from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult


class RankOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("rank", is_deterministic=True)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        scores = config.get("scores", [])
        sort_key = config.get("sort_key", "total_score")
        descending = config.get("descending", True)

        ranked = sorted(
            scores,
            key=lambda x: x.get(sort_key, 0),
            reverse=descending,
        )

        for i, item in enumerate(ranked, 1):
            item["rank"] = i

        return OperatorResult(
            success=True,
            data={"ranked": ranked},
            state_patch={"rankings": ranked},
        )
