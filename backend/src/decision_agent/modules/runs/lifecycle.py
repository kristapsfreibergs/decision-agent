from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.modules.runs.io import _load_run, _read_outputs
from decision_agent.shared.audit_log import append_audit_event

def start_run(run_id: str, root: Path) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")
    audit_path = run_dir / "audit.jsonl"
    append_audit_event(audit_path, {"event": "run_started", "run_id": run_id})
    run = _load_run(run_dir)
    return run


def post_worker_message(run_id: str, worker_id: str, message: str, root: Path) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")
    if not any(contract.get("worker_id") == worker_id for contract in run.get("contracts", [])):
        raise ValueError(f"Worker not found: {worker_id}")
    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {
            "event": "worker_message",
            "run_id": run_id,
            "worker_id": worker_id,
            "role": "human",
            "text": message,
        },
    )
    run = _load_run(run_dir)
    return run


def answer_worker(run_id: str, worker_id: str, answer: str, root: Path) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")
    if not any(contract.get("worker_id") == worker_id for contract in run.get("contracts", [])):
        raise ValueError(f"Worker not found: {worker_id}")
    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {
            "event": "human_answered",
            "run_id": run_id,
            "worker_id": worker_id,
            "answer": answer,
        },
    )
    run = _load_run(run_dir)
    return run


def gate_approve(run_id: str, note: str, root: Path) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")
    cfg = LayerConfig.from_dict(run.get("layer_config"))
    if cfg.dar_enabled:
        receipts = run.get("authorization") or []
        ok = any(
            r.get("decision") in {"ALLOW", "ESCALATE"} for r in receipts
        )
        if not ok:
            raise ValueError(
                "DAR: gate_approve requires an authorization receipt with decision "
                "ALLOW or ESCALATE. None found."
            )
    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {"event": "gate_approved", "run_id": run_id, "note": note},
    )
    # Index evidence from completed run into cross-run memory
    _index_run_to_memory(run_id, run_dir, run, root)
    run = _load_run(run_dir)
    return run


def _index_run_to_memory(
    run_id: str,
    run_dir: Path,
    run: dict[str, Any],
    root: Path,
) -> None:
    """Write validated worker evidence into cross-run memory after gate approval.

    Only validated workers are indexed — rejected/failed workers are excluded.
    This makes past run evidence searchable by future workers via memory_search.
    """
    try:
        from decision_agent.shared.memory.base import MemoryItem
        from decision_agent.shared.memory.registry import get_memory_provider
    except ImportError:
        return

    domain = run.get("decision_type", "generic")
    worker_statuses = run.get("worker_statuses", {})
    outputs = _read_outputs(run_dir)
    provider = get_memory_provider(root / "data")

    for worker_id, output in outputs.items():
        if worker_statuses.get(worker_id) not in {"validated", "submitted"}:
            continue
        sources = output.get("evidence_sources") or []
        for source in sources:
            if isinstance(source, dict):
                src_type = source.get("type", "")
                excerpt = source.get("excerpt", "") or str(source)[:300]
                created_at = source.get("created_at", "")
            elif isinstance(source, str):
                src_type = source
                excerpt = source
                created_at = ""
            else:
                continue
            if not src_type:
                continue
            provider.write(MemoryItem(
                source_run_id=run_id,
                worker_id=worker_id,
                evidence_class=src_type,
                content=excerpt,
                created_at=created_at,
                domain=domain,
            ))


def gate_reject(run_id: str, reason: str, root: Path) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")
    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {"event": "gate_rejected", "run_id": run_id, "reason": reason},
    )
    run = _load_run(run_dir)
    return run

