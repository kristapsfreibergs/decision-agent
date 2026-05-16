from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from decision_agent.modules.evaluation.auto_approver import watch_run_to_completion
from decision_agent.modules.evaluation.conditions import CONDITION_MAP, load_fixture
from decision_agent.modules.evaluation.execution import _apply_evidence_overrides, _execute_workers_in_thread, _run_baseline_model
from decision_agent.modules.evaluation.metrics import extract_all_metrics
from decision_agent.modules.runs.service import approve_architecture, build_architecture_proposal, create_run, generate_contracts_for_approved_architecture, start_run
from decision_agent.shared.providers.base import EXTENDED_MAX_TOKENS
from decision_agent.shared.providers.registry import get_provider

_RESULTS_LOCK = threading.Lock()


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
        _run_baseline_model(run_id, fixture, root, provider_override, fixture_id=fixture_id)
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
    stage: str | None = None,
    timestamped: bool = True,
) -> dict[str, Any]:
    """Run a case study evaluation using the graph executor.

    By default artifacts land inside one timestamped stage folder:
    case_studies/{case_id}/output/runs/{YYYYMMDD_HHMMSS}/{condition}_rep{n}/.
    Set timestamped=False to use the legacy deterministic {condition}_rep{n}/ path.
    Uses case.json as task, input/ for worker context, memory_seed/ for
    cross-run memory, and ground_truth.json for decision accuracy metrics.
    """
    from decision_agent.modules.evaluation.case_study import (
        ensure_run_dir,
        ensure_staged_run_dir,
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

    if timestamped:
        rd, run_stage = ensure_staged_run_dir(case_id, condition, rep, stage=stage)
    else:
        rd = ensure_run_dir(case_id, condition, rep, force=force)
        run_stage = stage or f"{condition}_rep{rep}"
    rid = make_run_id(case_id, condition, rep)
    started_at = datetime.now().astimezone().isoformat()

    _write_case_run_record(
        rd,
        run_id=rid,
        case_id=case_id,
        condition=condition,
        rep=rep,
        provider_override=provider_override,
        input_digest=input_hash(case),
        layer_config=layer_config.to_dict(),
        run_stage=run_stage,
        started_at=started_at,
    )

    audit_path = rd / "audit.jsonl"
    append_audit_event(audit_path, {"event": "run_created", "run_id": rid, "condition": condition})

    if condition == "A0":
        _run_baseline_model_in_dir(
            rid,
            case,
            rd,
            provider_override,
            audit_path,
            case_id,
            condition,
        )
        metrics = extract_all_metrics(rd, condition, rep, case_id, ground_truth=ground_truth)
        _persist_case_metrics(case_id, rd, condition, rep, run_stage, metrics)
        return metrics

    _populate_knowledge(rd, kd, knowledge_idx)
    _seed_memory(rd, msd)

    try:
        result = _run_case_graph(rid, case, rd, audit_path, provider_override, layer_config)
        append_audit_event(audit_path, {
            "event": "run_completed" if result.success else "run_failed",
            "run_id": rid,
            "final_phase": result.final_state.phase.value,
        })
        metrics = extract_all_metrics(rd, condition, rep, case_id, ground_truth=ground_truth)
    except Exception as exc:
        append_audit_event(audit_path, {
            "event": "run_failed",
            "run_id": rid,
            "error": str(exc)[:500],
        })
        metrics = extract_all_metrics(rd, condition, rep, case_id, ground_truth=ground_truth)
        metrics["error"] = str(exc)[:500]
    _persist_case_metrics(case_id, rd, condition, rep, run_stage, metrics)
    return metrics


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
    run_stage: str,
    started_at: str,
) -> None:
    import os
    from decision_agent.shared.providers.registry import get_provider

    # Capture actual provider and model name
    provider_obj = get_provider(provider_override)
    provider_name = provider_override or os.environ.get("MODEL_PROVIDER", "anthropic")

    # Get model name from provider
    actual_model_name = getattr(provider_obj, '_model', None)
    if not actual_model_name:
        # Fallback to env vars by provider type
        if "openai" in provider_name.lower():
            actual_model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        elif "anthropic" in provider_name.lower():
            actual_model_name = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        elif "ollama" in provider_name.lower():
            actual_model_name = os.environ.get("OLLAMA_MODEL", "")

    run_record = {
        "run_id": run_id,
        "case_id": case_id,
        "condition": condition,
        "rep": rep,
        "run_stage": run_stage,
        "started_at": started_at,
        "provider": provider_name,
        "model_name": actual_model_name,
        "input_hash": input_digest,
        "layer_config": layer_config,
    }
    (run_dir / "run-record.json").write_text(
        json.dumps(run_record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _persist_case_metrics(
    case_id: str,
    run_dir: Path,
    condition: str,
    rep: int,
    run_stage: str,
    metrics: dict[str, Any],
) -> None:
    from decision_agent.modules.evaluation.case_study import results_dir

    enriched = {
        **metrics,
        "run_stage": run_stage,
        "run_dir": str(run_dir),
    }
    out_dir = results_dir(case_id)
    line = json.dumps(enriched, ensure_ascii=False, default=str) + "\n"

    with _RESULTS_LOCK:
        # Write full indented JSON to the run directory for debugging.
        (run_dir / "metrics.json").write_text(
            json.dumps(enriched, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )

        out_dir.mkdir(parents=True, exist_ok=True)

        # Keep a per-stage append log so each experiment batch has a durable
        # record that is not mixed with earlier or later batches.
        stage_dir = out_dir / run_stage
        stage_dir.mkdir(parents=True, exist_ok=True)
        with (stage_dir / f"{condition}.jsonl").open("a", encoding="utf-8") as f:
            f.write(line)

        # Keep output/results/{condition}.jsonl as the latest-stage snapshot.
        # This avoids stale rows from previous batches and replaces duplicate
        # reps if the same process retries a run.
        _upsert_latest_stage_result(out_dir / f"{condition}.jsonl", enriched, run_stage)


def _upsert_latest_stage_result(jsonl_path: Path, row: dict[str, Any], run_stage: str) -> None:
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if existing.get("run_stage") != run_stage:
                continue
            key = _result_key(existing)
            rows[key] = existing

    key = _result_key(row)
    rows[key] = row
    ordered = sorted(rows.values(), key=_result_sort_key)
    payload = "".join(
        json.dumps(item, ensure_ascii=False, default=str) + "\n"
        for item in ordered
    )
    tmp_path = jsonl_path.with_suffix(jsonl_path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(jsonl_path)


def _result_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row.get("condition", "")), _result_rep(row)


def _result_sort_key(row: dict[str, Any]) -> tuple[str, int]:
    return str(row.get("condition", "")), _result_rep(row)


def _result_rep(row: dict[str, Any]) -> int:
    try:
        return int(row.get("rep", -1))
    except (TypeError, ValueError):
        return -1


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


def _run_baseline_model_in_dir(
    run_id: str,
    case: dict[str, Any],
    run_dir: Path,
    provider_override: str | None,
    audit_path: Path,
    case_id: str,
    condition: str,
) -> None:
    from decision_agent.modules.evaluation.baseline_prompts import (
        build_informed_context,
        detect_domain_from_fixture,
        get_a0_system_prompt,
    )
    from decision_agent.shared.audit_log import append_audit_event

    provider = get_provider(provider_override)
    domain = detect_domain_from_fixture(case_id)
    system = get_a0_system_prompt(domain)
    user = f"Task: {case.get('title', '')}\n\n{case.get('description', '')}"
    user = f"{user}\n\n{build_informed_context(domain, run_dir)}"

    append_audit_event(audit_path, {"event": "run_started", "run_id": run_id, "condition": condition})
    try:
        if hasattr(provider, "complete_with_usage"):
            raw, usage = provider.complete_with_usage(system, user, max_tokens=EXTENDED_MAX_TOKENS)
        else:
            raw, usage = provider.complete(system, user, max_tokens=EXTENDED_MAX_TOKENS), {}
        append_audit_event(audit_path, {"event": "llm_call_usage", "run_id": run_id,
                                        "input_tokens": usage.get("input_tokens", 0),
                                        "output_tokens": usage.get("output_tokens", 0)})
        stripped = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```\s*$", "", stripped.strip())
        # If model prefixed with text, extract the first {...} block
        if not stripped.startswith("{"):
            match = re.search(r"\{", stripped)
            if match:
                stripped = stripped[match.start():]
        output = json.loads(stripped)
    except Exception as exc:
        append_audit_event(audit_path, {"event": "llm_call_failed", "run_id": run_id, "error": str(exc)[:300]})
        return

    out_dir = run_dir / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "recommender.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    append_audit_event(audit_path, {"event": "run_completed", "run_id": run_id, "condition": condition})


_EVALUATION_ONLY_FIELDS = frozenset({
    "primary_failure",
    "price_score",
    "delivery_score",
    "quality_score",
    "compliance_score",
})


def _sanitize_knowledge_file(filename: str, content: str) -> str:
    """Strip pre-computed evaluation fields from JSON vendor files.

    These fields (scores, failure labels) are answer-key data that would let
    the model skip reasoning. Raw factual fields are kept intact.
    Only JSON files containing a 'vendors' list are modified.
    """
    if not filename.endswith(".json"):
        return content
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return content
    if not isinstance(data, dict) or not isinstance(data.get("vendors"), list):
        return content
    sanitized_vendors = [
        {k: v for k, v in vendor.items() if k not in _EVALUATION_ONLY_FIELDS}
        for vendor in data["vendors"]
    ]
    return json.dumps({**data, "vendors": sanitized_vendors}, indent=2, ensure_ascii=False) + "\n"


def _populate_knowledge(run_dir: Path, kd: Path, knowledge_idx: dict[str, list[str]]) -> None:
    """Copy input files into archive/knowledge/procurement/ and write a manifest log.

    Pre-computed evaluation fields (scores, failure labels) are stripped from JSON
    vendor data before copying so the model researches from raw facts only.
    """
    if not kd.exists():
        return
    archive_root = run_dir / "archive" / "knowledge" / "procurement"
    manifest = []
    seen: set[str] = set()
    for worker_id, file_paths in knowledge_idx.items():
        for rel_path in file_paths:
            src = kd / rel_path
            entry = {"worker": worker_id, "path": rel_path, "status": "ok"}
            if not src.exists():
                entry["status"] = "missing"
                manifest.append(entry)
                continue
            parts = Path(rel_path).parts
            target_dir = archive_root / parts[0] if len(parts) >= 2 else archive_root
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / src.name
            if rel_path not in seen:
                content = src.read_text(encoding="utf-8")
                content = _sanitize_knowledge_file(src.name, content)
                target.write_text(content, encoding="utf-8")
                seen.add(rel_path)
            manifest.append(entry)
    (run_dir / "input_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


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
