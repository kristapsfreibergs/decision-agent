from __future__ import annotations

import threading
import time
from pathlib import Path

from decision_agent.modules.runs.service import read_run
from decision_agent.modules.runs.state import PHASE_GATE_APPROVED
from decision_agent.modules.workers.runner import run_worker
from decision_agent.settings import get_settings
from decision_agent.shared.audit_log import append_audit_event

ROOT = Path.cwd()
SETTINGS = get_settings(ROOT)
_ACTIVE_SCHEDULERS: set[str] = set()
_SCHEDULER_LOCK = threading.Lock()

def _execute_in_background(
    run_id: str,
    worker_id: str,
    contract: dict,
    audit_path: Path,
    root: Path,
    provider: object,
) -> None:
    try:
        run_worker(run_id, worker_id, contract, audit_path, root, provider)
    except Exception as exc:
        append_audit_event(
            audit_path,
            {
                "event": "worker_failed",
                "run_id": run_id,
                "worker_id": worker_id,
                "error": str(exc),
            },
        )


def _is_phase_gate_cleared(run: dict, phase_id: str | None, gates: list[dict]) -> bool:
    if not phase_id:
        return True
    phase_gate = next((g for g in gates if g.get("placement") == phase_id), None)
    if phase_gate is None:
        return True
    return any(
        e.get("event") == PHASE_GATE_APPROVED and e.get("phase_id") == phase_id
        for e in run.get("audit", [])
    )


def _can_execute_contract(run: dict, contract: dict) -> tuple[bool, str]:
    gates = (run.get("architecture_proposal") or {}).get("topology", {}).get("gates", [])
    phase_id = contract.get("phase_id")
    if not _is_phase_gate_cleared(run, phase_id, gates):
        return False, f"Phase gate for phase '{phase_id}' has not been approved."
    return True, ""


def _run_scheduler(run_id: str, root: Path, provider: object) -> None:
    from decision_agent.modules.runs.scheduler import (
        get_ready_worker_ids,
        has_active_workers,
        has_blocked_workers,
        is_run_complete,
    )

    audit_path = root / "data" / "runs" / run_id / "audit.jsonl"
    try:
        append_audit_event(audit_path, {"event": "scheduler_started", "run_id": run_id})
        started: set[str] = set()

        for _ in range(120):
            run = read_run(run_id, root)
            if not run:
                break

            all_contracts = run.get("generated_contracts", []) or run.get("contracts", [])
            if not all_contracts:
                break
            if is_run_complete(run, all_contracts):
                append_audit_event(audit_path, {"event": "scheduler_completed", "run_id": run_id})
                break

            gates = (run.get("architecture_proposal") or {}).get("topology", {}).get("gates", [])
            ready = [
                worker_id
                for worker_id in get_ready_worker_ids(run, all_contracts, gates)
                if worker_id not in started
            ]
            if not ready and not has_active_workers(run, all_contracts) and has_blocked_workers(run, all_contracts):
                append_audit_event(audit_path, {"event": "scheduler_blocked", "run_id": run_id})
                break

            for worker_id in ready:
                contract = next(c for c in all_contracts if c["worker_id"] == worker_id)
                started.add(worker_id)
                append_audit_event(
                    audit_path,
                    {"event": "worker_assigned", "run_id": run_id, "worker_id": worker_id},
                )
                threading.Thread(
                    target=_execute_in_background,
                    args=(run_id, worker_id, contract, audit_path, root, provider),
                    daemon=True,
                ).start()

            time.sleep(5)
    finally:
        with _SCHEDULER_LOCK:
            _ACTIVE_SCHEDULERS.discard(run_id)

