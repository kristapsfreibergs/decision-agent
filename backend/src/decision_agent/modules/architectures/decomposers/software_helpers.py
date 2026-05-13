from __future__ import annotations

import re
from pathlib import Path
from typing import Any

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
