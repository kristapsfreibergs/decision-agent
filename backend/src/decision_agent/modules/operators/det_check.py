from __future__ import annotations

from typing import Any

from decision_agent.modules.governance.dar import (
    build_proposal_from_output,
    evaluate_action,
    persist_receipt,
)
from decision_agent.modules.governance.dsc import (
    ScopeContract,
    check_output_against_scope,
)
from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult


class CheckOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("check", is_deterministic=True)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        output = config.get("output", {})
        contract = config.get("contract", {})
        issues: list[str] = []
        data: dict[str, Any] = {}

        if context.layer_config.dsc_enabled:
            scope_dict = contract.get("scope_contract")
            if scope_dict:
                try:
                    scope = ScopeContract.from_dict(scope_dict)
                    enforce_required = "evidence_sources_declared" in (
                        contract.get("validators") or []
                    )
                    dsc_issues = check_output_against_scope(
                        output, scope, enforce_required_evidence=enforce_required
                    )
                    issues.extend(dsc_issues)
                except (KeyError, TypeError):
                    issues.append("check: scope_contract is malformed")

        if context.layer_config.dar_enabled and contract.get("dar_action_type"):
            proposal = build_proposal_from_output(output, contract)
            if proposal is not None:
                receipt = evaluate_action(proposal, contract, context.project_root)
                persist_receipt(receipt, context.run_id, context.project_root / "data" / "runs")
                data["authorization_receipt"] = receipt.to_dict()
                state_patch = {
                    "authorization_receipts": [receipt.to_dict()],
                }

        if issues:
            return OperatorResult(
                success=False,
                error="; ".join(issues),
                data={"check_issues": issues, **data},
            )

        return OperatorResult(
            success=True,
            data=data,
            state_patch=data.get("authorization_receipt") and {
                "authorization_receipts": [data["authorization_receipt"]],
            } or {},
        )
