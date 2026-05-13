from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from decision_agent.modules.governance.layer_config import LayerConfig
from decision_agent.modules.runs.scheduler import (
    has_active_workers,
    has_blocked_workers,
    is_run_complete,
)
from decision_agent.modules.runs.service import (
    gate_approve,
    read_run,
)
from decision_agent.modules.runs.state import (
    AGENT_STATUS_REJECTED,
    AGENT_STATUS_FAILED,
    AUTHORIZATION_RECEIPT_RECORDED,
    PHASE_GATE_APPROVED,
    RUN_FAILED,
    WORKER_ASSIGNED,
)
from decision_agent.shared.audit_log import append_audit_event

_MAX_RETRIES_DEFAULT = 2


def auto_approve_phase_gates_once(run_id: str, root: Path) -> int:
    run = read_run(run_id, root)
    if not run:
        return 0
    cfg = LayerConfig.from_dict(run.get("layer_config"))
    if not cfg.human_gate_enabled:
        return 0
    proposal = run.get("architecture_proposal") or {}
    topology = proposal.get("topology") or {}
    gates = topology.get("gates") or []
    if not gates:
        return 0

    audit_path = root / "data" / "runs" / run_id / "audit.jsonl"
    approved_phases = {
        e.get("phase_id")
        for e in run.get("audit", [])
        if e.get("event") == PHASE_GATE_APPROVED
    }
    count = 0
    for gate in gates:
        phase_id = gate.get("placement")
        if not phase_id or phase_id in approved_phases:
            continue
        append_audit_event(
            audit_path,
            {
                "event": PHASE_GATE_APPROVED,
                "run_id": run_id,
                "phase_id": phase_id,
                "note": "benchmark_auto_approver",
            },
        )
        count += 1
    return count


def auto_approve_phase_gate_when_dar_decided(run_id: str, root: Path) -> int:
    run = read_run(run_id, root)
    if not run:
        return 0
    cfg = LayerConfig.from_dict(run.get("layer_config"))
    if not cfg.human_gate_enabled:
        return 0
    audit = run.get("audit", [])
    receipts = [
        e for e in audit if e.get("event") == AUTHORIZATION_RECEIPT_RECORDED
    ]
    if not receipts:
        return 0
    if any(r.get("decision") == "DENY" for r in receipts):
        return 0
    return auto_approve_phase_gates_once(run_id, root)


def auto_finalize_when_complete(run_id: str, root: Path) -> bool:
    run = read_run(run_id, root)
    if not run:
        return False
    contracts = run.get("generated_contracts") or run.get("contracts", [])
    if not contracts:
        return False
    if not is_run_complete(run, contracts):
        return False
    audit = run.get("audit", [])
    if any(e.get("event") in {"gate_approved", "run_completed"} for e in audit):
        return False
    try:
        gate_approve(run_id, "benchmark_auto_finalize", root)
    except ValueError:
        return False
    return True


def auto_fail_when_blocked(run_id: str, root: Path) -> bool:
    run = read_run(run_id, root)
    if not run:
        return False
    contracts = run.get("generated_contracts") or run.get("contracts", [])
    if not contracts:
        return False
    if has_active_workers(run, contracts):
        return False
    if not has_blocked_workers(run, contracts):
        return False
    audit = run.get("audit", [])
    if any(e.get("event") == RUN_FAILED for e in audit):
        return False
    append_audit_event(
        root / "data" / "runs" / run_id / "audit.jsonl",
        {
            "event": RUN_FAILED,
            "run_id": run_id,
            "reason": "benchmark_blocked_after_worker_failure",
        },
    )
    return True


def auto_retry_rejected_workers(
    run_id: str,
    root: Path,
    max_retries: int = _MAX_RETRIES_DEFAULT,
) -> list[str]:
    run = read_run(run_id, root)
    if not run:
        return []

    worker_statuses = run.get("worker_statuses", {})
    audit = run.get("audit", [])
    audit_path = root / "data" / "runs" / run_id / "audit.jsonl"
    checkpoints_dir = root / "data" / "runs" / run_id / "checkpoints"

    retry_counts: dict[str, int] = {}
    for event in audit:
        if event.get("event") == "worker_retry_started":
            wid = event.get("worker_id", "")
            if wid:
                retry_counts[wid] = retry_counts.get(wid, 0) + 1

    retried: list[str] = []
    for worker_id, status in worker_statuses.items():
        if status not in {AGENT_STATUS_REJECTED, AGENT_STATUS_FAILED}:
            continue
        if retry_counts.get(worker_id, 0) >= max_retries:
            continue
        checkpoint_file = checkpoints_dir / f"{worker_id}.json"
        if not checkpoint_file.exists():
            continue
        append_audit_event(
            audit_path,
            {
                "event": WORKER_ASSIGNED,
                "run_id": run_id,
                "worker_id": worker_id,
                "retry_attempt": retry_counts.get(worker_id, 0) + 1,
                "from_checkpoint": True,
            },
        )
        retried.append(worker_id)

    return retried


def watch_run_to_completion(
    run_id: str,
    root: Path,
    timeout_seconds: float,
    poll_interval: float = 0.5,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        auto_retry_rejected_workers(run_id, root)
        auto_approve_phase_gate_when_dar_decided(run_id, root)
        if auto_fail_when_blocked(run_id, root):
            break
        if auto_finalize_when_complete(run_id, root):
            break
        run = read_run(run_id, root)
        if run and run.get("status") in {"completed", "failed"}:
            break
        time.sleep(poll_interval)
    return read_run(run_id, root) or {}
