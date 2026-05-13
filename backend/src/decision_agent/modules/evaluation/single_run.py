from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from decision_agent.modules.evaluation.auto_approver import watch_run_to_completion
from decision_agent.modules.evaluation.conditions import CONDITION_MAP, load_fixture
from decision_agent.modules.evaluation.execution import _apply_evidence_overrides, _execute_workers_in_thread, _run_plain_model
from decision_agent.modules.evaluation.metrics import extract_all_metrics
from decision_agent.modules.runs.service import approve_architecture, build_architecture_proposal, create_run, generate_contracts_for_approved_architecture, start_run
from decision_agent.shared.providers.registry import get_provider

def run_one(
    fixture_id: str,
    condition: str,
    rep: int,
    root: Path,
    timeout_seconds: float = 600.0,
    evidence_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    layer_config, provider_override = CONDITION_MAP[condition]
    fixture = load_fixture(fixture_id)
    fixture = {**fixture, "task_id": f"{fixture['task_id']}_{condition}_rep{rep}"}

    run = create_run(
        fixture,
        root,
        layer_config=layer_config,
        provider_override=provider_override,
        benchmark_mode=True,
    )
    run_id = run["run_id"]
    audit_path = root / "data" / "runs" / run_id / "audit.jsonl"

    if condition == "A0":
        _run_plain_model(run_id, fixture, root, provider_override)
        run_dir = root / "data" / "runs" / run_id
        return extract_all_metrics(run_dir, condition, rep, fixture_id)

    provider = get_provider(provider_override)

    build_architecture_proposal(run_id, root, provider)
    approve_architecture(run_id, "benchmark_auto", root)
    generate_contracts_for_approved_architecture(run_id, root)
    if evidence_overrides:
        _apply_evidence_overrides(run_id, root, evidence_overrides)
    start_run(run_id, root)
    worker_thread = threading.Thread(
        target=_execute_workers_in_thread,
        args=(run_id, root, provider_override, audit_path),
        daemon=True,
    )
    worker_thread.start()
    watch_run_to_completion(run_id, root, timeout_seconds=timeout_seconds)
    worker_thread.join(timeout=10.0)

    run_dir = root / "data" / "runs" / run_id
    return extract_all_metrics(run_dir, condition, rep, fixture_id)
