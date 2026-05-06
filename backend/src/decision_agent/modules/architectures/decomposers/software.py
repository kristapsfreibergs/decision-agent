from __future__ import annotations

import re
from pathlib import Path
from typing import Any


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
                ["docs/**", "backend/src/**", "public/**"],
                ["docs/**"],
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
                    ["backend/src/**", "docs/**"],
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
                    ["public/**", "backend/src/**"],
                    ["public/**"],
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
                    ["backend/src/**", "docs/**"],
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
                    ["backend/src/**", "backend/tests/**", "public/**"],
                    ["backend/tests/**"],
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


def _package(
    package_id: str,
    phase_id: str,
    work_layer: str,
    goal: str,
    read_paths: list[str],
    write_paths: list[str],
    allowed_tools: list[str],
    validators: list[str],
    output_fields: list[str],
) -> dict[str, Any]:
    return {
        "id": package_id,
        "phase_id": phase_id,
        "worker_role": f"{work_layer}_worker",
        "work_layer": work_layer,
        "goal": goal,
        "read_paths": read_paths,
        "write_paths": write_paths,
        "allowed_tools": allowed_tools,
        "validators": validators,
        "output_schema": {
            "type": "object",
            "required": output_fields,
            "properties": {field: {"type": "array" if field.endswith("s") or field == "files_changed" or field == "test_commands" else "string"} for field in output_fields},
        },
        "completion_contract": f"Return {', '.join(output_fields)}.",
    }


def _repo_context(root: Path) -> dict[str, Any]:
    return {
        "has_backend": (root / "backend" / "src").exists(),
        "has_public_ui": (root / "public").exists(),
        "has_tests": (root / "backend" / "tests").exists(),
        "has_docs": (root / "docs").exists(),
    }


def _software_subtype(text: str) -> str:
    if "auth" in text or "security" in text:
        return "auth_rewrite"
    if "health check" in text or "healthcheck" in text or "endpoint" in text:
        return "api_endpoint_change"
    if "ui" in text or "frontend" in text:
        return "ui_change"
    if "document" in text or "docs" in text:
        return "docs_change"
    if "infra" in text or "deploy" in text:
        return "infra_change"
    return "cross_surface_change"


def _affected_surfaces(text: str) -> list[str]:
    words = set(re.findall(r"[a-z0-9_]+", text))
    surfaces: list[str] = []
    if any(token in words for token in ("api", "endpoint", "backend", "server")) or any(phrase in text for phrase in ("health check", "healthcheck")):
        surfaces.append("api")
    if any(token in words for token in ("ui", "frontend", "page", "screen", "dashboard")):
        surfaces.append("ui")
    if any(token in words for token in ("logic", "workflow", "orchestration", "decision")):
        surfaces.append("logic")
    if any(token in words for token in ("test", "validate", "review", "check")):
        surfaces.append("validation")
    if any(token in words for token in ("auth", "security")):
        surfaces.extend(["api", "logic", "validation"])
    if not surfaces:
        surfaces.extend(["api", "validation"])
    return sorted(set(surfaces))


def _phase_for_slot(topology: dict[str, Any], preferred_ids: tuple[str, ...], fallback: int) -> str:
    phases = topology["phases"]
    for preferred in preferred_ids:
        for phase in phases:
            if phase["id"] == preferred:
                return phase["id"]
    return phases[fallback]["id"]


def _dependencies_for_packages(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dependencies: list[dict[str, Any]] = []
    api_exists = any(package["id"] == "api_change" for package in packages)
    for package in packages:
        if package["id"] == "ui_change" and api_exists:
            dependencies.append({"from": "ui_change", "on": "api_change", "reason": "UI depends on backend response shape."})
        if package["id"] == "validation_check":
            if api_exists:
                dependencies.append({"from": "validation_check", "on": "api_change", "reason": "Validation checks backend behavior."})
            if any(p["id"] == "ui_change" for p in packages):
                dependencies.append({"from": "validation_check", "on": "ui_change", "reason": "Validation checks exposed UI state."})
    return dependencies


def _reason_for_worker_count(subtype: str, packages: list[dict[str, Any]], ambiguous: bool) -> str:
    if ambiguous:
        return "Scope is unclear, so the builder reduced the first slice to clarification instead of broad implementation."
    if subtype == "api_endpoint_change":
        return "A bounded endpoint change needs one implementation package and one validation package."
    if subtype == "auth_rewrite":
        return "Auth or security work spans logic, API, and validation surfaces, which expands worker count."
    return f"Worker count follows bounded package count for subtype {subtype}."
