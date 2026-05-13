from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_agent.modules.architectures.decomposers.software import decompose_software_task
from decision_agent.modules.architectures.domain_catalog import _DOMAIN_CATALOG, _detect_domain
from decision_agent.modules.architectures.generic_decomposition import _generic_decomposition
from decision_agent.modules.architectures.goal_structure import classify_goal_structure
from decision_agent.modules.architectures.topology import build_topology
from decision_agent.modules.workers.explorers import EXPLORER_CATALOG, build_explorer_package
from decision_agent.shared.providers.base import LLMProvider

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
