from __future__ import annotations

from typing import Any

from decision_agent.modules.runs.state import (
    AGENT_STATUS_ASSIGNED,
    AGENT_STATUS_FAILED,
    AGENT_STATUS_PLANNED,
    AGENT_STATUS_REJECTED,
    AGENT_STATUS_VALIDATED,
    AGENT_STATUS_WORKING,
    PHASE_GATE_APPROVED,
)

TERMINAL_STATUSES = {AGENT_STATUS_VALIDATED, AGENT_STATUS_REJECTED, AGENT_STATUS_FAILED}


def is_phase_gate_cleared(run: dict[str, Any], phase_id: str | None, gates: list[dict[str, Any]]) -> bool:
    """Return True if there is no gate for this phase, or if the gate has been approved."""
    if not phase_id:
        return True
    phase_gate = next((g for g in gates if g.get("placement") == phase_id), None)
    if phase_gate is None:
        return True
    return any(
        e.get("event") == PHASE_GATE_APPROVED and e.get("phase_id") == phase_id
        for e in run.get("audit", [])
    )


def get_ready_worker_ids(
    run: dict[str, Any],
    all_contracts: list[dict[str, Any]],
    gates: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return worker IDs that are ready to execute: planned/assigned + all deps validated + phase gate cleared."""
    gates = gates or []
    statuses = run.get("worker_statuses", {})
    deps_map = {
        contract["worker_id"]: contract.get("depends_on", [])
        for contract in all_contracts
    }

    ready = []
    for contract in all_contracts:
        worker_id = contract["worker_id"]
        status = statuses.get(worker_id, AGENT_STATUS_PLANNED)
        if status not in (AGENT_STATUS_PLANNED, AGENT_STATUS_ASSIGNED):
            continue
        if not is_phase_gate_cleared(run, contract.get("phase_id"), gates):
            continue
        deps = deps_map.get(worker_id, [])
        if all(statuses.get(dep) == AGENT_STATUS_VALIDATED for dep in deps):
            ready.append(worker_id)
    return ready


def is_run_complete(run: dict[str, Any], all_contracts: list[dict[str, Any]]) -> bool:
    """True when every worker has reached a terminal status."""
    statuses = run.get("worker_statuses", {})
    return all(
        statuses.get(contract["worker_id"]) in TERMINAL_STATUSES
        for contract in all_contracts
    )


def has_active_workers(run: dict[str, Any], all_contracts: list[dict[str, Any]]) -> bool:
    statuses = run.get("worker_statuses", {})
    return any(
        statuses.get(contract["worker_id"]) in (AGENT_STATUS_ASSIGNED, AGENT_STATUS_WORKING)
        for contract in all_contracts
    )


def has_blocked_workers(run: dict[str, Any], all_contracts: list[dict[str, Any]]) -> bool:
    """True when a not-started worker depends on a rejected/failed worker."""
    statuses = run.get("worker_statuses", {})
    deps_map = {
        contract["worker_id"]: contract.get("depends_on", [])
        for contract in all_contracts
    }
    for contract in all_contracts:
        worker_id = contract["worker_id"]
        status = statuses.get(worker_id, AGENT_STATUS_PLANNED)
        if status not in (AGENT_STATUS_PLANNED, AGENT_STATUS_ASSIGNED):
            continue
        deps = deps_map.get(worker_id, [])
        if any(statuses.get(dep) in (AGENT_STATUS_REJECTED, AGENT_STATUS_FAILED) for dep in deps):
            return True
    return False
