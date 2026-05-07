from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from decision_agent.modules.architectures.registry import find_architecture_for_decision
from decision_agent.modules.architectures.proposal import (
    build_planning_artifact,
    artifact_to_proposal,
    propose_architecture,
    validate_architecture_proposal,
)
from decision_agent.modules.contracts.generator import generate_contracts_from_proposal
from decision_agent.modules.contracts.validator import (
    validate_architecture,
    validate_worker_contract,
)
from decision_agent.modules.decisions.router import classify_decision_type
from decision_agent.modules.runs.state import (
    ARCHITECTURE_APPROVED,
    ARCHITECTURE_BUILD_STARTED,
    CONTRACTS_GENERATED,
    ARCHITECTURE_PROPOSAL_REJECTED,
    ARCHITECTURE_PROPOSAL_VALIDATED,
    ARCHITECTURE_PROPOSED,
    ARCHITECTURE_REJECTED,
    CONTRACTS_GENERATION_COMPLETED,
    CONTRACTS_GENERATION_FAILED,
    CONTRACTS_GENERATION_STARTED,
    GENERATED_CONTRACT_CREATED,
    GOAL_STRUCTURE_CLASSIFIED,
    PACKAGES_DECOMPOSED,
    PLANNING_ARTIFACT_APPROVED,
    PLANNING_ARTIFACT_CREATED,
    PLANNING_ARTIFACT_REJECTED,
    TOPOLOGY_BUILT,
    enrich_run,
)
from decision_agent.shared.audit_log import append_audit_event, read_audit
from decision_agent.shared.providers.base import LLMProvider


def _run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"run_{stamp}_{uuid4().hex[:8]}"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _read_outputs(run_dir: Path) -> dict[str, Any]:
    outputs_dir = run_dir / "outputs"
    if not outputs_dir.exists():
        return {}

    outputs: dict[str, Any] = {}
    for output_file in sorted(outputs_dir.glob("*.json")):
        output = _read_json(output_file)
        if output is not None:
            outputs[output_file.stem] = output
    return outputs


def _read_architecture_proposal(run_dir: Path) -> dict[str, Any] | None:
    return _read_json(run_dir / "architecture-proposal.json")


def _read_planning_artifact(run_dir: Path) -> dict[str, Any] | None:
    return _read_json(run_dir / "planning-artifact.json")


_RUN_PATH_RE = re.compile(r"^(data/runs/)[^/]+(/.+)$")


def _normalize_contract_run_paths(contract: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Repair stale generated contracts that still contain preview run paths."""
    normalized = deepcopy(contract)
    normalized["run_id"] = run_id
    for field in ("read_paths", "write_paths"):
        paths = normalized.get(field)
        if not isinstance(paths, list):
            continue
        normalized[field] = [
            _RUN_PATH_RE.sub(rf"\g<1>{run_id}\2", path) if isinstance(path, str) else path
            for path in paths
        ]
    return normalized


def _read_contracts_dir(contracts_dir: Path, run_id: str | None = None) -> list[dict[str, Any]]:
    contracts = []
    if contracts_dir.exists():
        for contract_file in sorted(contracts_dir.glob("*.json")):
            contract = _read_json(contract_file)
            if contract:
                if run_id is not None:
                    contract = _normalize_contract_run_paths(contract, run_id)
                contracts.append(contract)
    return contracts


def _has_audit_event(run: dict[str, Any], event_name: str) -> bool:
    return any(event.get("event") == event_name for event in run.get("audit", []))


def instantiate_worker_contract(
    architecture: dict[str, Any],
    worker: dict[str, Any],
    task: dict[str, Any],
    run_id: str,
    decision: dict[str, Any],
) -> dict[str, Any]:
    return {
        "worker_id": worker["worker_id"],
        "layer": worker["layer"],
        "work_layer": worker.get("work_layer", worker["layer"]),
        "architecture_id": architecture["id"],
        "run_id": run_id,
        "decision_id": task.get("task_id") or uuid4().hex,
        "decision_type": architecture["decision_type"],
        "risk_level": architecture["risk_level"],
        "goal": worker["goal"],
        "context": {
            "task_title": task.get("title"),
            "task_summary": task.get("description"),
            "router_reason": decision["reason"],
        },
        "read_paths": deepcopy(worker["read_paths"]),
        "write_paths": deepcopy(worker["write_paths"]),
        "allowed_tools": deepcopy(worker["allowed_tools"]),
        "max_steps": worker["max_steps"],
        "output_schema": deepcopy(worker["output_schema"]),
        "validators": deepcopy(worker["validators"]),
        "completion_contract": worker["completion_contract"],
    }


def create_run(task: dict[str, Any], root: Path) -> dict[str, Any]:
    decision = classify_decision_type(task)
    architecture = find_architecture_for_decision(decision["decision_type"])

    run_id = _run_id()
    run_dir = root / "data" / "runs" / run_id
    contracts_dir = run_dir / "contracts"
    audit_path = run_dir / "audit.jsonl"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "task.json", task)

    # Dynamic runs (no registered static architecture) skip bootstrap contracts.
    # Architecture and contracts are built later via /architecture/build and /architecture/generate-contracts.
    is_dynamic = architecture is None

    if not is_dynamic:
        architecture_validation = validate_architecture(architecture)
        if not architecture_validation["valid"]:
            joined = "; ".join(architecture_validation["issues"])
            raise ValueError(f"Invalid architecture {architecture['id']}: {joined}")

    append_audit_event(
        audit_path,
        {
            "event": "run_created",
            "run_id": run_id,
            "decision_type": decision["decision_type"],
            "architecture_id": architecture["id"] if architecture else "dynamic",
            "task_title": task.get("title"),
        },
    )

    contracts: list[dict[str, Any]] = []
    if not is_dynamic:
        contracts = [
            instantiate_worker_contract(architecture, worker, task, run_id, decision)
            for worker in architecture["workers"]
        ]
        for contract in contracts:
            result = validate_worker_contract(contract)
            if not result["valid"]:
                joined = "; ".join(result["issues"])
                raise ValueError(f"Invalid contract {contract['worker_id']}: {joined}")
            _write_json(contracts_dir / f"{contract['worker_id']}.json", contract)
            append_audit_event(
                audit_path,
                {
                    "event": "contract_created",
                    "run_id": run_id,
                    "worker_id": contract["worker_id"],
                    "layer": contract["layer"],
                    "goal": contract["goal"],
                    "write_paths": contract["write_paths"],
                },
            )

    run_record = {
        "run_id": run_id,
        "decision_id": task.get("task_id"),
        "decision_type": decision["decision_type"],
        "router_confidence": decision["confidence"],
        "router_reason": decision["reason"],
        "architecture_id": architecture["id"] if architecture else "dynamic",
        "risk_level": architecture["risk_level"] if architecture else "medium",
        "action_gate": deepcopy(architecture["action_gate"]) if architecture else {"type": "human_gate", "requires_human_review": True, "automatic_final_action": False},
        "outcome_metrics": deepcopy(architecture["outcome_metrics"]) if architecture else ["planning_artifact_created", "architecture_approved", "contracts_generated"],
        "contracts": [
            {
                "worker_id": contract["worker_id"],
                "contract_file": f"contracts/{contract['worker_id']}.json",
                "write_paths": contract["write_paths"],
                "max_steps": contract["max_steps"],
            }
            for contract in contracts
        ],
    }

    _write_json(run_dir / "run-record.json", run_record)
    append_audit_event(
        audit_path,
        {"event": "run_ready", "run_id": run_id, "contract_count": len(contracts)},
    )

    audit = read_audit(audit_path)
    return enrich_run({**run_record, "run_dir": str(run_dir), "contracts": contracts, "task": task, "audit": audit})


def _load_run(run_dir: Path) -> dict[str, Any] | None:
    record = _read_json(run_dir / "run-record.json")
    if not record:
        return None
    run_id = record["run_id"]
    contracts = _read_contracts_dir(run_dir / "contracts", run_id)
    generated_contracts = _read_contracts_dir(run_dir / "generated-contracts", run_id)
    audit = read_audit(run_dir / "audit.jsonl")
    return enrich_run(
        {
            **record,
            "task": _read_json(run_dir / "task.json"),
            "contracts": contracts,
            "generated_contracts": generated_contracts,
            "audit": audit,
            "outputs": _read_outputs(run_dir),
            "architecture_proposal": _read_architecture_proposal(run_dir),
            "planning_artifact": _read_planning_artifact(run_dir),
            "run_dir": str(run_dir),
        }
    )


def read_runs(root: Path) -> list[dict[str, Any]]:
    runs_dir = root / "data" / "runs"
    if not runs_dir.exists():
        return []

    runs: list[dict[str, Any]] = []
    for run_dir in sorted((entry for entry in runs_dir.iterdir() if entry.is_dir()), reverse=True):
        run = _load_run(run_dir)
        if run:
            runs.append(run)

    return runs


def read_run(run_id: str, root: Path) -> dict[str, Any] | None:
    run_dir = root / "data" / "runs" / run_id
    if not run_dir.exists():
        return None
    return _load_run(run_dir)


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
    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {"event": "gate_approved", "run_id": run_id, "note": note},
    )
    run = _load_run(run_dir)
    return run


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


def build_architecture_proposal(run_id: str, root: Path, provider: LLMProvider, prebuilt_artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")

    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {"event": ARCHITECTURE_BUILD_STARTED, "run_id": run_id, "provider": provider.name},
    )

    if prebuilt_artifact is not None:
        from decision_agent.modules.architectures.proposal import artifact_to_proposal
        # Patch planning_id and run_id to match the actual run
        prebuilt_artifact = {**prebuilt_artifact, "planning_id": f"planning/{run['decision_type']}/{run_id}", "run_id": run_id}
        artifact = prebuilt_artifact
        proposal = artifact_to_proposal(artifact, run)
    else:
        artifact, proposal = propose_architecture(run, provider, root)
    proposal_result = validate_architecture_proposal(proposal)
    if not proposal_result["valid"]:
        append_audit_event(
            audit_path,
            {
                "event": ARCHITECTURE_PROPOSAL_REJECTED,
                "run_id": run_id,
                "issues": proposal_result["issues"],
            },
        )
        raise ValueError(f"Invalid architecture proposal: {'; '.join(proposal_result['issues'])}")

    _write_json(run_dir / "planning-artifact.json", artifact)
    _write_json(run_dir / "architecture-proposal.json", proposal)
    append_audit_event(
        audit_path,
        {
            "event": GOAL_STRUCTURE_CLASSIFIED,
            "run_id": run_id,
            "shape": artifact["goal_structure"]["shape"],
            "modifiers": artifact["goal_structure"]["modifiers"],
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": TOPOLOGY_BUILT,
            "run_id": run_id,
            "shape": artifact["topology"]["shape"],
            "phase_count": len(artifact["topology"]["phases"]),
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": PACKAGES_DECOMPOSED,
            "run_id": run_id,
            "package_count": len(artifact["packages"]),
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": PLANNING_ARTIFACT_CREATED,
            "run_id": run_id,
            "planning_id": artifact["planning_id"],
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": ARCHITECTURE_PROPOSED,
            "run_id": run_id,
            "architecture_id": proposal["architecture_id"],
            "worker_count": len(proposal.get("workers", [])),
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": ARCHITECTURE_PROPOSAL_VALIDATED,
            "run_id": run_id,
            "architecture_id": proposal["architecture_id"],
        },
    )
    run = _load_run(run_dir)
    return run


def approve_architecture(run_id: str, note: str, root: Path) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")
    proposal = run.get("architecture_proposal")
    if not proposal:
        raise ValueError("No architecture proposal exists for this run.")

    result = validate_architecture_proposal(proposal)
    if not result["valid"]:
        raise ValueError(f"Invalid architecture proposal: {'; '.join(result['issues'])}")

    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {
            "event": ARCHITECTURE_APPROVED,
            "run_id": run_id,
            "architecture_id": proposal["architecture_id"],
            "note": note,
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": PLANNING_ARTIFACT_APPROVED,
            "run_id": run_id,
            "planning_id": run["planning_artifact"]["planning_id"] if run.get("planning_artifact") else "",
            "note": note,
        },
    )
    run = _load_run(run_dir)
    return run


def reject_architecture(run_id: str, reason: str, root: Path) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")
    if not run.get("architecture_proposal"):
        raise ValueError("No architecture proposal exists for this run.")

    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {"event": ARCHITECTURE_REJECTED, "run_id": run_id, "reason": reason},
    )
    append_audit_event(
        audit_path,
        {
            "event": PLANNING_ARTIFACT_REJECTED,
            "run_id": run_id,
            "planning_id": run["planning_artifact"]["planning_id"] if run.get("planning_artifact") else "",
            "reason": reason,
        },
    )
    run = _load_run(run_dir)
    return run


def generate_contracts_for_approved_architecture(run_id: str, root: Path) -> dict[str, Any]:
    run_dir = root / "data" / "runs" / run_id
    run = _load_run(run_dir)
    if not run:
        raise ValueError(f"Run not found: {run_id}")
    if not run.get("architecture_proposal"):
        raise ValueError("No architecture proposal exists for this run.")
    if not _has_audit_event(run, ARCHITECTURE_APPROVED):
        raise ValueError("Architecture must be approved before generating contracts.")

    proposal = run["architecture_proposal"]
    audit_path = run_dir / "audit.jsonl"
    append_audit_event(
        audit_path,
        {
            "event": CONTRACTS_GENERATION_STARTED,
            "run_id": run_id,
            "architecture_id": proposal["architecture_id"],
        },
    )

    contracts, issues = generate_contracts_from_proposal(proposal, run)
    if issues:
        append_audit_event(
            audit_path,
            {
                "event": CONTRACTS_GENERATION_FAILED,
                "run_id": run_id,
                "architecture_id": proposal["architecture_id"],
                "issues": issues,
            },
        )
        raise ValueError(f"Generated contract validation failed: {'; '.join(issues)}")

    generated_dir = run_dir / "generated-contracts"
    generated_dir.mkdir(parents=True, exist_ok=True)
    for contract in contracts:
        _write_json(generated_dir / f"{contract['worker_id']}.json", contract)
        append_audit_event(
            audit_path,
            {
                "event": GENERATED_CONTRACT_CREATED,
                "run_id": run_id,
                "worker_id": contract["worker_id"],
                "architecture_id": contract["architecture_id"],
                "write_paths": contract["write_paths"],
            },
        )

    append_audit_event(
        audit_path,
        {
            "event": CONTRACTS_GENERATION_COMPLETED,
            "run_id": run_id,
            "architecture_id": proposal["architecture_id"],
            "contract_count": len(contracts),
        },
    )
    append_audit_event(
        audit_path,
        {
            "event": CONTRACTS_GENERATED,
            "run_id": run_id,
            "contract_count": len(contracts),
        },
    )
    planning_artifact = run.get("planning_artifact")
    if planning_artifact:
        planning_artifact["contract_summaries"] = [
            {
                "worker_id": contract["worker_id"],
                "work_package_id": contract.get("work_package_id"),
                "phase_id": contract.get("phase_id"),
                "work_layer": contract.get("work_layer"),
            }
            for contract in contracts
        ]
        _write_json(run_dir / "planning-artifact.json", planning_artifact)
    run = _load_run(run_dir)
    return run
