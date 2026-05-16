from __future__ import annotations

from typing import Any

from decision_agent.modules.governance.paap import evaluate_paap
from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult


class ScoreOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("score", is_deterministic=True)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        output = config.get("output", {})
        contract = config.get("contract", {})

        if not context.layer_config.paap_enabled:
            return OperatorResult(success=True, data={"paap_skipped": True})

        paap_issues, record = evaluate_paap(
            output, contract, project_root=context.project_root
        )

        data: dict[str, Any] = {
            "evidence_score": round(record.score, 4),
            "source_count": len(record.sources),
        }

        if paap_issues:
            return OperatorResult(
                success=False,
                error="; ".join(paap_issues),
                data=data,
            )
        return OperatorResult(success=True, data=data)
