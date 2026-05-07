from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from decision_agent.modules.contracts.validator import validate_worker_contract


def instantiate_generated_contract(
    worker: dict[str, Any],
    proposal: dict[str, Any],
    run: dict[str, Any],
) -> dict[str, Any]:
    run_id = run["run_id"]
    package_to_worker = {
        item.get("work_package_id", item["worker_id"]): item["worker_id"]
        for item in proposal.get("workers", [])
    }
    depends_on = [
        package_to_worker.get(dependency["on"], dependency["on"])
        for dependency in proposal.get("dependencies", [])
        if dependency.get("from") == worker.get("work_package_id", worker["worker_id"])
    ]
    # Map dependency worker_ids to their output file paths so this worker can read prior results
    dep_output_paths = [f"data/runs/{run_id}/outputs/{dep_id}.json" for dep_id in depends_on]

    def _fix_paths(paths: list[str]) -> list[str]:
        """Replace any stale run_id placeholder (e.g. 'preview') with the real run_id."""
        result = []
        for p in paths:
            # Replace data/runs/<anything>/  with data/runs/<run_id>/
            import re
            p = re.sub(r"^(data/runs/)[^/]+(/.+)$", rf"\g<1>{run_id}\2", p)
            result.append(p)
        return result

    raw_read_paths = _fix_paths(deepcopy(worker["read_paths"]))
    read_paths = raw_read_paths + [p for p in dep_output_paths if p not in raw_read_paths]

    return {
        "worker_id": worker["worker_id"],
        "work_package_id": worker.get("work_package_id"),
        "phase_id": worker.get("phase_id"),
        "worker_role": worker.get("worker_role", worker["worker_id"]),
        "layer": worker.get("layer", "execution"),
        "work_layer": worker.get("work_layer", worker.get("layer", "execution")),
        "architecture_id": proposal["architecture_id"],
        "run_id": run_id,
        "decision_id": run.get("decision_id") or uuid4().hex,
        "decision_type": proposal["decision_type"],
        "risk_level": proposal["risk_level"],
        "goal": worker["goal"],
        "context": {
            "task_title": (run.get("task") or {}).get("title"),
            "task_summary": (run.get("task") or {}).get("description"),
            "architecture_purpose": proposal.get("purpose"),
        },
        "depends_on": depends_on,
        "read_paths": read_paths,
        "write_paths": _fix_paths(deepcopy(worker["write_paths"])),
        "allowed_tools": deepcopy(worker["allowed_tools"]),
        "max_steps": worker["max_steps"],
        "output_schema": deepcopy(worker["output_schema"]),
        "validators": deepcopy(worker["validators"]),
        "evidence_profile": deepcopy(proposal.get("evidence_profile") or {}),
        "completion_contract": worker["completion_contract"],
        "generated_from": "architecture-proposal.json",
    }


def generate_contracts_from_proposal(
    proposal: dict[str, Any],
    run: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    contracts = [
        instantiate_generated_contract(worker, proposal, run)
        for worker in proposal.get("workers", [])
    ]

    issues: list[str] = []
    for contract in contracts:
        result = validate_worker_contract(contract)
        for issue in result["issues"]:
            issues.append(f"{contract.get('worker_id', 'unknown worker')}: {issue}")

    return contracts, issues
