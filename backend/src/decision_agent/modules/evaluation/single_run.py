from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from decision_agent.modules.evaluation.auto_approver import watch_run_to_completion
from decision_agent.modules.evaluation.conditions import CONDITION_MAP, load_fixture
from decision_agent.modules.evaluation.execution import _apply_evidence_overrides, _execute_workers_in_thread, _run_informed_plain_model, _run_plain_model
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
    """Run a single evaluation using legacy fixture + worker pipeline.

    Kept for backward compatibility. New experiments should use run_case_study().
    """
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
        _run_plain_model(run_id, fixture, root, provider_override, fixture_id=fixture_id)
        run_dir = root / "data" / "runs" / run_id
        return extract_all_metrics(run_dir, condition, rep, fixture_id)

    if condition == "A0_inf":
        _run_informed_plain_model(run_id, fixture, root, provider_override, fixture_id=fixture_id)
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


def run_case_study(
    case_id: str,
    condition: str,
    rep: int,
    timeout_seconds: float = 600.0,
    force: bool = False,
) -> dict[str, Any]:
    """Run a case study evaluation using the graph executor.

    All artifacts land directly in case_studies/{case_id}/runs/{condition}_rep{n}/.
    Uses case.json as task, knowledge/ for worker context, memory_seed/ for
    cross-run memory, and ground_truth.json for decision accuracy metrics.
    """
    from decision_agent.modules.evaluation.case_study import (
        ensure_run_dir,
        input_hash,
        knowledge_dir,
        load_case,
        load_ground_truth,
        load_knowledge_index,
        make_run_id,
        memory_seed_dir,
    )
    from decision_agent.shared.audit_log import append_audit_event

    layer_config, provider_override = CONDITION_MAP[condition]
    case = load_case(case_id)
    ground_truth = load_ground_truth(case_id)
    knowledge_idx = load_knowledge_index(case_id)
    kd = knowledge_dir(case_id)
    msd = memory_seed_dir(case_id)

    # Ensure run directory (overwrite protection)
    rd = ensure_run_dir(case_id, condition, rep, force=force)

    # Build run_id and task
    rid = make_run_id(case_id, condition, rep)

    _write_case_run_record(
        rd,
        run_id=rid,
        case_id=case_id,
        condition=condition,
        rep=rep,
        provider_override=provider_override,
        input_digest=input_hash(case),
        layer_config=layer_config.to_dict(),
    )

    # Copy knowledge files so agents can read them
    _populate_knowledge(rd, kd, knowledge_idx)

    # Seed memory if present
    _seed_memory(rd, msd)

    # Audit log lives in the run dir
    audit_path = rd / "audit.jsonl"
    append_audit_event(audit_path, {"event": "run_created", "run_id": rid, "condition": condition})

    if condition in ("A0", "A0_inf"):
        _run_case_baseline(condition, rid, case, rd, provider_override, audit_path, case_id)
        return extract_all_metrics(rd, condition, rep, case_id, ground_truth=ground_truth)

    result = _run_case_graph(rid, case, rd, audit_path, provider_override, layer_config)
    append_audit_event(audit_path, {
        "event": "run_completed" if result.success else "run_failed",
        "run_id": rid,
        "final_phase": result.final_state.phase.value,
    })

    return extract_all_metrics(rd, condition, rep, case_id, ground_truth=ground_truth)


def _write_case_run_record(
    run_dir: Path,
    *,
    run_id: str,
    case_id: str,
    condition: str,
    rep: int,
    provider_override: str | None,
    input_digest: str,
    layer_config: dict[str, Any],
) -> None:
    run_record = {
        "run_id": run_id,
        "case_id": case_id,
        "condition": condition,
        "rep": rep,
        "model": provider_override,
        "input_hash": input_digest,
        "layer_config": layer_config,
    }
    (run_dir / "run-record.json").write_text(
        json.dumps(run_record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _run_case_baseline(
    condition: str,
    run_id: str,
    case: dict[str, Any],
    run_dir: Path,
    provider_override: str | None,
    audit_path: Path,
    case_id: str,
) -> None:
    if condition == "A0":
        _run_plain_model_in_dir(run_id, case, run_dir, provider_override, audit_path, case_id)
        return
    _run_informed_plain_model_in_dir(run_id, case, run_dir, provider_override, audit_path, case_id)


def _run_case_graph(
    run_id: str,
    case: dict[str, Any],
    run_dir: Path,
    audit_path: Path,
    provider_override: str | None,
    layer_config: Any,
):
    from decision_agent.modules.graph.domain_graphs.procurement import build_procurement_graph
    from decision_agent.modules.graph.executor import GraphExecutor
    from decision_agent.modules.operators.base import OperatorContext

    provider = get_provider(provider_override)
    graph = build_procurement_graph(
        run_id,
        task_context=case,
        policies={"run_dir": str(run_dir)},
    )

    context = OperatorContext(
        run_id=run_id,
        agent_id="graph_executor",
        project_root=run_dir,
        audit_path=audit_path,
        provider=provider,
        layer_config=layer_config,
        policies={"run_dir": str(run_dir)},
    )

    executor = GraphExecutor()
    return executor.execute(graph, context)


def _run_plain_model_in_dir(
    run_id: str,
    case: dict[str, Any],
    run_dir: Path,
    provider_override: str | None,
    audit_path: Path,
    case_id: str,
) -> None:
    """A0 baseline: single LLM call, output written directly to run_dir."""
    from decision_agent.modules.evaluation.baseline_prompts import (
        detect_domain_from_fixture,
        get_a0_system_prompt,
    )
    from decision_agent.shared.audit_log import append_audit_event

    provider = get_provider(provider_override)
    domain = detect_domain_from_fixture(case_id)
    system = get_a0_system_prompt(domain)
    user = f"Task: {case.get('title', '')}\n\n{case.get('description', '')}"

    append_audit_event(audit_path, {"event": "run_started", "run_id": run_id, "condition": "A0"})
    try:
        import re
        raw = provider.complete(system, user)
        stripped = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```\s*$", "", stripped.strip())
        output = json.loads(stripped)
    except Exception as exc:
        append_audit_event(audit_path, {"event": "llm_call_failed", "run_id": run_id, "error": str(exc)[:300]})
        return

    out_dir = run_dir / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "recommender.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    append_audit_event(audit_path, {"event": "run_completed", "run_id": run_id, "condition": "A0"})


def _run_informed_plain_model_in_dir(
    run_id: str,
    case: dict[str, Any],
    run_dir: Path,
    provider_override: str | None,
    audit_path: Path,
    case_id: str,
) -> None:
    """A0_inf baseline: single LLM call with full context, output to run_dir."""
    from decision_agent.modules.evaluation.baseline_prompts import (
        build_informed_context,
        detect_domain_from_fixture,
        get_a0_system_prompt,
    )
    from decision_agent.shared.audit_log import append_audit_event

    provider = get_provider(provider_override)
    domain = detect_domain_from_fixture(case_id)
    system = get_a0_system_prompt(domain)
    informed_context = build_informed_context(domain, run_dir)
    user = (
        f"Task: {case.get('title', '')}\n\n"
        f"{case.get('description', '')}\n\n"
        f"{informed_context}"
    )

    append_audit_event(audit_path, {"event": "run_started", "run_id": run_id, "condition": "A0_inf"})
    try:
        import re
        raw = provider.complete(system, user)
        stripped = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```\s*$", "", stripped.strip())
        output = json.loads(stripped)
    except Exception as exc:
        append_audit_event(audit_path, {"event": "llm_call_failed", "run_id": run_id, "error": str(exc)[:300]})
        return

    out_dir = run_dir / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "recommender.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    append_audit_event(audit_path, {"event": "run_completed", "run_id": run_id, "condition": "A0_inf"})


def _populate_knowledge(run_dir: Path, kd: Path, knowledge_idx: dict[str, list[str]]) -> None:
    """Copy knowledge files into archive/knowledge/procurement/ so agents can read them."""
    if not kd.exists():
        return
    archive_root = run_dir / "archive" / "knowledge" / "procurement"
    for worker_id, file_paths in knowledge_idx.items():
        for rel_path in file_paths:
            src = kd / rel_path
            if not src.exists():
                continue
            parts = Path(rel_path).parts
            if len(parts) >= 2:
                target_dir = archive_root / parts[0]
            else:
                target_dir = archive_root
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / src.name
            target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def _seed_memory(run_dir: Path, msd: Path) -> None:
    """Copy memory_seed/ JSONL files into data/memory/ so MemoryProvider can find them."""
    if not msd.exists():
        return
    for domain_dir in msd.iterdir():
        if not domain_dir.is_dir():
            continue
        target_dir = run_dir / "data" / "memory" / domain_dir.name
        target_dir.mkdir(parents=True, exist_ok=True)
        for jsonl_file in domain_dir.glob("*.jsonl"):
            target = target_dir / jsonl_file.name
            target.write_text(jsonl_file.read_text(encoding="utf-8"), encoding="utf-8")
