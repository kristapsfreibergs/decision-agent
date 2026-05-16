from __future__ import annotations

from typing import Any

from decision_agent.modules.contracts.output_validator import validate_contractual_output
from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult
from decision_agent.modules.workers.json_output import _validate_output


class VerifyOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("verify", is_deterministic=True)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        output = config.get("output", {})
        schema = config.get("schema", {})
        contract = config.get("contract")

        issues: list[str] = []

        schema_issues = _validate_output(output, schema)
        issues.extend(schema_issues)

        if contract and context.layer_config.contract_validators_enabled:
            contract_issues = validate_contractual_output(
                output, contract, project_root=context.project_root
            )
            issues.extend(contract_issues)

        if issues:
            return OperatorResult(
                success=False,
                error="; ".join(issues),
                data={"validation_issues": issues},
            )
        return OperatorResult(success=True, data={"verified": True})
