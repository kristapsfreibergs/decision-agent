from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from decision_agent.modules.architectures.planning import build_planning_artifact

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


def _work_layers_for_packages(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    layers: dict[str, dict[str, Any]] = {}
    for package in packages:
        key = package["work_layer"]
        if key not in layers:
            layers[key] = {"id": key, "title": key.title(), "purpose": f"{key} work for the current task."}
    return list(layers.values())


def propose_architecture(run: dict[str, Any], provider: LLMProvider, root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    artifact = build_planning_artifact(run, root, provider=provider)
    proposal = artifact_to_proposal(artifact, run)
    return artifact, proposal
