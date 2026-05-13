from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_agent.modules.evaluation.governance_metrics import audit_completeness, authorization_receipt_present, evidence_completeness, scope_violations, unsafe_action_count, unsafe_approvals
from decision_agent.modules.evaluation.metric_loaders import _load_run_record
from decision_agent.modules.evaluation.quality_metrics import evidence_types_unrecognized, output_quality, recommendation_traceable, run_completed
from decision_agent.modules.evaluation.runtime_metrics import cost_tokens_total, model_provider, time_to_complete, worker_latency_p50_ms

def extract_all_metrics(
    run_dir: Path,
    condition: str,
    rep: int,
    fixture_id: str,
) -> dict[str, Any]:
    record = _load_run_record(run_dir)
    return {
        "condition": condition,
        "fixture": fixture_id,
        "rep": rep,
        "run_id": record.get("run_id"),
        "provider": model_provider(run_dir),
        "scope_violations": scope_violations(run_dir),
        "evidence_types_unrecognized": evidence_types_unrecognized(run_dir),
        "recommendation_traceable": recommendation_traceable(run_dir),
        "evidence_completeness": evidence_completeness(run_dir),
        "authorization_receipt_present": authorization_receipt_present(run_dir),
        "unsafe_action_count": unsafe_action_count(run_dir),
        "unsafe_approvals": unsafe_approvals(run_dir),
        "audit_completeness": audit_completeness(run_dir),
        "output_quality": output_quality(run_dir),
        "time_to_complete_s": time_to_complete(run_dir),
        "run_completed": run_completed(run_dir),
        "cost_tokens_total": cost_tokens_total(run_dir),
        "worker_latency_p50_ms": worker_latency_p50_ms(run_dir),
    }
