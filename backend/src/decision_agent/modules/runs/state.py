from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Event vocabulary
# ---------------------------------------------------------------------------
# run-level events
RUN_CREATED = "run_created"
RUN_READY = "run_ready"
RUN_STARTED = "run_started"
RUN_COMPLETED = "run_completed"
RUN_FAILED = "run_failed"

# contract events
CONTRACT_CREATED = "contract_created"

# worker-level events
WORKER_ASSIGNED = "worker_assigned"
WORKER_STARTED = "worker_started"
WORKER_MESSAGE = "worker_message"
WORKER_NEEDS_HUMAN = "worker_needs_human"
WORKER_SUBMITTED = "worker_submitted"
WORKER_HEARTBEAT = "worker_heartbeat"
WORKER_FAILED = "worker_failed"

# human interaction events
HUMAN_ANSWERED = "human_answered"

# validation events
VALIDATION_PASSED = "validation_passed"
VALIDATION_FAILED = "validation_failed"

# gate events
GATE_APPROVED = "gate_approved"
GATE_REJECTED = "gate_rejected"

# architecture proposal events
ARCHITECTURE_BUILD_STARTED = "architecture_build_started"
GOAL_STRUCTURE_CLASSIFIED = "goal_structure_classified"
TOPOLOGY_BUILT = "topology_built"
PACKAGES_DECOMPOSED = "packages_decomposed"
PLANNING_ARTIFACT_CREATED = "planning_artifact_created"
PLANNING_ARTIFACT_APPROVED = "planning_artifact_approved"
PLANNING_ARTIFACT_REJECTED = "planning_artifact_rejected"
ARCHITECTURE_PROPOSED = "architecture_proposed"
ARCHITECTURE_PROPOSAL_VALIDATED = "architecture_proposal_validated"
ARCHITECTURE_PROPOSAL_REJECTED = "architecture_proposal_rejected"
ARCHITECTURE_APPROVED = "architecture_approved"
ARCHITECTURE_REJECTED = "architecture_rejected"

# generated contract events
CONTRACTS_GENERATION_STARTED = "contracts_generation_started"
GENERATED_CONTRACT_CREATED = "generated_contract_created"
CONTRACTS_GENERATION_COMPLETED = "contracts_generation_completed"
CONTRACTS_GENERATION_FAILED = "contracts_generation_failed"
CONTRACTS_GENERATED = "contracts_generated"

# ---------------------------------------------------------------------------
# Run statuses (derived)
# ---------------------------------------------------------------------------
RUN_STATUS_CREATED = "created"
RUN_STATUS_READY = "ready"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_WAITING_HUMAN = "waiting_human"
RUN_STATUS_VALIDATING = "validating"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"

# ---------------------------------------------------------------------------
# Agent statuses (derived)
# ---------------------------------------------------------------------------
AGENT_STATUS_PLANNED = "planned"
AGENT_STATUS_ASSIGNED = "assigned"
AGENT_STATUS_WORKING = "working"
AGENT_STATUS_NEEDS_HUMAN = "needs_human"
AGENT_STATUS_BLOCKED = "blocked"
AGENT_STATUS_SUBMITTED = "submitted"
AGENT_STATUS_VALIDATED = "validated"
AGENT_STATUS_REJECTED = "rejected"
AGENT_STATUS_FAILED = "failed"

# ---------------------------------------------------------------------------
# State derivation
# ---------------------------------------------------------------------------

_RUN_EVENT_TO_STATUS: dict[str, str] = {
    RUN_CREATED: RUN_STATUS_CREATED,
    RUN_READY: RUN_STATUS_READY,
    RUN_STARTED: RUN_STATUS_RUNNING,
    WORKER_NEEDS_HUMAN: RUN_STATUS_WAITING_HUMAN,
    HUMAN_ANSWERED: RUN_STATUS_RUNNING,
    WORKER_SUBMITTED: RUN_STATUS_VALIDATING,
    VALIDATION_PASSED: RUN_STATUS_VALIDATING,
    VALIDATION_FAILED: RUN_STATUS_RUNNING,
    GATE_APPROVED: RUN_STATUS_COMPLETED,
    GATE_REJECTED: RUN_STATUS_FAILED,
    RUN_COMPLETED: RUN_STATUS_COMPLETED,
    RUN_FAILED: RUN_STATUS_FAILED,
}

_WORKER_EVENT_TO_STATUS: dict[str, str] = {
    CONTRACT_CREATED: AGENT_STATUS_PLANNED,
    WORKER_ASSIGNED: AGENT_STATUS_ASSIGNED,
    WORKER_STARTED: AGENT_STATUS_WORKING,
    WORKER_HEARTBEAT: AGENT_STATUS_WORKING,
    WORKER_NEEDS_HUMAN: AGENT_STATUS_NEEDS_HUMAN,
    HUMAN_ANSWERED: AGENT_STATUS_WORKING,
    WORKER_SUBMITTED: AGENT_STATUS_SUBMITTED,
    VALIDATION_PASSED: AGENT_STATUS_VALIDATED,
    VALIDATION_FAILED: AGENT_STATUS_REJECTED,
    WORKER_FAILED: AGENT_STATUS_FAILED,
}


def derive_run_status(events: list[dict[str, Any]]) -> str:
    """Return the current run status by replaying events in order."""
    status = RUN_STATUS_CREATED
    for event in events:
        name = event.get("event", "")
        if name in _RUN_EVENT_TO_STATUS:
            status = _RUN_EVENT_TO_STATUS[name]
    return status


def derive_worker_statuses(events: list[dict[str, Any]]) -> dict[str, str]:
    """Return {worker_id: status} by replaying events in order."""
    statuses: dict[str, str] = {}
    for event in events:
        name = event.get("event", "")
        worker_id = event.get("worker_id")
        if worker_id and name in _WORKER_EVENT_TO_STATUS:
            statuses[worker_id] = _WORKER_EVENT_TO_STATUS[name]
        elif name in (CONTRACT_CREATED, GENERATED_CONTRACT_CREATED) and worker_id:
            statuses.setdefault(worker_id, AGENT_STATUS_PLANNED)
    return statuses


def derive_worker_messages(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Return {worker_id: [message_event, ...]} for chat display."""
    messages: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        worker_id = event.get("worker_id")
        if not worker_id:
            continue
        if event.get("event") in (WORKER_MESSAGE, WORKER_NEEDS_HUMAN, HUMAN_ANSWERED, WORKER_SUBMITTED):
            messages.setdefault(worker_id, []).append(event)
    return messages


def enrich_run(run: dict[str, Any]) -> dict[str, Any]:
    """Add derived status fields to a run record (non-destructive)."""
    events: list[dict[str, Any]] = run.get("audit", [])
    worker_statuses = derive_worker_statuses(events)
    worker_messages = derive_worker_messages(events)
    return {
        **run,
        "status": derive_run_status(events),
        "worker_statuses": worker_statuses,
        "worker_messages": worker_messages,
    }
