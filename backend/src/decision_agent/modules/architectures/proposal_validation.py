from __future__ import annotations

from typing import Any

from decision_agent.modules.architectures.domain_catalog import PROVIDER_MARKERS

def validate_architecture_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    if not isinstance(proposal, dict):
        return {"valid": False, "issues": ["Proposal must be a JSON object."]}

    for field in [
        "architecture_id",
        "decision_type",
        "risk_level",
        "purpose",
        "goal_structure",
        "topology",
        "workers",
        "dependencies",
        "action_gate",
        "validators",
        "outcome_metrics",
    ]:
        if field not in proposal:
            issues.append(f"{field} is required.")

    if proposal.get("risk_level") not in {"low", "medium", "high"}:
        issues.append("risk_level must be low, medium, or high.")

    goal_structure = proposal.get("goal_structure")
    if not isinstance(goal_structure, dict) or goal_structure.get("shape") not in {"pipeline", "tree", "search", "funnel", "debate", "checker"}:
        issues.append("goal_structure.shape must be a supported shape.")

    topology = proposal.get("topology")
    if not isinstance(topology, dict) or not isinstance(topology.get("phases"), list) or not topology.get("phases"):
        issues.append("topology.phases must be a non-empty array.")

    workers = proposal.get("workers")
    if not isinstance(workers, list) or not workers:
        issues.append("workers must contain at least one worker.")
        workers = []

    worker_ids: set[str] = set()
    package_ids: set[str] = set()
    for worker in workers:
        if not isinstance(worker, dict):
            issues.append("workers contains a non-object worker.")
            continue
        worker_id = worker.get("worker_id")
        package_id = worker.get("work_package_id")
        if not isinstance(worker_id, str) or not worker_id:
            issues.append("worker_id must be a non-empty string.")
        else:
            worker_ids.add(package_id or worker_id)
        if not isinstance(package_id, str) or not package_id:
            issues.append(f"{worker_id or 'unknown worker'}: work_package_id is required.")
        else:
            package_ids.add(package_id)
        _validate_worker(worker, issues)

    for dependency in proposal.get("dependencies", []):
        if not isinstance(dependency, dict):
            issues.append("dependencies must contain objects.")
            continue
        source = dependency.get("from")
        target = dependency.get("on")
        if source not in package_ids:
            issues.append(f"dependency references unknown worker: {source}")
        if target not in package_ids:
            issues.append(f"dependency references unknown worker: {target}")

    if not proposal.get("worker_count_reasoning"):
        issues.append("worker_count_reasoning is required.")

    action_gate = proposal.get("action_gate")
    if not isinstance(action_gate, dict):
        issues.append("action_gate must be an object.")
    else:
        if proposal.get("risk_level") == "high" and action_gate.get("requires_human_review") is not True:
            issues.append("high-risk proposals must require human review.")
        if action_gate.get("automatic_final_action") is True:
            issues.append("action_gate must not allow automatic final action in V0.")

    _validate_no_provider_markers(proposal, issues)
    return {"valid": not issues, "issues": issues}


def _validate_worker(worker: dict[str, Any], issues: list[str]) -> None:
    for field in [
        "goal",
        "work_package_id",
        "phase_id",
        "worker_role",
        "read_paths",
        "write_paths",
        "allowed_tools",
        "max_steps",
        "output_schema",
        "validators",
        "completion_contract",
    ]:
        if field not in worker:
            issues.append(f"{worker.get('worker_id', 'unknown worker')}: {field} is required.")

    if any(path in {"*", "**/*"} for path in worker.get("write_paths", [])):
        issues.append(f"{worker.get('worker_id', 'unknown worker')}: repository-wide write scope is forbidden.")
    if "execute_final_action" in worker.get("allowed_tools", []):
        issues.append(f"{worker.get('worker_id', 'unknown worker')}: execute_final_action is forbidden.")
    if not isinstance(worker.get("max_steps"), int) or worker.get("max_steps", 0) < 1:
        issues.append(f"{worker.get('worker_id', 'unknown worker')}: max_steps must be positive.")


def _validate_no_provider_markers(value: Any, issues: list[str]) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _validate_no_provider_markers(item, issues)
    elif isinstance(value, list):
        for item in value:
            _validate_no_provider_markers(item, issues)
    elif isinstance(value, str):
        lowered = value.lower()
        for marker in PROVIDER_MARKERS:
            if marker in lowered:
                issues.append(f"provider-specific marker is forbidden: {marker}")
                return
