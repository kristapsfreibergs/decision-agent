from __future__ import annotations

import json
import time
from typing import Any

from decision_agent.modules.operators.base import OperatorBase, OperatorContext, OperatorResult
from decision_agent.modules.workers.json_output import _extract_json
from decision_agent.modules.workers.loop import _run_model_loop


class ExtractOperator(OperatorBase):
    def __init__(self) -> None:
        super().__init__("extract", is_deterministic=False)

    def execute(self, state: Any, config: dict[str, Any], context: OperatorContext) -> OperatorResult:
        contract = config.get("contract", {})
        if context.provider is None:
            return OperatorResult(success=False, error="No LLM provider available")

        def emit(event: str, **extra: Any) -> None:
            from decision_agent.shared.audit_log import append_audit_event
            append_audit_event(context.audit_path, {
                "event": event, "run_id": context.run_id, "agent_id": context.agent_id, **extra,
            })

        # Inject registry and run_id so ask_agent tool can resolve peers
        contract = {
            **contract,
            "run_id": context.run_id,
            "_agent_registry": context.policies.get("_agent_registry") or {},
        }
        try:
            raw, inp_tok, out_tok, wall_start = _run_model_loop(
                context.run_id, context.agent_id, contract,
                context.project_root, context.provider, False, emit,
            )
            output = _extract_json(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            return OperatorResult(success=False, error=f"Extract failed: {exc}")

        return OperatorResult(
            success=True,
            data={
                "output": output,
                "input_tokens": inp_tok,
                "output_tokens": out_tok,
                "wall_time_ms": int((time.monotonic() - wall_start) * 1000),
            },
            state_patch=config.get("state_patch_key") and {config["state_patch_key"]: output} or {},
        )
