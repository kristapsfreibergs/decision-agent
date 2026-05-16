from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from decision_agent.modules.contracts.output_validator import validate_contractual_output
from decision_agent.modules.governance.dar import build_proposal_from_output, evaluate_action, persist_receipt
from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.modules.governance.paap import evaluate_paap
from decision_agent.modules.runs.state import (
    ACTION_PROPOSED,
    AUTHORIZATION_RECEIPT_RECORDED,
    EVIDENCE_SCORED,
    VALIDATION_FAILED,
    VALIDATION_PASSED,
    WORKER_COST,
    WORKER_RETRY_STARTED,
    WORKER_STARTED,
    WORKER_SUBMITTED,
)
from decision_agent.modules.workers.checkpoints import _checkpoint_path, _clear_checkpoint, _load_checkpoint, _save_checkpoint
from decision_agent.modules.workers.json_output import _extract_json, _validate_output, _write_worker_output
from decision_agent.modules.workers.loop import _run_model_loop
from decision_agent.shared.audit_log import append_audit_event
from decision_agent.shared.providers.base import LLMProvider

def run_worker(
    run_id: str,
    worker_id: str,
    contract: dict[str, Any],
    audit_path: Path,
    project_root: Path,
    provider: LLMProvider,
    *,
    is_retry: bool = False,
    retry_attempt: int = 0,
) -> dict[str, Any]:
    def emit(event: str, **extra: Any) -> None:
        append_audit_event(audit_path, {"event": event, "run_id": run_id, "worker_id": worker_id, **extra})

    if is_retry:
        emit(WORKER_RETRY_STARTED, attempt=retry_attempt, from_checkpoint=True)
    emit(WORKER_STARTED, provider=provider.name)

    raw_response, total_input_tokens, total_output_tokens, worker_wall_start = _run_model_loop(
        run_id,
        worker_id,
        contract,
        project_root,
        provider,
        is_retry,
        emit,
    )

    try:
        output = _extract_json(raw_response)
    except (json.JSONDecodeError, ValueError) as exc:
        emit(VALIDATION_FAILED, reason=f"JSON parse error: {exc}", raw=raw_response[:200])
        raise ValueError(f"Worker {worker_id} returned invalid JSON: {exc}") from exc

    schema = contract.get("output_schema", {})
    issues = _validate_output(output, schema)
    if issues:
        emit(VALIDATION_FAILED, reason="; ".join(issues))
        raise ValueError(f"Worker {worker_id} output failed schema validation: {'; '.join(issues)}")

    cfg = LayerConfig.from_dict(contract.get("layer_config"))
    if cfg.contract_validators_enabled:
        contract_issues = validate_contractual_output(output, contract, project_root=project_root)
        if cfg.paap_enabled and "evidence_sources_declared" in (contract.get("validators") or []):
            _, record = evaluate_paap(output, contract, project_root=None)
            if record.sources:
                emit(
                    EVIDENCE_SCORED,
                    source_count=len(record.sources),
                    record_score=round(record.score, 4),
                    threshold=record.profile_thresholds.get("min_avg_score"),
                    passed=record.score >= record.profile_thresholds.get("min_avg_score", 0.0),
                )
        if contract_issues:
            emit(VALIDATION_FAILED, reason="; ".join(contract_issues))
            raise ValueError(f"Worker {worker_id} failed contractual validation: {'; '.join(contract_issues)}")
    else:
        contract_issues = []

    output_file = _write_worker_output(project_root, run_id, worker_id, output)
    _clear_checkpoint(project_root, run_id, worker_id)
    emit(VALIDATION_PASSED)
    emit(
        WORKER_SUBMITTED,
        summary=output.get("summary", ""),
        files_changed=output.get("files_changed", []),
        output_file=output_file,
    )
    emit(
        WORKER_COST,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_tokens=total_input_tokens + total_output_tokens,
        wall_time_ms=int((time.monotonic() - worker_wall_start) * 1000),
        provider=provider.name,
    )

    if cfg.dar_enabled and contract.get("dar_action_type"):
        proposal = build_proposal_from_output(output, contract)
        if proposal is not None:
            emit(
                ACTION_PROPOSED,
                action_type=proposal.action_type,
                target=proposal.target,
                evidence_count=len(proposal.claimed_evidence_ids),
            )
            receipt = evaluate_action(proposal, contract, project_root)
            persist_receipt(receipt, run_id, project_root / "data" / "runs")
            emit(
                AUTHORIZATION_RECEIPT_RECORDED,
                receipt_id=receipt.receipt_id,
                consequence_class=receipt.consequence_class,
                decision=receipt.decision,
                rule_fired=receipt.rule_fired,
                evidence_floor_met=receipt.evidence_floor_met,
                evidence_score=receipt.evidence_score,
            )

    return output
