from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_agent.modules.evaluation.governance_metrics import audit_completeness, authorization_receipt_present, evidence_completeness, scope_violations, unsafe_action_count, unsafe_approvals
from decision_agent.modules.evaluation.ground_truth_metrics import evaluate_ground_truth
from decision_agent.modules.evaluation.metric_loaders import _load_run_record
from decision_agent.modules.evaluation.quality_metrics import evidence_types_unrecognized, output_quality, recommendation_traceable, run_completed
from decision_agent.modules.evaluation.runtime_metrics import cost_tokens_total, estimated_cost_usd, model_name, model_provider, time_to_complete, tokens_input, tokens_output, worker_latency_p50_ms

def extract_all_metrics(
    run_dir: Path,
    condition: str,
    rep: int,
    fixture_id: str,
    ground_truth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = _load_run_record(run_dir)
    provider_name = model_provider(run_dir)
    model = model_name(run_dir)

    metrics: dict[str, Any] = {
        "condition": condition,
        "fixture": fixture_id,
        "rep": rep,
        "run_id": record.get("run_id"),
        "provider": provider_name,
        "model": model,
        "model_settings": _get_model_settings(provider_name, model),
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
        "tokens_input": tokens_input(run_dir),
        "tokens_output": tokens_output(run_dir),
        "estimated_cost_usd": estimated_cost_usd(run_dir),
        "worker_latency_p50_ms": worker_latency_p50_ms(run_dir),
    }
    if ground_truth:
        metrics.update(evaluate_ground_truth(run_dir, ground_truth))
    return metrics


def _get_model_settings(provider: str, model: str) -> dict[str, Any]:
    """Return model configuration settings for the given provider and model from environment/config."""
    import os

    provider_lower = provider.lower() if provider else ""
    settings: dict[str, Any] = {
        "provider": provider,
        "model": model,
    }

    if "anthropic" in provider_lower:
        settings.update({
            "temperature": 1.0,
            "top_p": None,
            "top_k": None,
            "prompt_caching": os.environ.get("ANTHROPIC_PROMPT_CACHE", "false").lower() == "true",
            "max_tokens": int(os.environ.get("ANTHROPIC_MAX_TOKENS", "32000")),
            "timeout_seconds": float(os.environ.get("ANTHROPIC_TIMEOUT_SECONDS", "600")),
            "sampling_note": "temperature=1.0 (API default, preserves natural variance)"
        })
    elif "openai" in provider_lower:
        settings.update({
            "temperature": 1.0,
            "top_p": 1.0,
            "max_tokens": int(os.environ.get("OPENAI_MAX_TOKENS", "32000")),
            "sampling_note": "temperature=1.0, top_p=1.0 (full distribution, no nucleus truncation)"
        })
    elif "ollama" in provider_lower:
        settings.update({
            "temperature": float(os.environ.get("OLLAMA_TEMPERATURE", "1.0")),
            "endpoint": os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434"),
            "sampling_note": "Local inference via Ollama"
        })

    return settings
