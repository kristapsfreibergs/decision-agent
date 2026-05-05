from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from decision_agent.modules.architectures.decomposers.software import decompose_software_task
from decision_agent.modules.architectures.goal_structure import classify_goal_structure
from decision_agent.modules.architectures.topology import build_topology
from decision_agent.shared.providers.base import LLMProvider

PROVIDER_MARKERS = [
    "anthropic",
    "claude",
    "openai",
    "gpt",
    "gemini",
    "llama",
    "mistral",
]


def build_mock_proposal(run: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    artifact = build_planning_artifact(run, root or Path.cwd())
    return artifact_to_proposal(artifact, run)


def build_planning_artifact(run: dict[str, Any], root: Path, provider: LLMProvider | None = None) -> dict[str, Any]:
    goal_structure = classify_goal_structure(run.get("task") or {})
    topology = build_topology(goal_structure)
    task = run.get("task") or {}

    if run["decision_type"] == "software_project_build_task":
        decomposition = decompose_software_task(task, topology, root, goal_structure)
    elif provider is not None:
        decomposition = _llm_decomposition(task, topology, goal_structure, provider)
    else:
        decomposition = _generic_decomposition(task, topology, goal_structure)

    packages = decomposition["packages"]
    return {
        "planning_id": f"planning/{run['decision_type']}/{run['run_id']}",
        "run_id": run["run_id"],
        "decision_type": run["decision_type"],
        "goal_structure": goal_structure,
        "topology": topology,
        "packages": packages,
        "dependencies": decomposition.get("dependencies", []),
        "reasoning": {
            "goal_structure": goal_structure["reasoning"],
            "topology": topology["topology_reasoning"],
            "package_decomposition": decomposition["worker_count_reasoning"]["reason"],
        },
        "package_outline": decomposition.get("package_outline", []),
        "worker_count_reasoning": decomposition["worker_count_reasoning"],
        "human_questions": decomposition.get("human_questions", []),
        "approval_status": "pending",
        "domain_context": {
            "domain": decomposition.get("domain", "generic"),
            "task_subtype": decomposition.get("task_subtype", "generic"),
            "affected_surfaces": decomposition.get("affected_surfaces", []),
            "repo_context": decomposition.get("repo_context", {}),
        },
    }


_NAMES = [
    "Ada", "Axel", "Bram", "Cleo", "Dax", "Echo", "Finn", "Gale", "Hana", "Io",
    "Jax", "Kira", "Lev", "Mira", "Nox", "Ora", "Pax", "Quinn", "Rael", "Sage",
    "Tess", "Uma", "Vex", "Wren", "Xan", "Yael", "Zora",
]


def _worker_id(phase_id: str, index: int) -> str:
    name = _NAMES[index % len(_NAMES)]
    return f"{name.lower()}_{phase_id}"


def artifact_to_proposal(artifact: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    workers = []
    for i, package in enumerate(artifact["packages"]):
        workers.append(
            {
                "worker_id": _worker_id(package["phase_id"], i),
                "work_package_id": package["id"],
                "phase_id": package["phase_id"],
                "worker_role": package["worker_role"],
                "layer": "execution",
                "work_layer": package["work_layer"],
                "goal": package["goal"],
                "read_paths": deepcopy(package["read_paths"]),
                "write_paths": deepcopy(package["write_paths"]),
                "allowed_tools": deepcopy(package["allowed_tools"]),
                "max_steps": 6,
                "validators": deepcopy(package["validators"]),
                "output_schema": deepcopy(package["output_schema"]),
                "completion_contract": package["completion_contract"],
            }
        )

    return {
        "architecture_id": f"dynamic/{run['decision_type']}/{run['run_id']}",
        "decision_type": run["decision_type"],
        "risk_level": "high" if "high_risk" in artifact["goal_structure"]["modifiers"] else "medium",
        "purpose": "Dynamic architecture derived from goal structure, topology, and bounded package decomposition.",
        "goal_structure": deepcopy(artifact["goal_structure"]),
        "topology": deepcopy(artifact["topology"]),
        "worker_count_reasoning": deepcopy(artifact["worker_count_reasoning"]),
        "package_outline": deepcopy(artifact["package_outline"]),
        "human_questions": deepcopy(artifact["human_questions"]),
        "evidence_profile": {
            "required_sources": ["task_request", "repository_structure", "local_docs"],
            "authority_weights": {"repository_structure": 0.95, "local_docs": 0.9, "task_request": 0.85},
            "conflict_rules": ["Bounded scope and validators override model preference."],
        },
        "work_layers": _work_layers_for_packages(artifact["packages"]),
        "workers": workers,
        "dependencies": deepcopy(artifact["dependencies"]),
        "action_gate": {
            "type": "human_gate",
            "requires_human_review": True,
            "automatic_final_action": False,
            "rule": "Human approval is required before generated contracts are treated as authoritative.",
        },
        "validators": ["architecture_proposal_schema", "write_scope", "dependency_graph", "human_gate"],
        "outcome_metrics": ["planning_artifact_created", "architecture_approved", "contracts_generated"],
    }


def propose_architecture(run: dict[str, Any], provider: LLMProvider, root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    artifact = build_planning_artifact(run, root, provider=provider)
    proposal = artifact_to_proposal(artifact, run)
    return artifact, proposal


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
    if not isinstance(goal_structure, dict) or goal_structure.get("shape") not in {"pipeline", "search", "funnel", "debate", "checker"}:
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


def _work_layers_for_packages(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    layers: dict[str, dict[str, Any]] = {}
    for package in packages:
        key = package["work_layer"]
        if key not in layers:
            layers[key] = {"id": key, "title": key.title(), "purpose": f"{key} work for the current task."}
    return list(layers.values())


def _llm_decomposition(
    task: dict[str, Any],
    topology: dict[str, Any],
    goal_structure: dict[str, Any],
    provider: LLMProvider,
) -> dict[str, Any]:
    shape = goal_structure["shape"]
    phases = topology["phases"]
    phase_list = ", ".join(f"{p['id']} ({p['done_means']})" for p in phases)

    system = (
        "You are a task decomposition planner. "
        "Given a task and a pre-determined execution topology, produce bounded work packages — "
        "one per topology phase — that are specific to what the task actually requires. "
        "Each package must have a concrete goal derived from the task content, not a generic placeholder. "
        "Respond with a single JSON object only. No markdown, no explanation outside the JSON."
    )

    user = (
        f"Task: {task.get('title', '')}\n"
        f"Description: {task.get('description', '') or 'none'}\n"
        f"Execution shape: {shape}\n"
        f"Phases: {phase_list}\n\n"
        "Return JSON with this exact shape:\n"
        "{\n"
        '  "packages": [\n'
        "    {\n"
        '      "id": "<phase_id>",\n'
        '      "phase_id": "<phase_id>",\n'
        '      "worker_role": "<role describing what this worker does for this specific task>",\n'
        '      "work_layer": "<phase_id>",\n'
        '      "goal": "<concrete goal for this specific task, not a generic description>",\n'
        '      "read_paths": ["docs/**"],\n'
        '      "write_paths": ["docs/**"],\n'
        '      "allowed_tools": ["read_file", "write_file", "list_files"],\n'
        '      "validators": ["write_scope"],\n'
        '      "output_fields": ["summary", "<2-3 fields that make sense for this phase and task>"]\n'
        "    }\n"
        "  ],\n"
        '  "human_questions": ["<question if task is underspecified, else empty array>"],\n'
        '  "worker_count_reasoning": "<one sentence explaining why this many workers>"\n'
        "}"
    )

    try:
        raw = provider.complete(system, user, max_tokens=1024)
        # strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw.strip())
        data = json.loads(raw)
    except Exception:
        return _generic_decomposition(task, topology, goal_structure)

    packages = []
    for item in data.get("packages", []):
        output_fields = item.get("output_fields", ["summary", "output"])
        packages.append({
            "id": item.get("id", item.get("phase_id", "unknown")),
            "phase_id": item.get("phase_id", item.get("id", "unknown")),
            "worker_role": item.get("worker_role", f"{item.get('id', 'worker')}_worker"),
            "work_layer": item.get("work_layer", item.get("phase_id", "generic")),
            "goal": item.get("goal", ""),
            "read_paths": item.get("read_paths") or ["docs/**"],
            "write_paths": item.get("write_paths") or ["docs/**"],
            "allowed_tools": item.get("allowed_tools") or ["read_file", "write_file", "list_files"],
            "validators": item.get("validators") or ["write_scope"],
            "output_schema": {
                "type": "object",
                "required": output_fields,
                "properties": {f: {"type": "string" if f == "summary" else "array"} for f in output_fields},
            },
            "completion_contract": f"Return {', '.join(output_fields)}.",
        })

    if not packages:
        return _generic_decomposition(task, topology, goal_structure)

    dependencies: list[dict[str, Any]] = []
    for i, pkg in enumerate(packages[1:], start=1):
        dependencies.append({
            "from": pkg["id"],
            "on": packages[i - 1]["id"],
            "reason": f"{pkg['id']} depends on output from {packages[i - 1]['id']}.",
        })

    return {
        "domain": "generic",
        "task_subtype": shape,
        "affected_surfaces": [],
        "repo_context": {},
        "packages": packages,
        "dependencies": dependencies,
        "human_questions": data.get("human_questions", []),
        "package_outline": [{"id": p["id"], "work_layer": p["work_layer"], "phase_id": p["phase_id"]} for p in packages],
        "worker_count_reasoning": {
            "total_workers": len(packages),
            "reason": data.get("worker_count_reasoning", f"{shape} topology with {len(packages)} task-specific workers."),
            "task_subtype": shape,
            "affected_surfaces": [],
        },
    }


_PHASE_GOALS: dict[str, str] = {
    # pipeline
    "scope": "Scope the task, clarify constraints, and define acceptance criteria.",
    "assemble": "Produce the requested artifact within the bounded scope.",
    "review": "Review the assembled result for completeness and quality.",
    # search
    "frame": "Frame the search space, define criteria, and set boundaries.",
    "explore": "Explore candidate options and gather supporting evidence.",
    "converge": "Converge on a justified result from the explored candidates.",
    # funnel
    "collect": "Collect candidate options for evaluation.",
    "narrow": "Narrow options against criteria to a shortlist.",
    "decide": "Select the recommended outcome from the shortlist.",
    # debate
    "position_a": "Develop the primary position with supporting reasoning.",
    "position_b": "Develop the counter-position with supporting reasoning.",
    "adjudicate": "Resolve competing positions and synthesise a conclusion.",
    # checker
    "verify": "Verify claims against collected evidence.",
    "gate": "Apply the final review gate and record the decision.",
}

_PHASE_OUTPUT_FIELDS: dict[str, list[str]] = {
    "scope":       ["summary", "constraints", "questions"],
    "assemble":    ["summary", "output", "files_changed"],
    "review":      ["summary", "issues", "verdict"],
    "frame":       ["summary", "search_criteria", "boundaries"],
    "explore":     ["summary", "candidates", "evidence"],
    "converge":    ["summary", "result", "reasoning"],
    "collect":     ["summary", "candidates"],
    "narrow":      ["summary", "shortlist", "eliminated"],
    "decide":      ["summary", "recommendation", "reasoning"],
    "position_a":  ["summary", "position", "arguments"],
    "position_b":  ["summary", "position", "arguments"],
    "adjudicate":  ["summary", "conclusion", "reasoning"],
    "verify":      ["summary", "findings", "verdict"],
    "gate":        ["summary", "decision", "reasoning"],
}

_DEFAULT_OUTPUT_FIELDS = ["summary", "output"]


def _package_for_phase(phase: dict[str, Any]) -> dict[str, Any]:
    phase_id = phase["id"]
    goal = _PHASE_GOALS.get(phase_id, f"Complete the {phase_id} phase of the task.")
    output_fields = _PHASE_OUTPUT_FIELDS.get(phase_id, _DEFAULT_OUTPUT_FIELDS)
    return {
        "id": phase_id,
        "phase_id": phase_id,
        "worker_role": f"{phase_id}_worker",
        "work_layer": phase_id,
        "goal": goal,
        "read_paths": ["docs/**", "README.md"],
        "write_paths": ["docs/**"],
        "allowed_tools": ["read_file", "write_file", "list_files"],
        "validators": ["write_scope"],
        "output_schema": {
            "type": "object",
            "required": output_fields,
            "properties": {f: {"type": "array" if f not in ("summary", "verdict", "result", "recommendation", "decision", "conclusion") else "string"} for f in output_fields},
        },
        "completion_contract": f"Return {', '.join(output_fields)}.",
    }


def _generic_decomposition(task: dict[str, Any], topology: dict[str, Any], goal_structure: dict[str, Any]) -> dict[str, Any]:
    packages = [_package_for_phase(phase) for phase in topology["phases"]]

    dependencies: list[dict[str, Any]] = []
    for i, package in enumerate(packages[1:], start=1):
        dependencies.append({
            "from": package["id"],
            "on": packages[i - 1]["id"],
            "reason": f"{package['id']} depends on output from {packages[i - 1]['id']}.",
        })

    human_questions = (
        ["What is the expected output or deliverable for this task?"]
        if "needs_clarification" in goal_structure.get("modifiers", [])
        else []
    )

    shape = goal_structure["shape"]
    return {
        "domain": "generic",
        "task_subtype": shape,
        "affected_surfaces": [],
        "repo_context": {},
        "packages": packages,
        "dependencies": dependencies,
        "human_questions": human_questions,
        "package_outline": [{"id": p["id"], "work_layer": p["work_layer"], "phase_id": p["phase_id"]} for p in packages],
        "worker_count_reasoning": {
            "total_workers": len(packages),
            "reason": f"{shape} topology derived {len(packages)} phase workers from goal structure.",
            "task_subtype": shape,
            "affected_surfaces": [],
        },
    }
