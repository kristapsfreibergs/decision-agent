from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from decision_agent.modules.architectures.decomposers.software import decompose_software_task
from decision_agent.modules.architectures.domains import story as _story_domain
from decision_agent.modules.architectures.domains import procurement as _procurement_domain
from decision_agent.modules.architectures.goal_structure import classify_goal_structure
from decision_agent.modules.architectures.topology import build_topology
from decision_agent.modules.workers.explorers import EXPLORER_CATALOG, build_explorer_package
from decision_agent.shared.providers.base import LLMProvider

# Domain catalog — each entry maps domain name to (spec, decomposition_fn, detection_keywords).
# To add a new domain: create a domain module with DOMAIN_ID, DETECTION_KEYWORDS,
# DOMAIN_SPEC, and build_*_decomposition(task, run_id). Register it here.
# No other files need to change.
_DOMAIN_CATALOG: dict[str, tuple[dict, Any, tuple[str, ...]]] = {
    _story_domain.DOMAIN_ID: (
        _story_domain.DOMAIN_SPEC,
        _story_domain.build_story_decomposition,
        _story_domain.DETECTION_KEYWORDS,
    ),
    _procurement_domain.DOMAIN_ID: (
        _procurement_domain.DOMAIN_SPEC,
        _procurement_domain.build_procurement_decomposition,
        _procurement_domain.DETECTION_KEYWORDS,
    ),
}


def _build_detect_prompt() -> str:
    """Build the domain detection system prompt dynamically from the catalog."""
    lines = [
        "You are a task domain classifier. Given a task title and description, "
        f"decide if it belongs to one of these known domains: {', '.join(_DOMAIN_CATALOG)}. "
    ]
    for domain_id, (spec, _, keywords) in _DOMAIN_CATALOG.items():
        lines.append(f"- {domain_id}: {', '.join(keywords[:5])}.")
    domain_list = " or ".join(
        f'{{\"domain\": \"{d}\"}}' for d in _DOMAIN_CATALOG
    )
    lines.append(f'Respond with JSON only: {domain_list} or {{"domain": null}}')
    return " ".join(lines)


def _detect_domain(task: dict[str, Any], provider: LLMProvider | None) -> str | None:
    text = f"{task.get('title', '')} {task.get('description', '')}".lower()
    # Deterministic catalog match first. Domain catalogs are safety-critical
    # architecture choices and should not depend on provider quality.
    for domain_id, (_, _, keywords) in _DOMAIN_CATALOG.items():
        if any(w in text for w in keywords):
            return domain_id

    if provider is None:
        return None
    user = f"Task: {task.get('title', '')}\nDescription: {task.get('description', '') or 'none'}"
    try:
        raw = provider.complete(_build_detect_prompt(), user, max_tokens=64)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw.strip())
        data = json.loads(raw)
        domain = data.get("domain")
        return domain if domain in _DOMAIN_CATALOG else None
    except Exception:
        return None

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
    task = run.get("task") or {}
    domain = run.get("decision_type") if run.get("decision_type") in _DOMAIN_CATALOG else _detect_domain(task, provider)

    if domain in _DOMAIN_CATALOG:
        domain_spec, build_fn, _ = _DOMAIN_CATALOG[domain]
        goal_structure = domain_spec["goal_structure"]
        topology = domain_spec["topology"]
        decomposition = build_fn(task, run["run_id"])
    else:
        goal_structure = classify_goal_structure(task, provider=provider)
        goal_structure = _apply_intake_policy(goal_structure, run, task, root)
        topology = build_topology(goal_structure)
        if run["decision_type"] == "software_project_build_task":
            decomposition = decompose_software_task(task, topology, root, goal_structure)
        else:
            decomposition = _generic_decomposition(task, topology, goal_structure)

    packages = decomposition["packages"]
    dependencies = decomposition.get("dependencies", [])
    explorer_packages = _build_intake_explorer_packages(goal_structure, run, task)
    if explorer_packages:
        packages, dependencies = _inject_explorer_packages(
            explorer_packages,
            packages,
            dependencies,
        )
    return {
        "planning_id": f"planning/{run['decision_type']}/{run['run_id']}",
        "run_id": run["run_id"],
        "decision_type": run["decision_type"],
        "goal_structure": goal_structure,
        "topology": topology,
        "packages": packages,
        "dependencies": dependencies,
        "reasoning": {
            "goal_structure": goal_structure["reasoning"],
            "topology": topology["topology_reasoning"],
            "package_decomposition": decomposition["worker_count_reasoning"]["reason"],
        },
        "package_outline": [
            {"id": package["id"], "work_layer": package["work_layer"], "phase_id": package["phase_id"]}
            for package in packages
        ],
        "worker_count_reasoning": decomposition["worker_count_reasoning"],
        "human_questions": decomposition.get("human_questions", []),
        "approval_status": "pending",
        "evidence_profile": decomposition.get("evidence_profile"),
        "scope_profile": decomposition.get("scope_profile"),
        "consequence_table": decomposition.get("consequence_table"),
        "action_gate": decomposition.get("action_gate"),
        "domain_context": {
            "domain": decomposition.get("domain", "generic"),
            "task_subtype": decomposition.get("task_subtype", "generic"),
            "affected_surfaces": decomposition.get("affected_surfaces", []),
            "repo_context": decomposition.get("repo_context", {}),
        },
    }


def _apply_intake_policy(
    goal_structure: dict[str, Any],
    run: dict[str, Any],
    task: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    sources = list(goal_structure.get("intake_sources", []))
    reasons = list(goal_structure.get("intake_policy_reasoning", []))
    text = " ".join(
        str(value)
        for value in [task.get("title"), task.get("description"), *(task.get("desired_outputs") or [])]
        if value
    ).lower()

    if run.get("decision_type") == "software_project_build_task":
        has_repo = (root / "backend").exists() or (root / "public").exists()
        code_terms = (
            "api",
            "backend",
            "frontend",
            "server",
            "endpoint",
            "code",
            "file",
            "module",
            "function",
            "class",
            "implement",
            "add",
        )
        if has_repo and any(term in text for term in code_terms) and "codebase_explorer" not in sources:
            sources.insert(0, "codebase_explorer")
            reasons.append("software code-writing task requires codebase_explorer")

    modifiers = list(goal_structure.get("modifiers", []))
    if sources and "requires_intake" not in modifiers:
        modifiers.append("requires_intake")

    return {
        **goal_structure,
        "modifiers": sorted(set(modifiers)),
        "intake_sources": sources,
        "intake_policy_reasoning": reasons,
    }


def _build_intake_explorer_packages(
    goal_structure: dict[str, Any],
    run: dict[str, Any],
    task: dict[str, Any],
) -> list[dict[str, Any]]:
    intake_sources = goal_structure.get("intake_sources", [])
    if not isinstance(intake_sources, list):
        return []
    task_context = f"{task.get('title', '')}. {task.get('description') or ''}".strip()
    return [
        build_explorer_package(source, run["run_id"], task_context)
        for source in intake_sources
        if source in EXPLORER_CATALOG
    ]


def _inject_explorer_packages(
    explorer_packages: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    explorer_ids = [package["id"] for package in explorer_packages]
    package_ids = {package["id"] for package in packages}
    existing_edges = {
        (dependency.get("from"), dependency.get("on"))
        for dependency in dependencies
    }
    extra_dependencies = [
        {
            "from": package_id,
            "on": explorer_id,
            "reason": f"Worker needs {explorer_id} context before starting.",
        }
        for package_id in package_ids
        for explorer_id in explorer_ids
        if (package_id, explorer_id) not in existing_edges
    ]
    return explorer_packages + packages, extra_dependencies + dependencies


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
        worker_id = package.get("worker_id") or _worker_id(package["phase_id"], i)
        workers.append(
            {
                "worker_id": worker_id,
                "work_package_id": package["id"],
                "phase_id": package["phase_id"],
                "worker_role": package["worker_role"],
                "layer": "execution",
                "work_layer": package["work_layer"],
                "goal": package["goal"],
                "read_paths": deepcopy(package["read_paths"]),
                "write_paths": deepcopy(package["write_paths"]),
                "allowed_tools": deepcopy(package["allowed_tools"]),
                "max_steps": package.get("max_steps", 6),
                "validators": deepcopy(package["validators"]),
                "output_schema": deepcopy(package["output_schema"]),
                "completion_contract": package["completion_contract"],
                "dar_action_type": package.get("dar_action_type"),
                "dar_consequence_class": package.get("dar_consequence_class"),
                "allowed_tables": deepcopy(package.get("allowed_tables") or []),
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
        "evidence_profile": artifact.get("evidence_profile") or {
            "required_sources": ["task_request", "repository_structure", "local_docs"],
            "authority_weights": {"repository_structure": 0.95, "local_docs": 0.9, "task_request": 0.85},
            "conflict_rules": ["Bounded scope and validators override model preference."],
        },
        "scope_profile": artifact.get("scope_profile"),
        "consequence_table": artifact.get("consequence_table"),
        "work_layers": _work_layers_for_packages(artifact["packages"]),
        "workers": workers,
        "dependencies": deepcopy(artifact["dependencies"]),
        "action_gate": artifact.get("action_gate") or {
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


def _work_layers_for_packages(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    layers: dict[str, dict[str, Any]] = {}
    for package in packages:
        key = package["work_layer"]
        if key not in layers:
            layers[key] = {"id": key, "title": key.title(), "purpose": f"{key} work for the current task."}
    return list(layers.values())


def _generic_decomposition(task: dict[str, Any], topology: dict[str, Any], goal_structure: dict[str, Any]) -> dict[str, Any]:
    task_title = task.get("title") or "Unnamed task"
    task_description = task.get("description") or ""
    task_context = f'Task: "{task_title}". {task_description}'.strip()
    human_questions = (
        ["What is the expected output or deliverable for this task?"]
        if "needs_clarification" in goal_structure.get("modifiers", [])
        else []
    )
    shape = goal_structure["shape"]
    packages = [
        {
            "id": "plain_llm",
            "worker_id": "plain_llm",
            "phase_id": "answer",
            "worker_role": "plain_llm",
            "work_layer": "answer",
            "goal": (
                f"{task_context}\n\n"
                "Handle this task as a single plain LLM worker. Do not assume access to external tools. "
                "Produce the best bounded answer from the task prompt and clearly state any assumptions or gaps."
            ),
            "read_paths": ["docs/**", "README.md"],
            "write_paths": ["docs/**"],
            "allowed_tools": [],
            "validators": ["write_scope"],
            "output_schema": {
                "type": "object",
                "required": ["summary", "answer", "assumptions", "files_changed"],
                "properties": {
                    "summary": {"type": "string"},
                    "answer": {"type": "string"},
                    "assumptions": {"type": "array"},
                    "files_changed": {"type": "array"},
                },
            },
            "completion_contract": "Return summary, answer, assumptions, files_changed.",
        }
    ]
    return {
        "domain": "generic",
        "task_subtype": "plain_llm",
        "affected_surfaces": [],
        "repo_context": {},
        "packages": packages,
        "dependencies": [],
        "human_questions": human_questions,
        "package_outline": [{"id": p["id"], "work_layer": p["work_layer"], "phase_id": p["phase_id"]} for p in packages],
        "worker_count_reasoning": {
            "total_workers": 1,
            "reason": f"No specific domain catalog matched; using one plain LLM fallback worker instead of a generated {shape} team.",
            "task_subtype": "plain_llm",
            "affected_surfaces": [],
        },
    }
