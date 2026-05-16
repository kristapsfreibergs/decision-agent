from __future__ import annotations

from pathlib import Path
from typing import Any

from decision_agent.modules.architectures.decomposers.software_helpers import (
    _affected_surfaces,
    _dependencies_for_packages,
    _package,
    _phase_for_slot,
    _reason_for_worker_count,
    _repo_context,
    _software_subtype,
)

def decompose_software_task(
    task: dict[str, Any],
    topology: dict[str, Any],
    root: Path,
    goal_structure: dict[str, Any],
) -> dict[str, Any]:
    text = " ".join(str(task.get(key) or "") for key in ("title", "description")).lower()
    affected_surfaces = _affected_surfaces(text)
    subtype = _software_subtype(text)
    repo_context = _repo_context(root)
    ambiguous = "needs_clarification" in set(goal_structure.get("modifiers", []))

    task_title = task.get("title") or "Unnamed task"
    task_description = task.get("description") or ""
    task_context = f'Task: "{task_title}". {task_description}'.strip()

    packages: list[dict[str, Any]] = []
    human_questions: list[str] = []

    if ambiguous:
        human_questions.append("Which service, module, or repository surface should change first?")
        packages.append(
            _package(
                "clarify_scope",
                topology["phases"][0]["id"],
                "planning",
                f"{task_context}\n\nClarify task scope, affected module, and acceptance checks before implementation. Use list_files and read_file to explore the codebase and understand what needs to change.",
                ["archive/docs/**", "backend/src/**", "archive/public/**"],
                ["archive/docs/**"],
                ["read_file", "list_files"],
                ["human_scope_confirmation"],
                ["scope_summary", "questions"],
            )
        )
    else:
        if "api" in affected_surfaces:
            packages.append(
                _package(
                    "api_change",
                    _phase_for_slot(topology, ("scope", "assemble", "explore", "collect"), fallback=0),
                    "api",
                    f"{task_context}\n\nImplement the required backend/API change. Use list_files to find relevant files, read_file to understand existing code, then write_file to make the changes. Write complete, working code — not stubs.",
                    ["backend/src/**", "archive/docs/**"],
                    ["backend/src/**"],
                    ["read_file", "write_file", "list_files"],
                    ["write_scope"],
                    ["summary", "files_changed", "public_api"],
                )
            )

        if "ui" in affected_surfaces:
            packages.append(
                _package(
                    "ui_change",
                    _phase_for_slot(topology, ("assemble", "explore", "collect"), fallback=1),
                    "ui",
                    f"{task_context}\n\nUpdate the operator-facing UI to expose the changed decision state or API surface. Use list_files to find relevant files, read_file to understand existing code, then write_file to make the changes.",
                    ["archive/public/**", "backend/src/**"],
                    ["archive/public/**"],
                    ["read_file", "write_file", "list_files"],
                    ["write_scope"],
                    ["summary", "files_changed", "ui_states"],
                )
            )

        if "logic" in affected_surfaces:
            packages.append(
                _package(
                    "logic_change",
                    _phase_for_slot(topology, ("assemble", "explore"), fallback=1),
                    "logic",
                    f"{task_context}\n\nUpdate internal logic or orchestration required by the task. Use list_files to find relevant files, read_file to understand existing code, then write_file to make the changes. Write complete, working code — not stubs.",
                    ["backend/src/**", "archive/docs/**"],
                    ["backend/src/**"],
                    ["read_file", "write_file", "list_files"],
                    ["write_scope"],
                    ["summary", "files_changed", "behavior_changes"],
                )
            )

        if "validation" in affected_surfaces or subtype in {"api_endpoint_change", "cross_surface_change", "auth_rewrite"}:
            packages.append(
                _package(
                    "validation_check",
                    _phase_for_slot(topology, ("review", "verify", "converge", "decide", "adjudicate", "gate"), fallback=-1),
                    "validation",
                    f"{task_context}\n\nValidate the implementation with focused tests. Use list_files and read_file to understand what was changed, then write_file to write or update test files.",
                    ["backend/src/**", "tests/**", "archive/public/**"],
                    ["tests/**"],
                    ["read_file", "write_file", "list_files"],
                    ["tests_run"],
                    ["summary", "files_changed", "test_commands"],
                )
            )

    dependencies = _dependencies_for_packages(packages)
    package_outline = [{"id": package["id"], "work_layer": package["work_layer"], "phase_id": package["phase_id"]} for package in packages]
    worker_count_reasoning = {
        "total_workers": len(packages),
        "reason": _reason_for_worker_count(subtype, packages, ambiguous),
        "affected_surfaces": affected_surfaces,
        "task_subtype": subtype,
    }

    return {
        "domain": "software",
        "task_subtype": subtype,
        "affected_surfaces": affected_surfaces,
        "repo_context": repo_context,
        "packages": packages,
        "dependencies": dependencies,
        "human_questions": human_questions,
        "package_outline": package_outline,
        "worker_count_reasoning": worker_count_reasoning,
    }
