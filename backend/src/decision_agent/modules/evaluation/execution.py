from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from decision_agent.modules.runs.scheduler import get_ready_worker_ids, has_active_workers, has_blocked_workers, is_run_complete
from decision_agent.modules.runs.service import read_run
from decision_agent.modules.workers.runner import run_worker
from decision_agent.shared.audit_log import append_audit_event
from decision_agent.shared.providers.registry import get_provider

def _execute_workers_in_thread(
    run_id: str,
    root: Path,
    provider_override: str | None,
    audit_path: Path,
) -> None:
    started: set[str] = set()
    provider = get_provider(provider_override)
    for _ in range(240):  # ~4 minutes at 1s poll
        run = read_run(run_id, root)
        if not run:
            return
        contracts = run.get("generated_contracts") or run.get("contracts", [])
        if not contracts:
            return
        if is_run_complete(run, contracts):
            return
        gates = (run.get("architecture_proposal") or {}).get("topology", {}).get("gates", [])
        ready = [
            wid for wid in get_ready_worker_ids(run, contracts, gates)
            if wid not in started
        ]
        if not ready and not has_active_workers(run, contracts) and has_blocked_workers(run, contracts):
            return
        if not ready:
            time.sleep(1.0)
            continue
        worker_threads = []
        for worker_id in ready:
            contract = next(c for c in contracts if c["worker_id"] == worker_id)
            started.add(worker_id)
            append_audit_event(
                audit_path,
                {"event": "worker_assigned", "run_id": run_id, "worker_id": worker_id},
            )

            is_retry_dispatch = False
            retry_attempt_num = 0
            for evt in reversed(run.get("audit", [])):
                if evt.get("event") == "worker_assigned" and evt.get("worker_id") == worker_id:
                    is_retry_dispatch = bool(evt.get("from_checkpoint"))
                    retry_attempt_num = int(evt.get("retry_attempt", 0))
                    break

            def _run(wid=worker_id, ct=contract, ir=is_retry_dispatch, ra=retry_attempt_num):
                try:
                    run_worker(run_id, wid, ct, audit_path, root, provider,
                               is_retry=ir, retry_attempt=ra)
                except Exception as exc:
                    append_audit_event(
                        audit_path,
                        {
                            "event": "worker_failed",
                            "run_id": run_id,
                            "worker_id": wid,
                            "error": str(exc)[:500],
                        },
                    )

            t = threading.Thread(target=_run, daemon=True)
            t.start()
            worker_threads.append(t)
        for t in worker_threads:
            t.join()


def _run_plain_model(
    run_id: str,
    fixture: dict[str, Any],
    root: Path,
    provider_override: str | None,
    fixture_id: str = "",
) -> None:
    from decision_agent.modules.evaluation.baseline_prompts import (
        detect_domain_from_fixture,
        get_a0_system_prompt,
    )

    provider = get_provider(provider_override)
    audit_path = root / "data" / "runs" / run_id / "audit.jsonl"

    domain = detect_domain_from_fixture(fixture_id)
    system = get_a0_system_prompt(domain)
    user = (
        f"Task: {fixture.get('title', '')}\n\n"
        f"{fixture.get('description', '')}"
    )
    append_audit_event(audit_path, {"event": "run_started", "run_id": run_id, "condition": "A0"})
    append_audit_event(audit_path, {"event": "llm_call_submitted", "run_id": run_id, "domain": domain})
    try:
        raw = provider.complete(system, user)
        import re as _re
        stripped = _re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=_re.IGNORECASE)
        stripped = _re.sub(r"\s*```\s*$", "", stripped.strip())
        output = json.loads(stripped)
    except Exception as exc:
        append_audit_event(audit_path, {"event": "llm_call_failed", "run_id": run_id, "error": str(exc)[:300]})
        return

    append_audit_event(audit_path, {"event": "llm_call_returned", "run_id": run_id})

    out_dir = root / "data" / "runs" / run_id / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "recommender.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    append_audit_event(audit_path, {"event": "run_completed", "run_id": run_id, "condition": "A0"})


def _run_informed_plain_model(
    run_id: str,
    fixture: dict[str, Any],
    root: Path,
    provider_override: str | None,
    fixture_id: str = "",
) -> None:
    """A0-inf: single LLM call with the full context governed workers would receive.

    Same as A0 but the user prompt includes all worker goals, evidence taxonomy,
    DSC scope rules, and knowledge files. This isolates architectural enforcement
    from information availability.
    """
    from decision_agent.modules.evaluation.baseline_prompts import (
        build_informed_context,
        detect_domain_from_fixture,
        get_a0_system_prompt,
    )

    provider = get_provider(provider_override)
    audit_path = root / "data" / "runs" / run_id / "audit.jsonl"

    domain = detect_domain_from_fixture(fixture_id)
    system = get_a0_system_prompt(domain)
    informed_context = build_informed_context(domain, root)
    user = (
        f"Task: {fixture.get('title', '')}\n\n"
        f"{fixture.get('description', '')}\n\n"
        f"{informed_context}"
    )
    append_audit_event(audit_path, {"event": "run_started", "run_id": run_id, "condition": "A0_inf"})
    append_audit_event(audit_path, {"event": "llm_call_submitted", "run_id": run_id, "domain": domain})
    try:
        raw = provider.complete(system, user)
        stripped = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```\s*$", "", stripped.strip())
        output = json.loads(stripped)
    except Exception as exc:
        append_audit_event(audit_path, {"event": "llm_call_failed", "run_id": run_id, "error": str(exc)[:300]})
        return

    append_audit_event(audit_path, {"event": "llm_call_returned", "run_id": run_id})

    out_dir = root / "data" / "runs" / run_id / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "recommender.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    append_audit_event(audit_path, {"event": "run_completed", "run_id": run_id, "condition": "A0_inf"})


def _execute_graph(
    run_id: str,
    root: Path,
    provider_override: str | None,
    audit_path: Path,
    task_context: dict[str, Any] | None = None,
    layer_config: Any | None = None,
    memory: Any | None = None,
) -> None:
    from decision_agent.modules.governance.layer_config import LayerConfig
    from decision_agent.modules.graph.domain_graphs.procurement import build_procurement_graph
    from decision_agent.modules.graph.executor import GraphExecutor
    from decision_agent.modules.operators.base import OperatorContext

    provider = get_provider(provider_override)
    if isinstance(layer_config, dict):
        cfg = LayerConfig.from_dict(layer_config)
    elif isinstance(layer_config, LayerConfig):
        cfg = layer_config
    else:
        cfg = LayerConfig.full()

    graph = build_procurement_graph(run_id, task_context=task_context)
    context = OperatorContext(
        run_id=run_id,
        agent_id="graph_executor",
        project_root=root,
        audit_path=audit_path,
        provider=provider,
        layer_config=cfg,
        memory=memory,
    )
    executor = GraphExecutor()
    executor.execute(graph, context)


def _apply_evidence_overrides(run_id: str, root: Path, overrides: dict[str, Any]) -> None:
    contracts_dir = root / "data" / "runs" / run_id / "generated-contracts"
    if not contracts_dir.exists():
        return
    for contract_path in contracts_dir.glob("*.json"):
        try:
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        profile = contract.get("evidence_profile")
        if not isinstance(profile, dict):
            continue
        profile.update(overrides)
        contract["evidence_profile"] = profile
        contract_path.write_text(
            json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

